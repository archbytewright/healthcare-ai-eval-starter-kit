"""Command-line entry point for the worked-example evaluation.

``hai-eval run`` loads the shipped rubric and synthetic vignette set, runs a clinical
decision support tool through the harness, and writes a Markdown report. By default the
tool is the deterministic mock -- a self-contained demonstration of the method end to
end; ``--model ollama:<name>`` evaluates a live local model via Ollama instead.

Usage:
    hai-eval run                             # deterministic mock -> reports/<tool>.md
    hai-eval run --out -                     # print report to stdout
    hai-eval run --model ollama:llama3.1:8b  # evaluate a live local model
    hai-eval run --rubric path.yaml --vignettes path.yaml
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from loguru import logger

from hai_eval.evaluator import EvaluationError, run_evaluation
from hai_eval.loader import LoaderError, load_rubric, load_vignettes
from hai_eval.ollama_model import OllamaError, OllamaModel
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
    run.add_argument(
        "--model",
        type=str,
        default=None,
        help="evaluate a live local model via Ollama, e.g. 'ollama:llama3.1:8b'; "
        "default (omitted) runs the deterministic mock.",
    )
    return parser


def _run(args: argparse.Namespace) -> int:
    try:
        rubric = load_rubric(args.rubric)
        vignettes = load_vignettes(args.vignettes)
    except LoaderError as exc:
        logger.error("load failed: {}", exc)
        return 2

    tool: MockDecisionSupportTool
    if args.model is None:
        tool = MockDecisionSupportTool(
            DeterministicMockModel(),
            provenance={"model": "DeterministicMockModel (offline, byte-reproducible)"},
        )
    elif args.model.startswith("ollama:"):
        model_name = args.model.split(":", 1)[1]
        backend = OllamaModel(model_name)
        # The report used to be titled "... (Ollama, local) ..." unconditionally, so pointing
        # OLLAMA_HOST at a remote endpoint produced an artifact asserting local inference.
        # Take the wording from the resolved host instead of from the flag.
        # startswith, not `in`: the non-loopback string CONTAINS the word "loopback", so the
        # substring test was true in both branches and every report was titled "local" -- including
        # the three shipped ones, whose own provenance block said otherwise.
        where = "local" if backend.provenance["host kind"].startswith("loopback") else "remote host"
        tool = MockDecisionSupportTool(
            backend,
            name=f"{model_name} (Ollama, {where}) as CDS tool",
            strip_tags=True,
            provenance=backend.provenance,
        )
    else:
        logger.error(
            "unrecognized --model {!r}; expected 'ollama:<name>' (e.g. 'ollama:llama3.1:8b')",
            args.model,
        )
        return 2

    try:
        report = run_evaluation(tool, rubric, vignettes)
    except OllamaError as exc:
        logger.error("live-model evaluation failed: {}", exc)
        return 2
    except EvaluationError as exc:
        logger.error("evaluation refused: {}", exc)
        return 2
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
