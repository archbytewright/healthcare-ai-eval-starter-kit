"""Tests for the Markdown report renderer and the CLI entry point."""

from __future__ import annotations

from pathlib import Path

from hai_eval.cli import main
from hai_eval.evaluator import run_evaluation
from hai_eval.models import Rubric, VignetteSet
from hai_eval.report import render_markdown
from hai_eval.tool import MockDecisionSupportTool


def test_report_surfaces_blocking_recommendation(
    rubric: Rubric, vignettes: VignetteSet, mock_tool: MockDecisionSupportTool
) -> None:
    """A run with a hard fail must render a do-not-adopt recommendation."""
    report = run_evaluation(mock_tool, rubric, vignettes)
    md = render_markdown(report)
    assert "# Evaluation report" in md
    assert "Do not adopt as-is" in md
    # The injection blocking finding must be visible in the report body.
    assert "injection" in md.lower()


def test_report_is_pipe_safe(
    rubric: Rubric, vignettes: VignetteSet, mock_tool: MockDecisionSupportTool
) -> None:
    """Evidence strings containing '|' must not break the Markdown tables."""
    report = run_evaluation(mock_tool, rubric, vignettes)
    md = render_markdown(report)
    for line in md.splitlines():
        if line.startswith("| ") and " | " in line and "---" not in line:
            # A data row should have a consistent column count (4 pipes -> 3 cells).
            assert line.count("|") == 4


def test_cli_writes_report(tmp_path: Path) -> None:
    """`hai-eval run --out <file>` writes a non-empty report and exits 0."""
    out = tmp_path / "report.md"
    code = main(["run", "--out", str(out)])
    assert code == 0
    assert out.exists()
    assert "Evaluation report" in out.read_text(encoding="utf-8")


def test_cli_missing_rubric_returns_error(tmp_path: Path) -> None:
    """A bad rubric path exits non-zero rather than raising."""
    code = main(["run", "--rubric", str(tmp_path / "nope.yaml")])
    assert code == 2
