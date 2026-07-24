"""A real-model seam for the harness: an Ollama-backed model so the worked example
can run against a *live* local LLM, not only the deterministic mock.

This is what turns the kit from a *method promise* into a *method demonstration*: the
same ``MockModel`` seam (``generate(system, user) -> str``), filled by a real model, so
the evaluator's probes score an actual model's behaviour on the synthetic vignettes.

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
        if "://" not in resolved:
            # Ollama's own OLLAMA_HOST convention is scheme-less (e.g. '127.0.0.1:11434').
            resolved = f"http://{resolved}"
        self._host = resolved.rstrip("/")
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
