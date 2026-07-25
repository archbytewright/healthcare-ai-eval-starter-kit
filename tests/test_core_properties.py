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
ANSWERABLE_IDS = ("s1", "s2")
"""Scenarios where an answer is expected.

Withholding is only withholding where something was owed. ``s3`` expects a deferral, so declining
it is the CORRECT answer -- and generating it as a "withholding" made the property fail on a tool
that had simply done the right thing. A property that calls correct behaviour concealment is
measuring the wrong thing.
"""

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
            key="core.token",
            axis="core",
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


def _scenario(scenario_id: str) -> EchoScenario:
    return next(
        s for s in _scenarios().scenarios if s.id == scenario_id and isinstance(s, EchoScenario)
    )


def _answering(scenario_id: str) -> ToolResponse:
    """A response that answers properly and contradicts itself nowhere.

    The first version of this helper declined *while citing*, which the profile flags as a
    self-contradiction -- so the "perfect" baseline actually scored 2.625, and every property was
    quietly comparing degradation against a broken reference.
    """
    scenario = _scenario(scenario_id)
    declining = bool(scenario.expects_decline)
    return ToolResponse(
        scenario_id=scenario_id,
        narrative="a full recommendation",
        level=Level.STRUCTURED,
        artifact={"cited": [] if declining else list(scenario.must_cite), "declined": declining},
    )


def _failing(scenario_id: str) -> ToolResponse:
    """A response that answers BADLY: cites nothing required, invents a fact, never declines.

    The baseline that matters. Comparing withholding against a perfect tool proves only that
    withholding is not better than perfection, which is true of everything. The dangerous direction
    is withholding versus answering badly, because that is the choice a subject with something to
    hide is actually making.
    """
    return ToolResponse(
        scenario_id=scenario_id,
        narrative="zzz a bad recommendation",
        level=Level.STRUCTURED,
        artifact={"cited": ["F99"], "declined": False},
    )


Withholding = Callable[[ToolResponse], ToolResponse]

# A withholding removes AVAILABILITY while leaving behaviour alone. Every one of these keeps the
# tool's own words and takes away only what a check could verify them against. The first version
# rewrote the narrative too, so it was measuring a different tool rather than the same tool being
# less forthcoming -- and duly "failed" on a subject that had simply stopped misbehaving.
_WITHHOLDINGS = st.sampled_from(
    [
        # decline, keeping the same text
        lambda r: r.model_copy(
            update={"artifact": {"cited": [], "declined": True}, "level": Level.STRUCTURED}
        ),
        # fall back to prose: same words, nothing checkable
        lambda r: r.model_copy(update={"level": Level.PROSE, "artifact": None}),
        # claim structure and supply something invalid
        lambda r: r.model_copy(update={"level": Level.STRUCTURED, "artifact": {"cited": "broken"}}),
        # an empty artifact
        lambda r: r.model_copy(
            update={"level": Level.STRUCTURED, "artifact": {"cited": [], "declined": False}}
        ),
    ]
)


@settings(max_examples=300, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(
    withheld=st.lists(st.sampled_from(ANSWERABLE_IDS), unique=True, min_size=1, max_size=2),
    how=_WITHHOLDINGS,
    answers_well=st.booleans(),
)
def test_withholding_can_never_raise_the_score(
    withheld: list[str], how: Withholding, answers_well: bool
) -> None:
    """Producing less must never score better than producing the same behaviour visibly.

    Generated against BOTH baselines. Against a good tool this says withholding costs something;
    against a bad one it says withholding cannot hide anything -- and the second is the property
    with teeth, because concealment is only attractive to a subject that would otherwise fail.
    """
    answer = _answering if answers_well else _failing
    baseline = _score({sid: answer(sid) for sid in SCENARIO_IDS})
    script = {sid: answer(sid) for sid in SCENARIO_IDS}
    for sid in withheld:
        script[sid] = how(script[sid])
    actual = _score(script)
    assert actual <= baseline + 1e-9, (
        f"withholding on {withheld} beat answering "
        f"({'well' if answers_well else 'badly'}): {actual} > {baseline}"
    )


@settings(max_examples=200, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(
    degraded=st.lists(st.sampled_from(ANSWERABLE_IDS), unique=True, min_size=1, max_size=1),
    how=_WITHHOLDINGS,
)
def test_degrading_one_scenario_cannot_erase_a_finding_elsewhere(
    degraded: list[str], how: Withholding
) -> None:
    """A blocking finding on scenario A must survive the tool going quiet on scenario B.

    The defect this pins: trust was resolved once per RUN from its weakest response, so a tool that
    provably violated scope on four scenarios deleted its blocking finding by falling back to prose
    on an unrelated fifth. Whatever is still visible must still count.
    """
    script = {sid: _answering(sid) for sid in SCENARIO_IDS}
    violator = next(sid for sid in SCENARIO_IDS if sid not in degraded)
    script[violator] = ToolResponse(
        scenario_id=violator,
        narrative="cites what it should not",
        level=Level.STRUCTURED,
        artifact={"cited": ["F99"], "declined": False},
    )
    baseline = run_evaluation(_Scripted(script), RUBRIC, _scenarios(), ECHO_PROFILE)
    assert baseline.blocking_findings, "the fixture must produce a finding to begin with"

    for sid in degraded:
        script[sid] = how(script[sid])
    after = run_evaluation(_Scripted(script), RUBRIC, _scenarios(), ECHO_PROFILE)
    assert after.blocking_findings, f"degrading {degraded} erased a finding proved on {violator}"


@settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(samples=st.integers(min_value=1, max_value=4))
def test_a_flaw_in_any_sample_is_a_flaw(samples: int) -> None:
    """Repeated sampling is conservative: one bad draw is a bad tool.

    A subject that behaves three times in four has not behaved. Taking the best draw would let a
    tool buy a verdict with variance, which is the opposite of what sampling is for.
    """

    class Flaky:
        name = "flaky"

        def __init__(self) -> None:
            self.calls = 0

        def respond(self, scenario: EchoScenario) -> ToolResponse:
            self.calls += 1
            if self.calls == 1:  # only the very first draw misbehaves
                return ToolResponse(
                    scenario_id=scenario.id,
                    narrative="fine",
                    level=Level.STRUCTURED,
                    artifact={"cited": ["F99"], "declined": False},
                )
            return _answering(scenario.id)

    report = run_evaluation(Flaky(), RUBRIC, _scenarios(), ECHO_PROFILE, samples=samples)
    assert report.coverage.samples_per_scenario == samples
    assert report.blocking_findings, "an invented citation on one draw is still a finding"


@settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(withheld=st.lists(st.sampled_from(ANSWERABLE_IDS), unique=True, min_size=1, max_size=2))
def test_a_screen_never_reaches_the_blocking_set(withheld: list[str]) -> None:
    """However a run degrades, nothing fallible may end the conversation.

    The blocking-eligible axis carries the fallible check on purpose. The earlier version put the
    only screen on an axis that could not block at all, so the property held no matter what the
    engine did.
    """
    script = {sid: _answering(sid) for sid in SCENARIO_IDS}
    for sid in withheld:
        script[sid] = ToolResponse(scenario_id=sid, narrative="zzz appears here", level=Level.PROSE)
    report = run_evaluation(_Scripted(script), RUBRIC, _scenarios(), ECHO_PROFILE)
    screens = {
        cs.criterion_key
        for axis in report.axis_scores
        for cs in axis.criterion_scores
        if cs.tier is not ProbeTier.DETERMINISTIC
    }
    for finding in report.blocking_findings:
        assert not any(key in finding for key in screens), finding


@settings(max_examples=200, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(
    withheld=st.lists(st.sampled_from(ANSWERABLE_IDS), unique=True, max_size=2),
    answers_well=st.booleans(),
)
def test_the_score_stays_inside_the_scale(withheld: list[str], answers_well: bool) -> None:
    """No degradation path may push the headline outside 0..scale_max."""
    answer = _answering if answers_well else _failing
    script = {sid: answer(sid) for sid in SCENARIO_IDS}
    for sid in withheld:
        script[sid] = ToolResponse(scenario_id=sid, narrative="", level=Level.PROSE)
    report = run_evaluation(_Scripted(script), RUBRIC, _scenarios(), ECHO_PROFILE)
    if report.weighted_score is not None:
        assert 0.0 <= report.weighted_score <= RUBRIC.scale_max
