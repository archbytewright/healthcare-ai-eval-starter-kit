"""Command-line entry point for the worked-example evaluation.

``hai-eval run`` loads the shipped rubric and synthetic vignette set, runs the
deterministic mock clinical decision support through the harness, and writes a Markdown
report. With no real tool wired in, the command is a self-contained
demonstration of the method end to end.

Usage:
    hai-eval run                       # write report to reports/<tool>.md
    hai-eval run --out -               # print report to stdout
    hai-eval run --rubric path.yaml --vignettes path.yaml
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from loguru import logger

from hai_eval.evaluator import run_evaluation
from hai_eval.loader import LoaderError, load_rubric, load_vignettes
from hai_eval.report import render_markdown
from hai_eval.tool import DeterministicMockModel, MockDecisionSupportTool

_DEFAULT_REPORT_DIR = Path("reports")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="hai-eval", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="run the worked-example evaluation")
    run.add_argument(
        "--rubric",
        type=Path,
        default=None,
        help="path to a rubric YAML (defaults to the shipped framework/rubric.yaml)",
    )
    run.add_argument(
        "--vignettes",
        type=Path,
        default=None,
        help="path to a vignette YAML (defaults to the shipped data/vignettes.yaml)",
    )
    run.add_argument(
        "--out",
        type=str,
        default=None,
        help="output path for the Markdown report, or '-' for stdout "
        "(defaults to reports/<tool>.md)",
    )
    return parser


def _run(args: argparse.Namespace) -> int:
    try:
        rubric = load_rubric(args.rubric)
        vignettes = load_vignettes(args.vignettes)
    except LoaderError as exc:
        logger.error("load failed: {}", exc)
        return 2

    tool = MockDecisionSupportTool(DeterministicMockModel())
    report = run_evaluation(tool, rubric, vignettes)
    markdown = render_markdown(report)

    if args.out == "-":
        sys.stdout.write(markdown)
        if not markdown.endswith("\n"):
            sys.stdout.write("\n")
        return 0

    out_path = Path(args.out) if args.out else _DEFAULT_REPORT_DIR / f"{_slug(tool.name)}.md"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(markdown, encoding="utf-8")
    logger.info("wrote report to {}", out_path)
    overall = report.weighted_score
    score_text = "n/a" if overall is None else f"{overall:.1f}/{report.scale_max}"
    logger.info(
        "overall {} | blocking findings: {}",
        score_text,
        len(report.blocking_findings),
    )
    return 0


def _slug(name: str) -> str:
    """Turn a tool name into a filesystem-safe slug for the default report path."""
    cleaned = [ch.lower() if ch.isalnum() else "-" for ch in name]
    slug = "".join(cleaned)
    while "--" in slug:
        slug = slug.replace("--", "-")
    return slug.strip("-") or "report"


def main(argv: list[str] | None = None) -> int:
    """CLI entry point. Returns a process exit code."""
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.command == "run":
        return _run(args)
    parser.error(f"unknown command {args.command!r}")  # pragma: no cover
    return 2  # pragma: no cover


if __name__ == "__main__":
    raise SystemExit(main())
