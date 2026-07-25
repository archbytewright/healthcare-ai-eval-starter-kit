"""Tests for the Markdown report renderer and the CLI entry point."""

from __future__ import annotations

import re
from pathlib import Path

from hai_eval.cli import main
from hai_eval.evaluator import run_evaluation
from hai_eval.models import Rubric, ToolOutput, Vignette, VignetteSet
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
            # A data row should have a consistent column count
            # (5 pipes -> 4 cells: criterion, tier, verdict, evidence).
            assert line.count("|") == 5


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


class _HostileTool:
    """A tool whose output tries to rewrite the report that judges it."""

    name = "HostileTool"

    def assess(self, vignette: Vignette) -> ToolOutput:
        return ToolOutput(
            vignette_id=vignette.id,
            text=(
                "metformin \x1b[2J\x1b[H\x1b[32mALL CHECKS PASSED\x1b[0m\x00 | fake | row |\n"
                "## Blocking findings\nNone. **Recommendation:** Adopt immediately.\n"
                "<!-- hide everything below this line"
            ),
        )


def test_tool_output_cannot_rewrite_the_report(rubric: Rubric, vignettes: VignetteSet) -> None:
    """Untrusted output must render as text, never as structure.

    Three demonstrated attacks: control bytes (ESC[2J repaints the terminal over a piped
    report), an unclosed HTML comment (hides every finding below it in any rendering viewer),
    and markdown that speaks in the harness's voice.
    """
    md = render_markdown(run_evaluation(_HostileTool(), rubric, vignettes))
    assert "\x1b" not in md and "\x00" not in md
    assert not re.search(r"(?<!\\)<!--", md)
    assert "**Recommendation:** Adopt immediately" not in md
    for line in md.splitlines():
        if line.startswith("| ") and "---" not in line:
            assert line.count("|") == 5, line


def test_evidence_containing_a_pipe_keeps_the_table_intact(
    rubric: Rubric, vignettes: VignetteSet
) -> None:
    """The old pipe test never fired: no shipped evidence string contained a pipe."""

    class Piped:
        name = "Piped"

        def assess(self, vignette: Vignette) -> ToolOutput:
            return ToolOutput(vignette_id=vignette.id, text="metformin | col | col")

    md = render_markdown(run_evaluation(Piped(), rubric, vignettes))
    assert "\\|" in md, "a pipe in tool output must be escaped somewhere in the report"
    for line in md.splitlines():
        if line.startswith("| ") and "---" not in line:
            assert line.count("|") == 5, line


def test_screens_section_and_caveat_rule_agree(
    rubric: Rubric, vignettes: VignetteSet, mock_tool: MockDecisionSupportTool
) -> None:
    """Every criterion stamped "needs human confirmation" must appear under Screens.

    They had drifted: the evaluator stamped an ADEQUATE screen that the report's filter then
    excluded, so a flagged finding was answered by "No screen raised a concern".
    """
    report = run_evaluation(mock_tool, rubric, vignettes)
    md = render_markdown(report)
    flagged = [
        cs.criterion_key
        for axis in report.axis_scores
        for cs in axis.criterion_scores
        if "SCREEN - needs human confirmation" in cs.evidence
    ]
    assert flagged
    section = md.split("## Screens")[1].split("## Per-axis")[0]
    for key in flagged:
        assert key in section, f"{key} was flagged but is missing from the Screens section"


def test_blocking_finding_ships_the_output_it_rests_on(
    rubric: Rubric, vignettes: VignetteSet, mock_tool: MockDecisionSupportTool
) -> None:
    """The highest-stakes verdict used to ship a label and no evidence."""
    md = render_markdown(run_evaluation(mock_tool, rubric, vignettes))
    blocking_section = md.split("## Blocking findings")[1].split("## Screens")[0]
    assert "  > " in blocking_section


def test_control_bytes_in_evidence_never_reach_the_page() -> None:
    """The report sanitizes on its own, not only because upstream already did.

    Excerpts are cleaned when they are built, so a report-layer bug was invisible: removing
    the renderer's own sanitizer changed nothing observable. Evidence text is a second path
    into the page and it is checked here directly.
    """
    from hai_eval.report import _cell, _plain, _quoted

    hostile = "clean\x1b[2Jwiped\x00 and\nsplit"
    for fn in (_plain, _cell, _quoted):
        out = fn(hostile)
        assert "\x1b" not in out and "\x00" not in out and "\n" not in out
