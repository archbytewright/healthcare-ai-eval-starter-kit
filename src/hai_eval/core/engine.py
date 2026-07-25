"""Run a tool over a scenario set and score what came back.

The engine owns four things a probe must not: verifying a claimed capability level, resolving how
far a finding can be trusted, deciding what may block, and deciding how an absence affects the
score. Each of those was a place where v0.1 trusted something it should have been measuring.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Protocol

from loguru import logger
from pydantic import BaseModel, ValidationError

from hai_eval.core.evidence import Evidence, Pair, Sample
from hai_eval.core.levels import Level
from hai_eval.core.models import CriterionScore, Rubric, ToolResponse
from hai_eval.core.outcomes import Cause, Disagreement, Unmeasurable
from hai_eval.core.profile import Profile, weakest
from hai_eval.core.verdicts import ProbeTier, Verdict

if TYPE_CHECKING:
    from collections.abc import Sequence

    from hai_eval.core.models import Criterion, ScenarioSet


def _ids(pairs: Sequence[Pair[Any]]) -> tuple[str, ...]:
    return tuple(sorted(p.scenario.id for p in pairs))


MANUAL_PREFIX = "manual_"
"""Reserved prefix declaring that a criterion is reviewed by a human.

Makes "no automated check" something an author writes on purpose, so it can be told apart from a
mistyped probe name -- which used to look identical and silently deleted the criterion.
"""


class EvaluationError(RuntimeError):
    """The harness cannot score this run, and will not guess."""


class ToolUnderTest[S](Protocol):
    """One method, plus a name. Everything a tool reports about itself is derived, not asserted.

    ``respond`` is called once per requested sample, so it must be safe to call repeatedly with the
    same scenario. A deterministic tool simply returns the same thing each time.

    Generic over the scenario type because an adapter is written against ONE profile: a tool that
    understands a scenario carrying one domain's annotations is not a tool that understands another
    domain's. Typing it as the base scenario would let the two be mixed silently, which is the sort
    of thing that reads as flexibility right up to the moment it produces a nonsense report.
    """

    @property
    def name(self) -> str: ...

    def respond(self, scenario: S) -> ToolResponse: ...


@dataclass(frozen=True)
class AxisScore:
    axis_key: str
    title: str
    weight: float
    criterion_scores: tuple[CriterionScore, ...]

    @property
    def mean(self) -> float | None:
        """Mean over criteria that produced a number, counting tool-caused absences as zero.

        The two cases are deliberately different. A criterion the rubric cannot automate is dropped
        -- it says nothing about the tool. A criterion the TOOL prevented from running scores zero,
        because otherwise declining is a way to delete a check rather than fail it, and a tool that
        answered nothing reached a perfect score.
        """
        values = [
            (0.0 if cs.verdict is None else float(cs.verdict))
            for cs in self.criterion_scores
            if cs.verdict is not None or cs.counts_against_tool
        ]
        return sum(values) / len(values) if values else None


@dataclass(frozen=True)
class Coverage:
    criteria_scored: int
    criteria_total: int
    weight_scored: float
    weight_total: float
    scenarios_total: int
    samples_per_scenario: int
    levels_reached: tuple[tuple[str, str], ...]
    """(scenario id, level label) for every response, so a reader can see where a tool degraded."""

    @property
    def weight_fraction(self) -> float:
        return self.weight_scored / self.weight_total if self.weight_total else 0.0


@dataclass(frozen=True)
class EvaluationReport:
    tool_name: str
    rubric_name: str
    rubric_version: str
    profile_ref: str
    scale_max: int
    scenario_set: str
    axis_scores: tuple[AxisScore, ...]
    blocking_findings: tuple[str, ...]
    coverage: Coverage
    provenance: dict[str, str]

    @property
    def weighted_score(self) -> float | None:
        num = 0.0
        weight_total = 0.0
        for axis in self.axis_scores:
            mean = axis.mean
            if mean is None:
                continue
            num += mean * axis.weight
            weight_total += axis.weight
        return num / weight_total if weight_total else None

    @property
    def max_level_reached(self) -> Level:
        """The best any response managed; the score's label is qualified by it."""
        seen = [lvl for _, lvl in self.coverage.levels_reached]
        order = {"prose": Level.PROSE, "structured": Level.STRUCTURED, "grounded": Level.GROUNDED}
        return max((order[s] for s in seen), default=Level.PROSE)


def _verify_level(response: ToolResponse, profile: Profile) -> tuple[Level, BaseModel | None, str]:
    """Check a claimed level against the artifact actually supplied.

    A level is a claim until this passes. An adapter that says STRUCTURED and ships nothing valid is
    reported as an INTEGRATION finding rather than being quietly demoted, because "your connector is
    broken" and "your model is unsafe" are different conversations with different owners.
    """
    claimed = response.level
    if claimed <= Level.PROSE:
        return Level.PROSE, None, ""
    if claimed not in profile.levels:
        return (
            Level.PROSE,
            None,
            (f"claimed level '{claimed.label}' is not supported by profile {profile.ref}"),
        )
    if profile.artifact_model is None or response.artifact is None:
        return Level.PROSE, None, f"claimed level '{claimed.label}' but supplied no artifact"
    try:
        artifact = profile.artifact_model.model_validate(response.artifact)
    except ValidationError as exc:
        return (
            Level.PROSE,
            None,
            f"claimed level '{claimed.label}' but the artifact is invalid: {exc}",
        )
    return claimed, artifact, ""


def run_evaluation(
    tool: ToolUnderTest[Any],
    rubric: Rubric,
    scenario_set: ScenarioSet,
    profile: Profile,
    *,
    samples: int = 1,
) -> EvaluationReport:
    """Run ``tool`` over the scenarios and score it against ``rubric``.

    ``samples`` draws each scenario that many times. One draw cannot distinguish a tool that is
    right from one that is right this time, so the count is explicit rather than assumed, and every
    sample is verified independently.

    Raises:
        EvaluationError: if the rubric targets another profile, names a check the profile does not
            supply, or the responses do not correspond one-to-one with the scenarios.
    """
    if samples < 1:
        msg = f"samples must be at least 1, got {samples}"
        raise EvaluationError(msg)
    if rubric.profile != profile.ref:
        msg = f"rubric targets profile {rubric.profile!r} but {profile.ref!r} was supplied"
        raise EvaluationError(msg)

    # A criterion naming a check the profile does not have used to be reported as the rubric's gap,
    # which excluded it from the score AND took its axis weight out of the divisor -- so a
    # one-character typo in a probe name raised a failing tool to a perfect score and deleted its
    # blocking finding. Exactly the defect that was fixed for axis names and left open for probe
    # names. A criterion meant for human review declares it with the reserved prefix.
    unknown = sorted(
        {
            c.probe
            for c in rubric.criteria
            if not c.probe.startswith(MANUAL_PREFIX) and c.probe not in profile.probes
        }
    )
    if unknown:
        msg = (
            f"rubric names check(s) {unknown} that profile {profile.ref!r} does not supply "
            f"(available: {sorted(profile.probes)}); use the {MANUAL_PREFIX!r} prefix for a "
            f"criterion reviewed by a human"
        )
        raise EvaluationError(msg)

    logger.info(
        "evaluating tool={} rubric={}@{} profile={} scenarios={}",
        tool.name,
        rubric.name,
        rubric.version,
        profile.ref,
        len(scenario_set.scenarios),
    )
    draws: dict[str, list[ToolResponse]] = {}
    misdirected: list[str] = []
    for scenario in scenario_set.scenarios:
        for index in range(samples):
            response = tool.respond(scenario)
            # A response must answer the scenario it was HANDED. Checking only that the set of ids
            # matched let a tool permute its own labels: the same violation, re-attributed to a
            # scenario that never forbade it, took a run from 0.0 with a blocking finding to a clean
            # 3.0. Comparing multisets cannot see that, because nothing goes missing.
            if response.scenario_id != scenario.id:
                label = scenario.id if samples == 1 else f"{scenario.id} sample {index + 1}"
                misdirected.append(f"{label} answered as {response.scenario_id!r}")
            draws.setdefault(scenario.id, []).append(response)
    if misdirected:
        msg = f"responses answer the wrong scenario: {'; '.join(misdirected)}"
        raise EvaluationError(msg)

    # An adapter returning the wrong scenario id used to shrink the run silently: the join dropped
    # unmatched cases, every emptied probe blamed the DATA for the adapter's bug, and
    # the thinned run scored full marks. Refuse instead.
    # No multiset check here any more. Once every response must answer the scenario it was handed
    # (above), the ids and the per-scenario counts follow by construction -- the old guard became
    # unreachable, and a check nothing can reach is indistinguishable from a check that does not
    # work. Deleted rather than kept as reassurance.

    pairs: list[Pair[Any]] = []
    faulted_scenarios: set[str] = set()
    integration_faults: list[str] = []
    for scenario in scenario_set.scenarios:
        collected: list[Sample[Any]] = []
        for index, response in enumerate(draws[scenario.id]):
            level, artifact, fault = _verify_level(response, profile)
            if fault:
                faulted_scenarios.add(scenario.id)
                label = f"{scenario.id}" if samples == 1 else f"{scenario.id} sample {index + 1}"
                integration_faults.append(f"{label}: {fault}")
            collected.append(
                Sample(
                    response=response.model_copy(update={"level": level}),
                    artifact=artifact,
                    level=level,
                )
            )
        pairs.append(Pair(scenario=scenario, samples=tuple(collected)))
    evidence = Evidence(pairs=tuple(pairs), samples_requested=samples)

    axis_scores: list[AxisScore] = []
    blocking: list[str] = []
    scored_criteria = 0
    total_criteria = 0
    scored_weight = 0.0

    for axis in rubric.axes:
        criterion_scores: list[CriterionScore] = []
        for criterion in rubric.criteria_for(axis.key):
            total_criteria += 1
            score = _score_one(
                criterion,
                axis_key=axis.key,
                evidence=evidence,
                profile=profile,
                faulted=faulted_scenarios,
            )
            if score.verdict is not None:
                scored_criteria += 1
            criterion_scores.append(score)

            # Blocking needs three things at once, all explicit: a hard fail, an axis the RUBRIC
            # marks eligible, and a check whose claim is exact. Any one of them missing and the
            # finding is reported without ending the conversation.
            if (
                score.verdict == Verdict.FAIL
                and axis.blocking_eligible
                and score.tier is ProbeTier.DETERMINISTIC
            ):
                blocking.append(f"{criterion.key}: {score.evidence}")

        axis_scores.append(
            AxisScore(
                axis_key=axis.key,
                title=axis.title,
                weight=axis.weight,
                criterion_scores=tuple(criterion_scores),
            )
        )
        if any(cs.verdict is not None or cs.counts_against_tool for cs in criterion_scores):
            scored_weight += axis.weight

    coverage = Coverage(
        criteria_scored=scored_criteria,
        criteria_total=total_criteria,
        weight_scored=scored_weight,
        weight_total=sum(a.weight for a in rubric.axes),
        scenarios_total=len(scenario_set.scenarios),
        samples_per_scenario=samples,
        levels_reached=tuple((p.scenario.id, p.level.label) for p in pairs),
    )
    # Adapter-supplied provenance is NAMESPACED. It arrives from the party under evaluation, and
    # unprefixed it could set a key like "integration faults" that reads as an engine finding --
    # which one did, in a red-team run that shipped "integration faults: none, independently
    # verified" into a report the engine had never checked.
    provenance = {
        f"adapter-declared: {key}": str(value)
        for key, value in dict(getattr(tool, "provenance", {}) or {}).items()
    }
    provenance["integration faults"] = (
        "; ".join(integration_faults) if integration_faults else "none detected"
    )

    report = EvaluationReport(
        tool_name=tool.name,
        rubric_name=rubric.name,
        rubric_version=rubric.version,
        profile_ref=profile.ref,
        scale_max=rubric.scale_max,
        scenario_set=scenario_set.name,
        axis_scores=tuple(axis_scores),
        blocking_findings=tuple(blocking),
        coverage=coverage,
        provenance=provenance,
    )
    check_conservation(report, rubric)
    return report


class ConservationError(EvaluationError):
    """Something left the calculation without anyone deciding it should.

    Raised, not logged. Every disappearing-evidence bug this core has had -- a criterion dropped by
    a mistyped probe name, an axis whose weight left the divisor, a scenario erased by a level gate,
    a denominator shrunk by a probe naming ids outside its own relevance -- was an instance of one
    class, and each was fixed one at a time while the class stayed open. This is the class.
    """


def check_conservation(report: EvaluationReport, rubric: Rubric) -> None:
    """Assert that nothing vanished between the rubric and the report.

    Three identities, each of which a past bug violated:

    1. **Disposition completeness.** Every criterion the rubric declares appears in the report
       exactly once, carrying either a verdict or a stated cause. A criterion cannot be silently
       absent, and it cannot be present with no disposition.
    2. **Scenario partition.** For every criterion, the scenarios it judged and the ones it could
       not partition the scenarios it applies to -- disjoint, and together exhaustive. A shrunken
       denominator shows up here as an arithmetic failure rather than as a better score.
    3. **Weight accounting.** Every axis is either scored or explicitly unassessed, and the weight
       said to be covered equals the weight of the axes that actually produced something.

    Called at the end of every run. It has never yet fired in anger; that is the point of an
    accounting identity, and it is cheap enough to keep asserting.
    """
    scored = [cs for axis in report.axis_scores for cs in axis.criterion_scores]

    declared = [c.key for c in rubric.criteria]
    present = [cs.criterion_key for cs in scored]
    if sorted(declared) != sorted(present):
        missing = sorted(set(declared) - set(present))
        extra = sorted(set(present) - set(declared))
        msg = f"criteria lost between rubric and report: missing={missing} unexpected={extra}"
        raise ConservationError(msg)

    for cs in scored:
        if cs.verdict is None and not cs.unmeasurable_cause:
            msg = f"{cs.criterion_key}: no verdict and no reason -- a criterion with no disposition"
            raise ConservationError(msg)
        judged, unjudged = set(cs.scenarios_judged), set(cs.scenarios_unjudged)
        relevant = set(cs.scenarios_relevant)
        if judged & unjudged:
            both = sorted(judged & unjudged)
            msg = f"{cs.criterion_key}: scenario(s) both judged and unjudged: {both}"
            raise ConservationError(msg)
        if judged | unjudged != relevant:
            lost = sorted(relevant - (judged | unjudged))
            invented = sorted((judged | unjudged) - relevant)
            msg = (
                f"{cs.criterion_key}: scenarios do not account for the relevant set "
                f"(unaccounted={lost}, invented={invented})"
            )
            raise ConservationError(msg)

    counted = sum(
        axis.weight
        for axis in report.axis_scores
        if any(cs.verdict is not None or cs.counts_against_tool for cs in axis.criterion_scores)
    )
    if abs(counted - report.coverage.weight_scored) > 1e-9:
        msg = (
            f"weight accounting disagrees: coverage says {report.coverage.weight_scored}, "
            f"the axes that produced something total {counted}"
        )
        raise ConservationError(msg)


def _score_one(
    criterion: Criterion,
    *,
    axis_key: str,
    evidence: Evidence[Any],
    profile: Profile,
    faulted: set[str],
) -> CriterionScore:
    """Resolve one criterion to a score, including the ways it can fail to resolve."""
    if criterion.probe.startswith(MANUAL_PREFIX):
        return CriterionScore(
            criterion_key=criterion.key,
            axis=axis_key,
            verdict=None,
            evidence=f"declared for human review ({criterion.probe})",
            tier=ProbeTier.MANUAL,
            unmeasurable_cause=Cause.RUBRIC.value,
            scenarios_relevant=(),
            scenarios_judged=(),
            scenarios_unjudged=(),
        )
    spec = profile.probes[criterion.probe]  # validated at entry to run_evaluation

    # Relevance and reachability are resolved PER CRITERION. Resolving them once for the whole run,
    # from its weakest response, meant one degraded scenario demoted every criterion in the rubric:
    # a tool that provably violated scope on four scenarios lost its blocking finding by falling
    # back to prose on a fifth, unrelated one.
    relevant = tuple(p for p in evidence.pairs if spec.relevant(p.scenario))
    if not relevant:
        return CriterionScore(
            criterion_key=criterion.key,
            axis=axis_key,
            verdict=None,
            evidence="no scenario in this set exercises this criterion",
            tier=criterion.tier,
            unmeasurable_cause=Cause.RUBRIC.value,
            scenarios_relevant=(),
            scenarios_judged=(),
            scenarios_unjudged=(),
        )

    usable = tuple(p for p in relevant if spec.tier_at(p.level) is not None)
    short = tuple(p for p in relevant if spec.tier_at(p.level) is None)
    if not usable:
        cause = (
            Cause.ADAPTER if short and all(p.scenario.id in faulted for p in short) else Cause.TOOL
        )
        blame = (
            "the integration failed to produce what it declared"
            if cause is Cause.ADAPTER
            else f"the tool exposed only '{min(p.level for p in relevant).label}'"
        )
        return CriterionScore(
            criterion_key=criterion.key,
            axis=axis_key,
            verdict=None,
            evidence=(
                f"needs '{spec.minimum_level.label}' evidence on "
                f"{', '.join(p.scenario.id for p in short)}; {blame}"
            ),
            tier=criterion.tier,
            unmeasurable_cause=cause.value,
            scenarios_relevant=_ids(relevant),
            scenarios_judged=(),
            scenarios_unjudged=_ids(relevant),
            counts_against_tool=True,
        )

    # Trust comes from the weakest level among the scenarios actually used, not from the run.
    tier_for_level = weakest(*(spec.tier_at(p.level) for p in usable))
    outcome = spec.fn(criterion, evidence)

    if isinstance(outcome, Unmeasurable):
        return CriterionScore(
            criterion_key=criterion.key,
            axis=axis_key,
            verdict=None,
            evidence=outcome.reason,
            tier=criterion.tier,
            unmeasurable_cause=outcome.cause.value,
            scenarios_relevant=_ids(relevant),
            scenarios_judged=(),
            scenarios_unjudged=_ids(relevant),
            counts_against_tool=outcome.cause in (Cause.TOOL, Cause.ADAPTER),
        )

    if isinstance(outcome, Disagreement):
        # A contradiction between sources is a hard fail so it cannot be a warning nobody acts on --
        # but it goes through the SAME capping path as any other verdict. Returning it used to be a
        # way around the cap entirely: a criterion the rubric called fallible produced an uncapped
        # zero with no caveat, purely by choosing a different outcome type.
        verdict = Verdict.FAIL
        text = f"sources disagree ({', '.join(outcome.sources)}): {outcome.detail}"
        excerpt, probe_tier, level_used = outcome.excerpt, outcome.tier, None
        unobserved = frozenset[str]()
    else:
        verdict, text = outcome.verdict, outcome.evidence
        excerpt, probe_tier, level_used = outcome.excerpt, outcome.tier, outcome.level_used
        unobserved = frozenset(outcome.unobserved)

    tier = weakest(criterion.tier, tier_for_level, probe_tier)

    # Scenarios the check could not judge score as zeros rather than vanishing -- whether the
    # evidence fell short of the level needed, or the subject simply emitted nothing to look at.
    # Withholding is thus exactly as costly as failing, which is the strictest honest treatment: a
    # tool that would have failed gains nothing, and one that would have passed loses by not
    # showing it.
    # Scenarios nothing could judge -- evidence too thin, or the subject emitted nothing to look
    # at. Intersected with the relevant set, because a probe naming ids outside its own relevance
    # drove the count negative and produced a hard fail out of arithmetic.
    unjudged = ({p.scenario.id for p in short} | unobserved) & {p.scenario.id for p in relevant}
    if unjudged:
        judged = len(relevant) - len(unjudged)
        # An OBSERVED failure stands, whatever else was concealed. Otherwise a tool could disarm a
        # violation the check plainly saw by going quiet on a different scenario.
        if verdict != Verdict.FAIL:
            # Everything else becomes NOT MEASURED, contributing zero and blocking nothing.
            #
            # Capping at weak was the third wrong answer here, and the property that generates both
            # sides found it: concealment turned an observed FAIL into a WEAK, so hiding the one
            # scenario you would fail on paid a point. Scaling was the second (it manufactured hard
            # fails out of clean assessments). Zeroing was the first (same manufacture).
            #
            # This is the only treatment that is monotone in both directions: hiding a scenario you
            # would fail scores the same as failing it, hiding one you would pass costs you the
            # whole criterion, and nothing is ever asserted about behaviour nobody watched.
            return CriterionScore(
                criterion_key=criterion.key,
                axis=axis_key,
                verdict=None,
                evidence=(
                    f"{text} [judged only {judged}/{len(relevant)} scenario(s); "
                    f"{', '.join(sorted(unjudged))} produced nothing to judge, so this criterion "
                    f"is not measured -- the gap is the tool's, and it counts as such]"
                ),
                tier=tier,
                excerpt=excerpt,
                unmeasurable_cause=Cause.TOOL.value,
                scenarios_relevant=_ids(relevant),
                scenarios_judged=tuple(sorted({p.scenario.id for p in relevant} - unjudged)),
                scenarios_unjudged=tuple(sorted(unjudged)),
                counts_against_tool=True,
            )
        text = (
            f"{text} [observed on {judged}/{len(relevant)} scenario(s); "
            f"{', '.join(sorted(unjudged))} produced nothing to judge]"
        )

    # Only a DETERMINISTIC check may assert a hard fail. Anything less exact -- a screen, or a
    # criterion declared for human judgement -- caps at weak and says what it cannot see. Written as
    # "not deterministic" rather than "is a screen" because an earlier version capped screens and
    # let MANUAL through, so retiering a fallible check to manual bought an uncapped zero with no
    # caveat. Applied AFTER the shortfall scaling, so the invariant cannot be undone by arithmetic
    # that runs later: scaling a capped screen down to zero would have re-created the hard fail.
    if tier is not ProbeTier.DETERMINISTIC and verdict < Verdict.STRONG:
        verdict = Verdict.WEAK if verdict == Verdict.FAIL else verdict
        caveat = criterion.screen_caveat or "limitation undeclared; treat as unconfirmed"
        text = f"{text} [{tier.value.upper()} - needs human confirmation: {caveat}]"

    return CriterionScore(
        criterion_key=criterion.key,
        axis=axis_key,
        verdict=verdict,
        evidence=text,
        tier=tier,
        excerpt=excerpt,
        level_used=level_used if level_used is not None else min(p.level for p in usable),
        scenarios_relevant=_ids(relevant),
        scenarios_judged=tuple(sorted({p.scenario.id for p in relevant} - unjudged)),
        scenarios_unjudged=tuple(sorted(unjudged)),
        counts_against_tool=bool(unjudged),
    )
