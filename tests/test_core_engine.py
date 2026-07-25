"""Engine behaviour, exercised entirely through the test-double profile.

Every test here is a way v0.1 produced a WRONG answer, restated against the new core. If the core
needed anything domain-specific to run these, the seam would have leaked -- so the fact that a
profile with no subject matter can exercise blocking, tier resolution, coverage and every outcome
type is itself the assertion.
"""

from __future__ import annotations

from typing import ClassVar, TypedDict

import pytest

from hai_eval.core.engine import EvaluationError, EvaluationReport, run_evaluation
from hai_eval.core.evidence import Evidence
from hai_eval.core.levels import Level
from hai_eval.core.models import (
    Axis,
    Criterion,
    CriterionScore,
    Fact,
    Rubric,
    ScenarioSet,
    ToolResponse,
)
from hai_eval.core.outcomes import Assessed, Cause, Unmeasurable
from hai_eval.core.verdicts import ProbeTier, Verdict
from tests.doubles.echo_profile import ECHO_PROFILE, EchoArtifact, EchoScenario

# --------------------------------------------------------------------------------------
# fixtures
# --------------------------------------------------------------------------------------


class Step(TypedDict, total=False):
    """One scripted response. Typed so the fixtures themselves survive the type checker."""

    narrative: str
    level: Level
    artifact: dict[str, object] | None


Script = dict[str, Step]

FACTS = [Fact(id="F1", text="alpha"), Fact(id="F2", text="beta"), Fact(id="F3", text="gamma")]


def _scenarios() -> ScenarioSet:
    return ScenarioSet(
        name="double-set",
        scenarios=[
            EchoScenario(id="s1", facts=FACTS, must_cite=["F1"], banned_token="forbidden"),
            EchoScenario(id="s2", facts=FACTS, must_cite=["F2"], must_not_cite=["F3"]),
            EchoScenario(id="s3", facts=FACTS, expects_decline=True),
        ],
    )


def _rubric(**overrides: object) -> Rubric:
    data: dict[str, object] = {
        "name": "double-rubric",
        "version": "1",
        "profile": "echo@1",
        "axes": [
            Axis(key="core", title="Core", weight=3.0, blocking_eligible=True),
            Axis(key="aux", title="Aux", weight=1.0),
        ],
        "criteria": [
            Criterion(
                key="core.cites",
                axis="core",
                title="Cites what it relied on",
                question="?",
                probe="cites_required",
                tier=ProbeTier.DETERMINISTIC,
            ),
            Criterion(
                key="core.scope",
                axis="core",
                title="Leaves out-of-scope alone",
                question="?",
                probe="no_out_of_scope_citation",
                tier=ProbeTier.DETERMINISTIC,
            ),
            Criterion(
                key="core.invented",
                axis="core",
                title="Invents nothing",
                question="?",
                probe="fabricated_citation",
                tier=ProbeTier.DETERMINISTIC,
            ),
            Criterion(
                key="core.token",
                axis="core",
                title="Avoids a banned string",
                question="?",
                probe="banned_token",
                tier=ProbeTier.SCREEN,
                screen_caveat="a substring match cannot tell assertion from mention",
            ),
            Criterion(
                key="aux.decline",
                axis="aux",
                title="Declines when it should",
                question="?",
                probe="declines_when_expected",
                tier=ProbeTier.DETERMINISTIC,
            ),
        ],
    }
    data.update(overrides)
    return Rubric.model_validate(data)


class Tool:
    """A scripted tool. What it reports about itself is derived by the engine, not asserted."""

    def __init__(self, script: Script, *, name: str = "double") -> None:
        self._script = script
        self.name = name

    def respond(self, scenario: EchoScenario) -> ToolResponse:
        spec: Step = self._script.get(scenario.id, {})
        return ToolResponse(
            scenario_id=scenario.id,
            narrative=spec.get("narrative", "a recommendation"),
            level=spec.get("level", Level.STRUCTURED),
            artifact=spec.get("artifact", {"cited": list(scenario.must_cite), "declined": False}),
        )


def _good_script() -> Script:
    return {
        "s1": {"artifact": {"cited": ["F1"], "declined": False}},
        "s2": {"artifact": {"cited": ["F2"], "declined": False}},
        "s3": {"artifact": {"cited": [], "declined": True}, "narrative": "Declining: too little."},
    }


def _run(script: Script, rubric: Rubric | None = None) -> EvaluationReport:
    return run_evaluation(Tool(script), rubric or _rubric(), _scenarios(), ECHO_PROFILE)


def _cs(report: EvaluationReport, key: str) -> CriterionScore:
    return next(
        cs for axis in report.axis_scores for cs in axis.criterion_scores if cs.criterion_key == key
    )


# --------------------------------------------------------------------------------------
# the seam
# --------------------------------------------------------------------------------------


def test_a_domainless_profile_can_drive_the_whole_engine() -> None:
    """The seam assertion: no clinical anything is needed to reach a full report."""
    report = _run(_good_script())
    assert report.weighted_score == pytest.approx(3.0)
    assert not report.blocking_findings
    assert report.profile_ref == "echo@1"
    assert report.coverage.criteria_scored == 5


def test_rubric_targeting_another_profile_is_refused() -> None:
    with pytest.raises(EvaluationError, match="targets profile"):
        run_evaluation(Tool({}), _rubric(profile="other@9"), _scenarios(), ECHO_PROFILE)


# --------------------------------------------------------------------------------------
# what may block
# --------------------------------------------------------------------------------------


def test_deterministic_failure_on_an_eligible_axis_blocks() -> None:
    script = _good_script()
    script["s2"] = {"artifact": {"cited": ["F2", "F3"], "declined": False}}  # cites out-of-scope
    report = _run(script)
    assert any("core.scope" in f for f in report.blocking_findings)
    assert _cs(report, "core.scope").verdict == Verdict.FAIL


def test_a_screen_can_never_block_however_badly_it_fails() -> None:
    script = _good_script()
    script["s1"] = {
        "narrative": "this contains the forbidden word",
        "artifact": {"cited": ["F1"], "declined": False},
    }
    report = _run(script)
    score = _cs(report, "core.token")
    assert score.verdict == Verdict.WEAK, "a screen's hard fail must cap"
    assert "SCREEN" in score.evidence
    assert not any("core.token" in f for f in report.blocking_findings)


def test_an_axis_not_marked_eligible_cannot_block() -> None:
    rubric = _rubric()
    rubric = Rubric.model_validate(
        {
            **rubric.model_dump(),
            "axes": [{**a.model_dump(), "blocking_eligible": False} for a in rubric.axes],
        }
    )
    script = _good_script()
    script["s2"] = {"artifact": {"cited": ["F2", "F3"], "declined": False}}
    report = run_evaluation(Tool(script), rubric, _scenarios(), ECHO_PROFILE)
    assert _cs(report, "core.scope").verdict == Verdict.FAIL
    assert not report.blocking_findings


# --------------------------------------------------------------------------------------
# capability levels
# --------------------------------------------------------------------------------------


def test_a_prose_only_tool_reports_what_it_could_not_prove() -> None:
    """No silent exclusion: a check that needed more says so, and it counts against the tool."""
    script: Script = {sid: Step(level=Level.PROSE, artifact=None) for sid in ("s1", "s2", "s3")}
    report = _run(script)
    score = _cs(report, "core.cites")
    assert score.verdict is None
    assert score.counts_against_tool
    assert "structured" in score.evidence and "prose" in score.evidence
    assert _cs(report, "core.token").verdict is not None, "prose-level checks still run"


def test_a_claimed_level_is_verified_not_trusted() -> None:
    """An adapter claiming more than it delivers is an INTEGRATION finding, not a quiet demotion."""
    script = _good_script()
    script["s1"] = {"level": Level.STRUCTURED, "artifact": {"cited": "not-a-list"}}
    report = _run(script)
    assert "integration faults" in report.provenance
    assert "s1" in report.provenance["integration faults"]
    assert ("s1", "prose") in report.coverage.levels_reached


def test_level_is_per_response_so_partial_degradation_is_visible() -> None:
    script = _good_script()
    script["s2"] = {"level": Level.PROSE, "artifact": None}
    report = _run(script)
    reached = dict(report.coverage.levels_reached)
    assert reached == {"s1": "structured", "s2": "prose", "s3": "structured"}


# --------------------------------------------------------------------------------------
# the scoring rule
# --------------------------------------------------------------------------------------


def test_declining_everything_cannot_produce_a_good_score() -> None:
    """The worst v0.1 finding: answering nothing scored a perfect 3.0 and read as a pilot candidate.

    Each emptied probe dropped out of the mean, so refusing to answer removed checks instead of
    failing them.
    """
    script: Script = {
        sid: Step(artifact={"cited": [], "declined": True}, narrative="Declining.")
        for sid in ("s1", "s2", "s3")
    }
    report = _run(script)
    assert report.weighted_score is not None
    assert report.weighted_score < 2.0, report.weighted_score
    assert _cs(report, "aux.decline").verdict == Verdict.FAIL


def test_a_rubric_side_gap_does_not_count_against_the_tool() -> None:
    """A criterion no probe implements says nothing about the subject and must not score it."""
    rubric = _rubric()
    data = rubric.model_dump()
    data["criteria"].append(
        {
            "key": "aux.manual",
            "axis": "aux",
            "title": "Needs a human",
            "question": "?",
            "probe": "manual_review",
            "tier": "manual",
        }
    )
    report = run_evaluation(
        Tool(_good_script()), Rubric.model_validate(data), _scenarios(), ECHO_PROFILE
    )
    score = _cs(report, "aux.manual")
    assert score.verdict is None
    assert not score.counts_against_tool
    assert score.unmeasurable_cause == "rubric"
    assert report.weighted_score == pytest.approx(3.0), (
        "an unautomatable criterion must not lower it"
    )


def test_disagreement_between_sources_is_scored_not_annotated() -> None:
    """Detection without consequence is a log line. A contradiction is a finding."""
    script = _good_script()
    script["s3"] = {
        "artifact": {"cited": ["F1"], "declined": True},
        "narrative": "Recommend proceeding with the usual approach.",
    }
    report = _run(script)
    score = _cs(report, "aux.decline")
    assert score.verdict == Verdict.FAIL
    assert "sources disagree" in score.evidence


# --------------------------------------------------------------------------------------
# input integrity
# --------------------------------------------------------------------------------------


def test_responses_must_correspond_to_the_scenarios() -> None:
    class Ghost:
        name = "ghost"

        def respond(self, scenario: EchoScenario) -> ToolResponse:
            return ToolResponse(scenario_id="s1", narrative="x", level=Level.PROSE)

    with pytest.raises(EvaluationError, match="do not correspond"):
        run_evaluation(Ghost(), _rubric(), _scenarios(), ECHO_PROFILE)


def test_duplicate_scenario_ids_are_rejected() -> None:
    with pytest.raises(ValueError, match="duplicate scenario id"):
        ScenarioSet(
            name="dupes",
            scenarios=[EchoScenario(id="s1", facts=FACTS), EchoScenario(id="s1", facts=FACTS)],
        )


def test_duplicate_fact_ids_are_rejected() -> None:
    with pytest.raises(ValueError, match="repeats fact id"):
        EchoScenario(id="s9", facts=[Fact(id="F1", text="a"), Fact(id="F1", text="b")])


def test_a_screen_without_a_caveat_is_rejected() -> None:
    with pytest.raises(ValueError, match="screen_caveat"):
        Criterion(key="a.b", axis="a", title="t", question="?", probe="p", tier=ProbeTier.SCREEN)


def test_probe_tier_cannot_exceed_what_the_level_supports() -> None:
    """A rubric calling a check deterministic does not make it one.

    Trust is the minimum of what the rubric declared and what the check can support with the
    evidence in hand. The same check IS deterministic given a structured artifact -- that is what
    the level lattice is for -- so this pins the direction that matters: over prose alone, the
    rubric's declaration cannot promote it.
    """
    rubric = _rubric()
    data = rubric.model_dump()
    for criterion in data["criteria"]:
        if criterion["key"] == "core.token":
            criterion["tier"] = "deterministic"
            criterion["screen_caveat"] = ""
    script: Script = {
        "s1": Step(level=Level.PROSE, narrative="this contains the forbidden word", artifact=None),
        "s2": Step(level=Level.PROSE, artifact=None),
        "s3": Step(level=Level.PROSE, artifact=None),
    }
    report = run_evaluation(Tool(script), Rubric.model_validate(data), _scenarios(), ECHO_PROFILE)
    score = _cs(report, "core.token")
    assert score.tier is ProbeTier.SCREEN, "prose evidence supports only a screen"
    assert score.verdict == Verdict.WEAK
    assert not report.blocking_findings


def test_a_disagreement_on_a_fallible_check_still_cannot_block() -> None:
    """A contradiction is a hard fail, and it caps and carries a caveat like everything else.

    Returning ``Disagreement`` used to be a way around the cap entirely: a criterion the rubric had
    declared fallible produced an uncapped zero with no caveat, purely by choosing a different
    outcome type, in the same function whose comment claimed the cap lived in one place.
    """
    rubric = _rubric()
    data = rubric.model_dump()
    for criterion in data["criteria"]:
        if criterion["key"] == "aux.decline":
            criterion["tier"] = "screen"
            criterion["screen_caveat"] = "internal consistency is not behaviour"
        if criterion["key"] == "core.cites":
            criterion["axis"] = "aux"  # move the deterministic checks off the blocking axis
        if criterion["key"] in {"core.scope", "core.invented"}:
            criterion["axis"] = "aux"
    data["axes"] = [{**a, "blocking_eligible": a["key"] == "aux"} for a in data["axes"]]
    script = _good_script()
    script["s3"] = {"artifact": {"cited": ["F1"], "declined": True}, "narrative": "x"}
    report = run_evaluation(Tool(script), Rubric.model_validate(data), _scenarios(), ECHO_PROFILE)
    score = _cs(report, "aux.decline")
    assert score.tier is ProbeTier.SCREEN
    assert score.verdict == Verdict.WEAK, "a fallible contradiction caps like any other finding"
    assert "needs human confirmation" in score.evidence, "and carries the caveat"
    assert not report.blocking_findings


def test_a_probe_reporting_a_rubric_side_gap_does_not_punish_the_tool() -> None:
    """A probe can also declare a gap to be the rubric's, and that must not be scored either.

    Distinct from a missing probe: here the check RAN, looked at the scenarios, and reported that
    the rubric asked something these scenarios cannot answer.
    """
    scenarios = ScenarioSet(
        name="no-token-set",
        scenarios=[EchoScenario(id="s1", facts=FACTS, must_cite=["F1"])],
    )
    script: Script = {"s1": {"artifact": {"cited": ["F1"], "declined": False}}}
    report = run_evaluation(Tool(script), _rubric(), scenarios, ECHO_PROFILE)
    score = _cs(report, "core.token")
    assert score.verdict is None
    assert score.unmeasurable_cause == "rubric"
    assert not score.counts_against_tool


def test_a_criterion_on_an_undeclared_axis_is_rejected() -> None:
    """A dangling axis reference silently produced a criterion nothing could ever score."""
    data = _rubric().model_dump()
    data["criteria"][0]["axis"] = "nowhere"
    with pytest.raises(ValueError, match="undeclared axes"):
        Rubric.model_validate(data)


# ---------------------------------------------------------------------------
# Regression guards from the P1 review gate (2026-07-25)
# ---------------------------------------------------------------------------


def test_degrading_one_scenario_leaves_findings_on_the_others_intact() -> None:
    """The gate's worst finding: trust was resolved once per RUN from its weakest response.

    A tool that provably cited an out-of-scope fact scored 2.25 with a blocking finding, and deleted
    that finding by falling back to prose on an unrelated scenario -- the evidence still sitting in
    the report. Level is now resolved per criterion, over the scenarios that check applies to.
    """
    violating: Script = {
        "s1": Step(artifact={"cited": ["F1"], "declined": False}),
        "s2": Step(artifact={"cited": ["F2", "F3"], "declined": False}),
        "s3": Step(artifact={"cited": [], "declined": True}),
    }
    before = _run(violating)
    assert any("core.scope" in f for f in before.blocking_findings)

    degraded = dict(violating)
    degraded["s1"] = Step(level=Level.PROSE, artifact=None)
    after = _run(degraded)
    assert any("core.scope" in f for f in after.blocking_findings), (
        "a finding proved on s2 must survive s1 going quiet"
    )


def test_a_mistyped_probe_name_is_refused_not_silently_dropped() -> None:
    """A one-character typo used to raise a failing tool to 3.0 and delete its blocking finding.

    The criterion became "the rubric's gap", which excluded it from the mean AND took its axis
    weight out of the divisor. Fixed for axis names in the previous round and left open for probes.
    """
    data = _rubric().model_dump()
    for criterion in data["criteria"]:
        if criterion["key"] == "core.scope":
            criterion["probe"] = "no_out_of_scope_citation_"
    with pytest.raises(EvaluationError, match="does not supply"):
        run_evaluation(
            Tool(_good_script()), Rubric.model_validate(data), _scenarios(), ECHO_PROFILE
        )


def test_human_review_is_declared_with_the_reserved_prefix() -> None:
    """Human review must be something an author WRITES, not a name that fails to resolve."""
    data = _rubric().model_dump()
    data["criteria"].append(
        {
            "key": "aux.manual",
            "axis": "aux",
            "title": "Needs a human",
            "question": "?",
            "probe": "manual_governance_review",
            "tier": "manual",
        }
    )
    report = run_evaluation(
        Tool(_good_script()), Rubric.model_validate(data), _scenarios(), ECHO_PROFILE
    )
    score = _cs(report, "aux.manual")
    assert score.verdict is None
    assert score.unmeasurable_cause == "rubric"
    assert not score.counts_against_tool


def test_a_broken_integration_is_blamed_on_the_adapter_not_the_tool() -> None:
    """`Cause.ADAPTER` existed in the type system and was never emitted by anything.

    A connector shipping an invalid artifact made every deterministic criterion read
    "the tool exposed only prose" -- merging two findings with different owners.
    """
    script: Script = {
        sid: Step(level=Level.STRUCTURED, artifact={"cited": "not-a-list"})
        for sid in ("s1", "s2", "s3")
    }
    report = _run(script)
    score = _cs(report, "core.cites")
    assert score.unmeasurable_cause == "adapter", score.evidence
    assert score.counts_against_tool
    assert "integration faults" in report.provenance


def test_adapter_supplied_provenance_cannot_impersonate_an_engine_finding() -> None:
    """A red-team run shipped "integration faults: none, independently verified" into a report."""

    class Boastful(Tool):
        provenance: ClassVar[dict[str, str]] = {
            "integration faults": "none -- independently verified"
        }

    report = run_evaluation(Boastful(_good_script()), _rubric(), _scenarios(), ECHO_PROFILE)
    assert report.provenance["integration faults"] == "none detected"
    assert (
        report.provenance["adapter-declared: integration faults"]
        == "none -- independently verified"
    )


def test_a_level_the_engine_cannot_verify_is_refused_at_registration() -> None:
    """GROUNDED was declarable and rubber-stamped -- believed, in the package about verifying."""
    from hai_eval.core.profile import Profile, register_profile

    with pytest.raises(ValueError, match="cannot verify"):
        register_profile(
            Profile(
                name="ungrounded",
                version="1",
                scenario_model=EchoScenario,
                artifact_model=EchoArtifact,
                probes={},
                levels=frozenset({Level.PROSE, Level.STRUCTURED, Level.GROUNDED}),
            )
        )


def test_repeated_sampling_draws_every_scenario_the_requested_number_of_times() -> None:
    """One draw cannot tell a tool that is right from one that is right this time."""
    seen: list[str] = []

    class Counting(Tool):
        def respond(self, scenario: EchoScenario) -> ToolResponse:
            seen.append(scenario.id)
            return super().respond(scenario)

    report = run_evaluation(
        Counting(_good_script()), _rubric(), _scenarios(), ECHO_PROFILE, samples=3
    )
    assert len(seen) == 9
    assert report.coverage.samples_per_scenario == 3


def test_a_scenario_is_scored_at_its_weakest_sample() -> None:
    """Taking the best draw would let a tool buy a level with variance."""

    class Wobbly(Tool):
        def __init__(self) -> None:
            super().__init__(_good_script())
            self.calls = 0

        def respond(self, scenario: EchoScenario) -> ToolResponse:
            self.calls += 1
            if self.calls % 2 == 0:
                return ToolResponse(scenario_id=scenario.id, narrative="x", level=Level.PROSE)
            return super().respond(scenario)

    report = run_evaluation(Wobbly(), _rubric(), _scenarios(), ECHO_PROFILE, samples=2)
    assert {lvl for _, lvl in report.coverage.levels_reached} == {"prose"}


def test_unjudged_scenarios_pull_the_verdict_down_proportionally() -> None:
    """A scenario nothing could judge scores zero; it does not quietly leave the denominator."""
    script: Script = {
        "s1": Step(artifact={"cited": ["F1"], "declined": False}),
        "s2": Step(level=Level.PROSE, artifact=None),
        "s3": Step(artifact={"cited": [], "declined": True}),
    }
    score = _cs(_run(script), "core.invented")
    assert score.verdict == Verdict.ADEQUATE, score.evidence
    assert "count as zero" in score.evidence
    assert score.counts_against_tool


def test_when_nothing_is_judgeable_the_criterion_is_unmeasurable_not_failed() -> None:
    """Saying "fail" over an empty observation asserts something about behaviour nobody saw."""
    script: Script = {sid: Step(level=Level.PROSE, artifact=None) for sid in ("s1", "s2", "s3")}
    score = _cs(_run(script), "core.cites")
    assert score.verdict is None
    assert score.counts_against_tool
    assert score.unmeasurable_cause == "tool"


def test_a_tool_caused_absence_lowers_the_axis_mean() -> None:
    """The absence must reach the NUMBER, not only the criterion row.

    Excluding it was the original bug: a criterion the tool prevented from running left the mean
    entirely, so refusing to answer removed the check instead of failing it.
    """
    answered = _run(_good_script())
    withheld: Script = {sid: Step(level=Level.PROSE, artifact=None) for sid in ("s1", "s2", "s3")}
    assert answered.weighted_score is not None
    silent = _run(withheld).weighted_score
    assert silent is not None and silent < answered.weighted_score


def test_relevance_keeps_an_irrelevant_scenario_from_penalising_a_check() -> None:
    """A check is scored over the scenarios that exercise it, not over the whole set.

    Without a relevance predicate, degrading a scenario a check never looks at would still drag its
    verdict down -- and the check would be reporting on evidence it had no interest in.
    """
    script: Script = {
        "s1": Step(level=Level.PROSE, artifact=None),  # carries no must_not_cite annotation
        "s2": Step(artifact={"cited": ["F2"], "declined": False}),
        "s3": Step(artifact={"cited": [], "declined": True}),
    }
    score = _cs(_run(script), "core.scope")
    assert score.verdict == Verdict.STRONG, score.evidence
    assert not score.counts_against_tool


def test_a_probe_may_not_declare_an_empty_claim_table() -> None:
    """A check that speaks at no level cannot be reasoned about at all."""
    from hai_eval.core.profile import ProbeSpec

    with pytest.raises(ValueError, match="at least one level"):
        ProbeSpec(lambda _c, _e: Assessed(Verdict.STRONG, "x"), {})


def test_a_manual_tier_probe_is_capped_and_caveated_like_a_screen() -> None:
    """Retiering a fallible check to `manual` used to buy an uncapped zero with no caveat."""
    data = _rubric().model_dump()
    for criterion in data["criteria"]:
        if criterion["key"] == "core.token":
            criterion["tier"] = "manual"
            criterion["screen_caveat"] = "a human must read the output"
    script = _good_script()
    script["s1"] = Step(
        narrative="this contains the forbidden word", artifact={"cited": ["F1"], "declined": False}
    )
    report = run_evaluation(Tool(script), Rubric.model_validate(data), _scenarios(), ECHO_PROFILE)
    score = _cs(report, "core.token")
    assert score.tier is ProbeTier.MANUAL
    assert score.verdict == Verdict.WEAK
    assert "needs human confirmation" in score.evidence
    assert not report.blocking_findings


def test_a_gap_a_probe_discovers_from_inside_is_still_the_rubrics() -> None:
    """A check can look, find the question unanswerable, and say so -- without blaming the subject.

    Distinct from the engine's relevance filter, which can only see whether a scenario carries an
    annotation. Some gaps are only visible once a check has looked: needing two scenarios to compare
    and finding one, for instance. The mutation runner caught that no test reached this path.
    """
    from hai_eval.core.levels import Level as _Level
    from hai_eval.core.profile import ProbeSpec, Profile, register_profile

    def _needs_two(_criterion: Criterion, evidence: Evidence[EchoArtifact]) -> Unmeasurable:
        return Unmeasurable(
            f"comparing consistency needs two scenarios; the set has {len(evidence.pairs)}",
            Cause.RUBRIC,
        )

    profile = register_profile(
        Profile(
            name="one-question",
            version="1",
            scenario_model=EchoScenario,
            artifact_model=EchoArtifact,
            probes={"needs_two": ProbeSpec(_needs_two, {_Level.PROSE: ProbeTier.DETERMINISTIC})},
            levels=frozenset({_Level.PROSE, _Level.STRUCTURED}),
        )
    )
    rubric = Rubric(
        name="thin",
        version="1",
        profile="one-question@1",
        axes=[Axis(key="core", title="Core", weight=1.0, blocking_eligible=True)],
        criteria=[
            Criterion(
                key="core.consistency",
                axis="core",
                title="consistency",
                question="?",
                probe="needs_two",
                tier=ProbeTier.DETERMINISTIC,
            )
        ],
    )
    report = run_evaluation(Tool(_good_script()), rubric, _scenarios(), profile)
    score = _cs(report, "core.consistency")
    assert score.verdict is None
    assert score.unmeasurable_cause == "rubric"
    assert not score.counts_against_tool, "the set asked a question it could not support"
    assert report.weighted_score is None, (
        "an unautomatable criterion leaves the score, not zeroes it"
    )
