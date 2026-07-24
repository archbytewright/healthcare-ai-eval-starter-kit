"""Tests for the Ollama-backed real-model adapter and its CLI wiring.

These never touch the network: ``urllib.request.urlopen`` is monkeypatched, so the
adapter's request, parse, and error paths -- and the CLI ``--model`` dispatch -- are
exercised deterministically.
"""

from __future__ import annotations

import io
import json
import urllib.error
from pathlib import Path
from typing import Any

import pytest

from hai_eval.cli import main
from hai_eval.ollama_model import OllamaError, OllamaModel


def _reply(payload: dict[str, Any]) -> Any:
    """Build a fake urlopen that returns ``payload`` as a JSON /api/chat response."""

    def fake_urlopen(req: Any, timeout: float = 0) -> io.BytesIO:
        return io.BytesIO(json.dumps(payload).encode("utf-8"))

    return fake_urlopen


def test_generate_returns_message_content(monkeypatch: pytest.MonkeyPatch) -> None:
    """A well-formed /api/chat response yields the stripped message content."""
    monkeypatch.setattr("urllib.request.urlopen", _reply({"message": {"content": "  hi  "}}))
    assert OllamaModel("llama3.1:8b").generate("sys", "user") == "hi"


def test_generate_raises_on_empty_content(monkeypatch: pytest.MonkeyPatch) -> None:
    """Missing/empty content is an OllamaError, never a silent empty string."""
    monkeypatch.setattr("urllib.request.urlopen", _reply({"message": {}}))
    with pytest.raises(OllamaError):
        OllamaModel("llama3.1:8b").generate("sys", "user")


def test_generate_wraps_transport_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """A transport failure (Ollama down) is wrapped as OllamaError, not a raw URLError."""

    def boom(req: Any, timeout: float = 0) -> io.BytesIO:
        raise urllib.error.URLError("connection refused")

    monkeypatch.setattr("urllib.request.urlopen", boom)
    with pytest.raises(OllamaError):
        OllamaModel("llama3.1:8b").generate("sys", "user")


def test_host_scheme_is_normalized() -> None:
    """A scheme-less host gets an http:// prefix; a trailing slash is trimmed."""
    assert OllamaModel("m", host="127.0.0.1:11434")._host == "http://127.0.0.1:11434"
    assert OllamaModel("m", host="http://h:1/")._host == "http://h:1"


def test_cli_rejects_unrecognized_model(tmp_path: Path) -> None:
    """--model without the 'ollama:' prefix errors instead of silently running the mock."""
    out = tmp_path / "r.md"
    assert main(["run", "--model", "gpt-4", "--out", str(out)]) == 2
    assert not out.exists()


def test_cli_ollama_dispatch_writes_report(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """--model ollama:<name> routes through OllamaModel and writes a named report."""
    monkeypatch.setattr(
        "urllib.request.urlopen", _reply({"message": {"content": "Conservative management."}})
    )
    out = tmp_path / "r.md"
    assert main(["run", "--model", "ollama:llama3.1:8b", "--out", str(out)]) == 0
    assert "llama3.1:8b" in out.read_text(encoding="utf-8")
