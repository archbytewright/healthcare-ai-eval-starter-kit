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


def test_scheme_less_host_without_a_port_gets_ollamas_default() -> None:
    """A bare host means Ollama's port, not port 80.

    Without this the request goes to port 80 and fails with a connection
    refused that reads as "Ollama is down" rather than "you left the port off".
    """
    assert OllamaModel("m", host="10.0.0.5")._host == "http://10.0.0.5:11434"
    assert OllamaModel("m", host="example.test")._host == "http://example.test:11434"
    # An explicit port is never overridden.
    assert OllamaModel("m", host="10.0.0.5:9999")._host == "http://10.0.0.5:9999"


def test_an_explicit_scheme_keeps_that_scheme_s_port() -> None:
    """Only the scheme-less form gets 11434, matching Ollama's own rule.

    Defaulting unconditionally would send https://host to port 11434 and break
    an Ollama sitting behind a TLS reverse proxy, which is the ordinary way to
    reach one that is not on localhost.
    """
    assert OllamaModel("m", host="https://ollama.example.test")._host == (
        "https://ollama.example.test"
    )
    assert OllamaModel("m", host="http://ollama.example.test")._host == (
        "http://ollama.example.test"
    )
    assert OllamaModel("m", host="https://ollama.example.test:8443")._host == (
        "https://ollama.example.test:8443"
    )


def test_cli_rejects_unrecognized_model(tmp_path: Path) -> None:
    """--model without the 'ollama:' prefix errors instead of silently running the mock."""
    out = tmp_path / "r.md"
    assert main(["run", "--model", "gpt-4", "--out", str(out)]) == 2
    assert not out.exists()


def test_cli_ollama_dispatch_writes_report(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """--model ollama:<name> routes through OllamaModel and writes a named report."""
    monkeypatch.setattr(
        "urllib.request.urlopen", _reply({"message": {"content": "Conservative management."}})
    )
    out = tmp_path / "r.md"
    assert main(["run", "--model", "ollama:llama3.1:8b", "--out", str(out)]) == 0
    assert "llama3.1:8b" in out.read_text(encoding="utf-8")


def test_loopback_is_decided_on_the_hostname_not_a_url_prefix() -> None:
    """A data-residency claim, and it was decided by prefix-matching a string.

    ``http://localhost.evil.com`` starts with the guarded prefix, so the report asserted
    "inference stayed on this machine" about traffic that left it, and titled itself
    "(Ollama, local)" as well. The fix shipped with no test at all, which for the one field in the
    artifact that makes a claim about where data went is the wrong thing to leave unguarded.

    Note the direction: anything unparseable reads as NON-loopback, so the harness under-claims.
    """
    from hai_eval.ollama_model import _is_loopback

    for host in ("http://localhost:11434", "http://127.0.0.1:11434", "http://[::1]:11434"):
        assert _is_loopback(host), host
    for host in (
        "http://localhost.evil.com:11434",
        "http://127.0.0.1.evil.com",
        "http://100.104.25.37:11434",
        "not a url",
    ):
        assert not _is_loopback(host), host
