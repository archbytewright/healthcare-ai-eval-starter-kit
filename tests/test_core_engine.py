"""Engine behaviour, exercised entirely through the test-double profile.

Every test here is a way v0.1 produced a WRONG answer, restated against the new core. If the core
needed anything domain-specific to run these, the seam would have leaked -- so the fact that a
profile with no subject matter can exercise blocking, tier resolution, coverage and every outcome
type is itself the assertion.
"""

from __future__ import annotations

from typing import TypedDict

import pytest

from hai_eval.core.engine import EvaluationError, EvaluationReport, run_evaluation
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
from hai_eval.core.verdicts import ProbeTier, Verdict
from tests.doubles.echo_profile import ECHO_PROFILE, EchoScenario

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
                key="aux.token",
                axis="aux",
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
    score = _cs(report, "aux.token")
    assert score.verdict == Verdict.WEAK, "a screen's hard fail must cap"
    assert "SCREEN" in score.evidence
    assert not any("aux.token" in f for f in report.blocking_findings)


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
    assert _cs(report, "aux.token").verdict is not None, "prose-level checks still run"


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
    """A rubric calling a screen deterministic does not make it one.

    Trust is the minimum of what the rubric declared and what the check can support with the
    evidence in hand, so a rubric edit cannot promote a fallible check into something that blocks.
    """
    rubric = _rubric()
    data = rubric.model_dump()
    for criterion in data["criteria"]:
        if criterion["key"] == "aux.token":
            criterion["tier"] = "deterministic"
            criterion["screen_caveat"] = ""
    script = _good_script()
    script["s1"] = {
        "narrative": "this contains the forbidden word",
        "artifact": {"cited": ["F1"], "declined": False},
    }
    report = run_evaluation(Tool(script), Rubric.model_validate(data), _scenarios(), ECHO_PROFILE)
    score = _cs(report, "aux.token")
    assert score.tier is ProbeTier.SCREEN
    assert not report.blocking_findings


def test_a_disagreement_on_a_fallible_check_still_cannot_block() -> None:
    """The blocking gate must read the TIER, not merely rely on screens having been capped.

    A disagreement is scored as a hard fail, and it is the one path that reaches the gate with a
    FAIL verdict on a screen-tier criterion. Without the tier condition it would block -- which the
    mutation runner proved, by deleting the condition and watching every test stay green.
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
    assert score.verdict == Verdict.FAIL
    assert score.tier is ProbeTier.SCREEN
    assert not report.blocking_findings, "a screen-tier disagreement must not block"


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
    score = _cs(report, "aux.token")
    assert score.verdict is None
    assert score.unmeasurable_cause == "rubric"
    assert not score.counts_against_tool


def test_a_criterion_on_an_undeclared_axis_is_rejected() -> None:
    """A dangling axis reference silently produced a criterion nothing could ever score."""
    data = _rubric().model_dump()
    data["criteria"][0]["axis"] = "nowhere"
    with pytest.raises(ValueError, match="undeclared axes"):
        Rubric.model_validate(data)
