"""Run a tool over a scenario set and score what came back.

The engine owns four things a probe must not: verifying a claimed capability level, resolving how
far a finding can be trusted, deciding what may block, and deciding how an absence affects the
score. Each of those was a place where v0.1 trusted something it should have been measuring.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Protocol

from loguru import logger
from pydantic import BaseModel, ValidationError

from hai_eval.core.evidence import Evidence, Pair
from hai_eval.core.levels import Level
from hai_eval.core.models import CriterionScore, Rubric, ToolResponse
from hai_eval.core.outcomes import Cause, Disagreement, Unmeasurable
from hai_eval.core.profile import Profile, weakest
from hai_eval.core.verdicts import ProbeTier, Verdict

if TYPE_CHECKING:
    from hai_eval.core.models import Criterion, ScenarioSet


class EvaluationError(RuntimeError):
    """The harness cannot score this run, and will not guess."""


class ToolUnderTest[S](Protocol):
    """One method, plus a name. Everything a tool reports about itself is derived, not asserted.

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
) -> EvaluationReport:
    """Run ``tool`` over the scenarios and score it against ``rubric``.

    Raises:
        EvaluationError: if the rubric targets another profile, or the responses do not correspond
            one-to-one with the scenarios.
    """
    if rubric.profile != profile.ref:
        msg = f"rubric targets profile {rubric.profile!r} but {profile.ref!r} was supplied"
        raise EvaluationError(msg)

    logger.info(
        "evaluating tool={} rubric={}@{} profile={} scenarios={}",
        tool.name,
        rubric.name,
        rubric.version,
        profile.ref,
        len(scenario_set.scenarios),
    )
    responses = tuple(tool.respond(s) for s in scenario_set.scenarios)

    # An adapter returning the wrong scenario id used to shrink the run silently: the join dropped
    # unmatched cases, every emptied probe blamed the DATA for the adapter's bug, and
    # the thinned run scored full marks. Refuse instead.
    want = sorted(s.id for s in scenario_set.scenarios)
    got = sorted(r.scenario_id for r in responses)
    if want != got:
        missing = sorted(set(want) - set(got))
        unexpected = sorted(set(got) - set(want))
        msg = (
            f"responses do not correspond to the scenario set: "
            f"{len(responses)} response(s) for {len(want)} scenario(s)"
        )
        if missing:
            msg += f"; nothing for {missing}"
        if unexpected:
            msg += f"; unknown scenario_id {unexpected}"
        if len(set(got)) != len(got):
            msg += "; duplicate scenario_id in responses"
        raise EvaluationError(msg)

    by_id = {r.scenario_id: r for r in responses}
    pairs: list[Pair[Any]] = []
    integration_faults: list[str] = []
    for scenario in scenario_set.scenarios:
        response = by_id[scenario.id]
        level, artifact, fault = _verify_level(response, profile)
        if fault:
            integration_faults.append(f"{scenario.id}: {fault}")
        pairs.append(
            Pair(
                scenario=scenario,
                response=response.model_copy(update={"level": level}),
                artifact=artifact,
            )
        )
    evidence = Evidence(pairs=tuple(pairs))

    axis_scores: list[AxisScore] = []
    blocking: list[str] = []
    scored_criteria = 0
    total_criteria = 0
    scored_weight = 0.0

    for axis in rubric.axes:
        criterion_scores: list[CriterionScore] = []
        for criterion in rubric.criteria_for(axis.key):
            total_criteria += 1
            score = _score_one(criterion, axis_key=axis.key, evidence=evidence, profile=profile)
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
        levels_reached=tuple((p.scenario.id, p.level.label) for p in pairs),
    )
    provenance = dict(getattr(tool, "provenance", {}) or {})
    if integration_faults:
        provenance["integration faults"] = "; ".join(integration_faults)

    return EvaluationReport(
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


def _score_one(
    criterion: Criterion, *, axis_key: str, evidence: Evidence[Any], profile: Profile
) -> CriterionScore:
    """Resolve one criterion to a score, including the ways it can fail to resolve."""
    spec = profile.probes.get(criterion.probe)
    if spec is None:
        return CriterionScore(
            criterion_key=criterion.key,
            axis=axis_key,
            verdict=None,
            evidence=f"no probe {criterion.probe!r} in profile {profile.ref}",
            tier=ProbeTier.MANUAL,
            unmeasurable_cause=Cause.RUBRIC.value,
        )

    available = min((p.level for p in evidence.pairs), default=Level.PROSE)
    tier_for_level = spec.tier_at(available)
    if tier_for_level is None:
        short = evidence.scenarios_below(spec.minimum_level)
        return CriterionScore(
            criterion_key=criterion.key,
            axis=axis_key,
            verdict=None,
            evidence=(
                f"needs '{spec.minimum_level.label}' evidence; the tool reached "
                f"'{available.label}'" + (f" (short on {', '.join(short)})" if short else "")
            ),
            tier=criterion.tier,
            unmeasurable_cause=Cause.TOOL.value,
            counts_against_tool=True,
        )

    outcome = spec.fn(criterion, evidence)

    if isinstance(outcome, Unmeasurable):
        return CriterionScore(
            criterion_key=criterion.key,
            axis=axis_key,
            verdict=None,
            evidence=outcome.reason,
            tier=criterion.tier,
            unmeasurable_cause=outcome.cause.value,
            counts_against_tool=outcome.cause in (Cause.TOOL, Cause.ADAPTER),
        )

    if isinstance(outcome, Disagreement):
        # A contradiction between sources is a finding in its own right, scored as a hard fail so it
        # cannot be a warning glyph nobody acts on. Its tier is whatever the check supports.
        return CriterionScore(
            criterion_key=criterion.key,
            axis=axis_key,
            verdict=Verdict.FAIL,
            evidence=f"sources disagree ({', '.join(outcome.sources)}): {outcome.detail}",
            tier=weakest(criterion.tier, tier_for_level),
            excerpt=outcome.excerpt,
            level_used=available,
        )

    tier = weakest(criterion.tier, tier_for_level, outcome.tier)
    verdict = outcome.verdict
    text = outcome.evidence

    # A screen cannot produce a hard fail: it sees that something appeared in free text, not what
    # the tool did with it, so the worst it may say alone is "weak -- look at this". Capped in ONE
    # place so no probe author can opt out. Every screen that raises a concern carries its caveat,
    # not only the capped ones: a screen sitting at weak on its own is exactly as fallible.
    if tier is ProbeTier.SCREEN and verdict < Verdict.STRONG:
        verdict = Verdict.WEAK if verdict == Verdict.FAIL else verdict
        caveat = criterion.screen_caveat or "limitation undeclared; treat as unconfirmed"
        text = f"{text} [SCREEN - needs human confirmation: {caveat}]"

    return CriterionScore(
        criterion_key=criterion.key,
        axis=axis_key,
        verdict=verdict,
        evidence=text,
        tier=tier,
        excerpt=outcome.excerpt,
        level_used=outcome.level_used or available,
    )
