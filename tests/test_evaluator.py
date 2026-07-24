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
    EvaluationReport,
    Rubric,
    ToolOutput,
    Verdict,
    Vignette,
    VignetteSet,
)
from hai_eval.tool import DeterministicMockModel, MockDecisionSupportTool


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
    """A tool that emits a forbidden fact hard-fails no_fabrication; clean tool passes."""
    leaky = run_evaluation(_LeakyTool(), rubric, vignettes)
    clean = run_evaluation(_PerfectTool(), rubric, vignettes)
    assert _score_for(leaky, "safety.no_fabrication") == Verdict.FAIL
    assert _score_for(clean, "safety.no_fabrication") == Verdict.STRONG


def test_scope_isolation_probe_discriminates(rubric: Rubric, vignettes: VignetteSet) -> None:
    """The keep-everything mock leaks out-of-scope context; the scoped tool excludes it."""
    bad = run_evaluation(MockDecisionSupportTool(DeterministicMockModel()), rubric, vignettes)
    good = run_evaluation(_PerfectTool(), rubric, vignettes)
    assert _score_for(bad, "safety.scope_isolation") == Verdict.FAIL
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


def test_weighted_score_ignores_unassessed_axes(
    rubric: Rubric, vignettes: VignetteSet
) -> None:
    """The overall score is computed only over axes with assessed criteria."""
    report = run_evaluation(_PerfectTool(), rubric, vignettes)
    # The perfect tool scores strongly on the three harness-assessed axes.
    overall = report.weighted_score
    assert overall is not None
    # safety + workflow(partial) assessed; manual-only axes contribute nothing.
    assert 0.0 < overall <= rubric.scale_max
