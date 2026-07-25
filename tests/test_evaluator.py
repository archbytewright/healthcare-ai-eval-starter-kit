"""Differential tests for the probes and the end-to-end evaluation.

The discriminating principle: a probe is only useful if a *better* tool scores
*better* on it. Each test below pairs the failing mock tool against a minimal
"fixed" tool that repairs exactly one failure mode, and asserts the relevant
verdict improves while unrelated verdicts do not. Field-echo assertions are
avoided in favor of behavior-difference assertions.
"""

from __future__ import annotations

from hai_eval.evaluator import registered_probes, run_evaluation
from hai_eval.models import (
    CriterionScore,
    EvaluationReport,
    ProbeTier,
    Rubric,
    ToolOutput,
    Verdict,
    Vignette,
    VignetteSet,
)
from hai_eval.tool import DeterministicMockModel, MockDecisionSupportTool


def _cs(report: EvaluationReport, criterion_key: str) -> CriterionScore:
    for axis in report.axis_scores:
        for cs in axis.criterion_scores:
            if cs.criterion_key == criterion_key:
                return cs
    msg = f"criterion {criterion_key} not in report"
    raise AssertionError(msg)


def _score_for(report: EvaluationReport, criterion_key: str) -> Verdict:
    for axis in report.axis_scores:
        for cs in axis.criterion_scores:
            if cs.criterion_key == criterion_key:
                return cs.verdict
    msg = f"criterion {criterion_key} not in report"
    raise AssertionError(msg)


class _PerfectTool:
    """A tool that retains everything, never injects, and abstains on injection cases."""

    name = "PerfectTool"

    def assess(self, vignette: Vignette) -> ToolOutput:
        if vignette.injection:
            return ToolOutput(vignette_id=vignette.id, text="ABSTAIN", abstained=True)
        # Echo the required facts back so retention is perfect; never emit forbidden.
        text = " ".join(vignette.must_include)
        return ToolOutput(vignette_id=vignette.id, text=text)


class _LeakyTool:
    """A tool that fabricates a forbidden fact, to exercise the no_fabrication probe."""

    name = "LeakyTool"

    def assess(self, vignette: Vignette) -> ToolOutput:
        text = " ".join(vignette.must_include)
        if vignette.must_not_include:
            text = f"{text} {vignette.must_not_include[0]}"
        return ToolOutput(vignette_id=vignette.id, text=text)


def test_registered_probes_cover_harness_criteria(rubric: Rubric) -> None:
    """Every non-manual criterion in the shipped rubric has a registered probe."""
    probes = registered_probes()
    for criterion in rubric.criteria:
        if criterion.probe.startswith("manual_"):
            continue
        assert criterion.probe in probes, f"unregistered probe {criterion.probe}"


def test_manual_criteria_report_not_assessed(
    rubric: Rubric, vignettes: VignetteSet, mock_tool: MockDecisionSupportTool
) -> None:
    """Manual criteria are reported as not-assessed -- never a silent pass."""
    report = run_evaluation(mock_tool, rubric, vignettes)
    assert _score_for(report, "workflow.fits_clinical_flow") == Verdict.NOT_ASSESSED
    assert _score_for(report, "oversight.monitoring_plan") == Verdict.NOT_ASSESSED


def test_injection_probe_discriminates(rubric: Rubric, vignettes: VignetteSet) -> None:
    """The failing tool fails injection-resistance; the perfect tool passes it."""
    bad = run_evaluation(MockDecisionSupportTool(DeterministicMockModel()), rubric, vignettes)
    good = run_evaluation(_PerfectTool(), rubric, vignettes)
    assert _score_for(bad, "safety.injection_resistance") == Verdict.FAIL
    assert _score_for(good, "safety.injection_resistance") == Verdict.STRONG


def test_retention_probe_discriminates(rubric: Rubric, vignettes: VignetteSet) -> None:
    """The contraindication-dropping tool scores below the fact-retaining tool."""
    bad = run_evaluation(MockDecisionSupportTool(DeterministicMockModel()), rubric, vignettes)
    good = run_evaluation(_PerfectTool(), rubric, vignettes)
    assert _score_for(bad, "safety.retains_critical_facts") < Verdict.STRONG
    assert _score_for(good, "safety.retains_critical_facts") == Verdict.STRONG


def test_abstention_probe_discriminates(rubric: Rubric, vignettes: VignetteSet) -> None:
    """The never-abstaining tool is weak; the abstaining tool is strong."""
    bad = run_evaluation(MockDecisionSupportTool(DeterministicMockModel()), rubric, vignettes)
    good = run_evaluation(_PerfectTool(), rubric, vignettes)
    assert _score_for(bad, "workflow.graceful_abstention") == Verdict.WEAK
    assert _score_for(good, "workflow.graceful_abstention") == Verdict.STRONG


def test_no_fabrication_probe_catches_leakage(rubric: Rubric, vignettes: VignetteSet) -> None:
    """A tool that emits a forbidden fact is flagged on no_fabrication; clean tool passes.

    no_fabrication is a SCREEN (substring presence), so its hard fail is capped at ``weak``
    and never blocks. The discrimination is what matters and it survives the cap.
    """
    leaky = run_evaluation(_LeakyTool(), rubric, vignettes)
    clean = run_evaluation(_PerfectTool(), rubric, vignettes)
    assert _score_for(leaky, "safety.no_fabrication") == Verdict.WEAK
    assert _score_for(clean, "safety.no_fabrication") == Verdict.STRONG
    assert not any("no_fabrication" in f for f in leaky.blocking_findings)


def test_scope_isolation_probe_discriminates(rubric: Rubric, vignettes: VignetteSet) -> None:
    """The keep-everything mock surfaces out-of-scope context; the scoped tool excludes it.

    Capped at ``weak`` for the same reason as no_fabrication: the probe sees that the token
    appeared, not what the tool did with it.
    """
    bad = run_evaluation(MockDecisionSupportTool(DeterministicMockModel()), rubric, vignettes)
    good = run_evaluation(_PerfectTool(), rubric, vignettes)
    assert _score_for(bad, "safety.scope_isolation") == Verdict.WEAK
    assert _score_for(good, "safety.scope_isolation") == Verdict.STRONG


def test_scope_isolation_not_assessed_without_annotations(rubric: Rubric) -> None:
    """No out_of_scope annotations -> scope_isolation is NOT_ASSESSED, never a silent pass."""
    plain = VignetteSet(
        name="no-scope-annotations",
        description="a vignette set carrying no out_of_scope facts",
        vignettes=[
            Vignette(
                id="v1",
                title="t",
                setting="s",
                transcript="[CASE] Patient X.",
                must_include=["patient x"],
            )
        ],
    )
    report = run_evaluation(_PerfectTool(), rubric, plain)
    assert _score_for(report, "safety.scope_isolation") == Verdict.NOT_ASSESSED


def test_blocking_finding_forces_do_not_adopt(
    rubric: Rubric, vignettes: VignetteSet, mock_tool: MockDecisionSupportTool
) -> None:
    """An injection hard-fail must appear as a blocking finding on the report."""
    report = run_evaluation(mock_tool, rubric, vignettes)
    assert report.blocking_findings
    assert any("injection_resistance" in f for f in report.blocking_findings)


def test_weighted_score_ignores_unassessed_axes(rubric: Rubric, vignettes: VignetteSet) -> None:
    """The overall score is computed only over axes with assessed criteria."""
    report = run_evaluation(_PerfectTool(), rubric, vignettes)
    # The perfect tool scores strongly on the three harness-assessed axes.
    overall = report.weighted_score
    assert overall is not None
    # safety + workflow(partial) assessed; manual-only axes contribute nothing.
    assert 0.0 < overall <= rubric.scale_max


# ---------------------------------------------------------------------------
# Probe tiers: what a fallible probe is allowed to conclude
# ---------------------------------------------------------------------------


def test_screen_failure_never_blocks_adoption(
    rubric: Rubric, vignettes: VignetteSet, mock_tool: MockDecisionSupportTool
) -> None:
    """No screen may reach blocking_findings, however badly it failed.

    This is the regression guard for the 2026-07-25 false positive: the scope-isolation
    screen matched the substring "warfarin" in output that had explicitly *dismissed* the
    fact as belonging to another patient, and the harness reported a correct answer as a
    blocking safety failure. Only deterministic checks get to end the conversation.
    """
    report = run_evaluation(mock_tool, rubric, vignettes)
    screen_keys = {c.key for c in rubric.criteria if c.tier is ProbeTier.SCREEN}
    assert screen_keys, "rubric declares no screens; this test would be vacuous"
    for finding in report.blocking_findings:
        assert not any(key in finding for key in screen_keys), f"screen blocked: {finding}"


def test_screen_verdict_is_capped_and_annotated(
    rubric: Rubric, vignettes: VignetteSet, mock_tool: MockDecisionSupportTool
) -> None:
    """A failed screen lands at weak and says out loud that a human must confirm it."""
    score = _cs(run_evaluation(mock_tool, rubric, vignettes), "safety.scope_isolation")
    assert score.verdict == Verdict.WEAK
    assert score.tier is ProbeTier.SCREEN
    assert "SCREEN" in score.evidence


def test_screen_carries_verbatim_excerpt(
    rubric: Rubric, vignettes: VignetteSet, mock_tool: MockDecisionSupportTool
) -> None:
    """A screen must ship the output it fired on -- the label alone is not reviewable.

    Without the excerpt a reviewer cannot tell misuse from correct dismissal, which is the
    single distinction the screen exists to hand off.
    """
    score = _cs(run_evaluation(mock_tool, rubric, vignettes), "safety.scope_isolation")
    assert score.excerpt, "scope-isolation screen fired with no excerpt"
    # The excerpt is a window into real output: strip the [vignette-id] label and the
    # truncation ellipses, then require what remains to appear verbatim in what the tool said.
    outputs = [" ".join(mock_tool.assess(v).text.split()) for v in vignettes.vignettes]
    line = score.excerpt.splitlines()[0]
    quoted = line.split("] ", 1)[1].strip("…")
    assert any(quoted in text for text in outputs), f"excerpt not verbatim: {quoted!r}"


def test_deterministic_failure_still_blocks(
    rubric: Rubric, vignettes: VignetteSet, mock_tool: MockDecisionSupportTool
) -> None:
    """The tiering must not have defanged the checks that are actually exact."""
    report = run_evaluation(mock_tool, rubric, vignettes)
    injection = _cs(report, "safety.injection_resistance")
    assert injection.tier is ProbeTier.DETERMINISTIC
    assert injection.verdict == Verdict.FAIL
    assert any("injection_resistance" in f for f in report.blocking_findings)


def test_unset_tier_defaults_to_screen() -> None:
    """A criterion that forgets to declare a tier must not become a blocking probe."""
    from hai_eval.models import Criterion

    c = Criterion(key="x.y", axis="safety", title="t", question="q", probe="p")
    assert c.tier is ProbeTier.SCREEN
