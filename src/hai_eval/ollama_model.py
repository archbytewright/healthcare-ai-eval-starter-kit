"""A real-model seam for the harness: an Ollama-backed model so the worked example
can run against a *live* local LLM, not only the deterministic mock.

This is what turns the kit from a *method promise* into a *method demonstration*: the
same ``MockModel`` seam (``generate(system, user) -> str``), filled by a real model, so
the evaluator's probes score an actual model's behavior on the synthetic vignettes.

Local inference by design -- the model runs against a local Ollama instance (host set via
the ``OLLAMA_HOST`` environment variable, default ``http://localhost:11434``), so no
vignette text or model output egresses. Deterministic-ish (temperature 0) so a report is
reproducible. Stdlib-only.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from urllib.parse import urlsplit, urlunsplit

DEFAULT_PORT = 11434


class OllamaError(RuntimeError):
    """An Ollama request failed or returned no usable content."""


class OllamaModel:
    """Satisfies the :class:`hai_eval.tool.MockModel` seam via an Ollama ``/api/chat`` call.

    Structural typing: this class has ``generate(system, user) -> str``, so it drops into
    :class:`hai_eval.tool.MockDecisionSupportTool` exactly where the mock model did.
    """

    def __init__(
        self,
        model: str,
        *,
        host: str | None = None,
        timeout: float = 180.0,
    ) -> None:
        self.model = model
        resolved = host or os.environ.get("OLLAMA_HOST") or "http://localhost:11434"
        had_scheme = "://" in resolved
        if not had_scheme:
            # Ollama's own OLLAMA_HOST convention is scheme-less (e.g. '127.0.0.1:11434').
            resolved = f"http://{resolved}"
        resolved = resolved.rstrip("/")

        # A scheme-less host with no port would otherwise be tried on port 80
        # and fail with a bare "connection refused" that explains nothing.
        # Ollama's own client fills in 11434 here, and only here: given an
        # explicit scheme it uses that scheme's port, so https://host stays on
        # 443 and keeps working behind a TLS proxy.
        parsed = urlsplit(resolved)
        if not had_scheme and parsed.port is None and parsed.netloc:
            resolved = urlunsplit(
                parsed._replace(netloc=f"{parsed.netloc}:{DEFAULT_PORT}")
            )
        self._host = resolved
        self._timeout = timeout

    def generate(self, system: str, user: str) -> str:
        body = json.dumps(
            {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "stream": False,
                "options": {"temperature": 0},
            }
        ).encode("utf-8")
        req = urllib.request.Request(
            f"{self._host}/api/chat", data=body, headers={"Content-Type": "application/json"}
        )
        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                data = json.load(resp)
        except (urllib.error.URLError, OSError, ValueError) as exc:
            raise OllamaError(f"Ollama call failed for {self.model!r}: {exc}") from exc
        message = data.get("message") or {}
        content = str(message.get("content") or "")
        if not content.strip():
            snippet = str(data)[:160]
            raise OllamaError(f"Ollama returned empty content for {self.model!r}: {snippet}")
        return content.strip()
