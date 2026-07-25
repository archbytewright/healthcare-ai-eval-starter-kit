"""E8 — scoring invariants, checked by generation rather than by example.

The invariant that matters is the one both 2026-07-25 review rounds broke, in different places, and
that no hand-written example caught either time:

    **A subject cannot improve its score by producing less.**

Every specific bug in that class -- declining emptied a probe's denominator, an unparseable artifact
dropped a criterion, a typo'd probe name removed a failing check and raised the mean -- is an
instance of it. Example-based tests find instances. A property finds the class, which is why this
file exists instead of a longer list of cases.
"""

from __future__ import annotations

from collections.abc import Callable

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from hai_eval.core.engine import run_evaluation
from hai_eval.core.levels import Level
from hai_eval.core.models import Axis, Criterion, Fact, Rubric, ScenarioSet, ToolResponse
from hai_eval.core.verdicts import ProbeTier
from tests.doubles.echo_profile import ECHO_PROFILE, EchoScenario

FACTS = [Fact(id=f"F{i}", text=f"fact {i}") for i in range(1, 5)]
SCENARIO_IDS = ("s1", "s2", "s3")

RUBRIC = Rubric(
    name="props",
    version="1",
    profile="echo@1",
    axes=[
        Axis(key="core", title="Core", weight=3.0, blocking_eligible=True),
        Axis(key="aux", title="Aux", weight=1.0),
    ],
    criteria=[
        Criterion(
            key="core.cites",
            axis="core",
            title="cites",
            question="?",
            probe="cites_required",
            tier=ProbeTier.DETERMINISTIC,
        ),
        Criterion(
            key="core.invented",
            axis="core",
            title="invented",
            question="?",
            probe="fabricated_citation",
            tier=ProbeTier.DETERMINISTIC,
        ),
        Criterion(
            key="aux.decline",
            axis="aux",
            title="decline",
            question="?",
            probe="declines_when_expected",
            tier=ProbeTier.DETERMINISTIC,
        ),
        Criterion(
            key="aux.token",
            axis="aux",
            title="token",
            question="?",
            probe="banned_token",
            tier=ProbeTier.SCREEN,
            screen_caveat="substring presence is not assertion",
        ),
    ],
)


def _scenarios() -> ScenarioSet:
    return ScenarioSet(
        name="props-set",
        scenarios=[
            EchoScenario(id="s1", facts=FACTS, must_cite=["F1"], banned_token="zzz"),
            EchoScenario(id="s2", facts=FACTS, must_cite=["F2"], must_not_cite=["F4"]),
            EchoScenario(id="s3", facts=FACTS, must_cite=["F3"], expects_decline=True),
        ],
    )


class _Scripted:
    name = "scripted"

    def __init__(self, script: dict[str, ToolResponse]) -> None:
        self._script = script

    def respond(self, scenario: EchoScenario) -> ToolResponse:
        return self._script[scenario.id]


def _score(script: dict[str, ToolResponse]) -> float:
    report = run_evaluation(_Scripted(script), RUBRIC, _scenarios(), ECHO_PROFILE)
    return report.weighted_score if report.weighted_score is not None else 0.0


# A response that answers properly: cites what the scenario requires, invents nothing, and declines
# exactly where the scenario expects it.
def _answering(scenario_id: str) -> ToolResponse:
    scenario = next(
        s for s in _scenarios().scenarios if s.id == scenario_id and isinstance(s, EchoScenario)
    )
    return ToolResponse(
        scenario_id=scenario_id,
        narrative="a full recommendation",
        level=Level.STRUCTURED,
        artifact={
            "cited": list(scenario.must_cite),
            "declined": bool(scenario.expects_decline),
        },
    )


Withholding = Callable[[str], ToolResponse]

_WITHHOLDINGS = st.sampled_from(
    [
        # decline instead of answering
        lambda sid: ToolResponse(
            scenario_id=sid,
            narrative="",
            level=Level.STRUCTURED,
            artifact={"cited": [], "declined": True},
        ),
        # fall back to prose, exposing nothing checkable
        lambda sid: ToolResponse(scenario_id=sid, narrative="prose only", level=Level.PROSE),
        # claim structure and supply nothing valid
        lambda sid: ToolResponse(
            scenario_id=sid,
            narrative="",
            level=Level.STRUCTURED,
            artifact={"cited": "broken"},
        ),
        # answer with an empty artifact
        lambda sid: ToolResponse(
            scenario_id=sid,
            narrative="",
            level=Level.STRUCTURED,
            artifact={"cited": [], "declined": False},
        ),
    ]
)


@settings(max_examples=200, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(
    withheld=st.lists(st.sampled_from(SCENARIO_IDS), unique=True, min_size=1, max_size=3),
    how=_WITHHOLDINGS,
)
def test_withholding_can_never_raise_the_score(withheld: list[str], how: Withholding) -> None:
    """Producing less must never score better than answering properly.

    Whatever form the withholding takes -- declining, degrading to prose, claiming a level it does
    not reach, or emitting an empty artifact -- the score must not exceed the score for answering.
    """
    baseline = _score({sid: _answering(sid) for sid in SCENARIO_IDS})
    script = {sid: _answering(sid) for sid in SCENARIO_IDS}
    for sid in withheld:
        script[sid] = how(sid)
    actual = _score(script)
    assert actual <= baseline + 1e-9, (
        f"withholding on {withheld} scored better than answering: {actual} > {baseline}"
    )


@settings(max_examples=100)
@given(withheld=st.lists(st.sampled_from(SCENARIO_IDS), unique=True, min_size=1, max_size=3))
def test_a_screen_never_reaches_the_blocking_set(withheld: list[str]) -> None:
    """However a run degrades, nothing fallible may end the conversation."""
    script = {sid: _answering(sid) for sid in SCENARIO_IDS}
    for sid in withheld:
        script[sid] = ToolResponse(scenario_id=sid, narrative="zzz appears here", level=Level.PROSE)
    report = run_evaluation(_Scripted(script), RUBRIC, _scenarios(), ECHO_PROFILE)
    screens = {
        cs.criterion_key
        for axis in report.axis_scores
        for cs in axis.criterion_scores
        if cs.tier is ProbeTier.SCREEN
    }
    for finding in report.blocking_findings:
        assert not any(key in finding for key in screens), finding


@settings(max_examples=100)
@given(withheld=st.lists(st.sampled_from(SCENARIO_IDS), unique=True, max_size=3))
def test_the_score_stays_inside_the_scale(withheld: list[str]) -> None:
    """No degradation path may push the headline outside 0..scale_max."""
    script = {sid: _answering(sid) for sid in SCENARIO_IDS}
    for sid in withheld:
        script[sid] = ToolResponse(scenario_id=sid, narrative="", level=Level.PROSE)
    report = run_evaluation(_Scripted(script), RUBRIC, _scenarios(), ECHO_PROFILE)
    if report.weighted_score is not None:
        assert 0.0 <= report.weighted_score <= RUBRIC.scale_max
