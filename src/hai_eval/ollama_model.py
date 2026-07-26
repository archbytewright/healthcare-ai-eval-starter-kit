"""A real-model seam for the harness: an Ollama-backed model so the worked example
can run against a *live* local LLM, not only the deterministic mock.

This is what turns the kit from a *method promise* into a *method demonstration*: the
same ``MockModel`` seam (``generate(system, user) -> str``), filled by a real model, so
the evaluator's probes score an actual model's behavior on the synthetic vignettes.

Inference runs against an Ollama instance you control (``OLLAMA_HOST``, default
``http://localhost:11434``). **On the default host nothing leaves the machine; point it
elsewhere and the vignette text and model output travel there**, which is why every report
records whether inference stayed on the loopback interface rather than asserting that it did.
Temperature 0, which is not the same as reproducible -- a served model is not bit-for-bit
deterministic, so the sampling options are RECORDED in the report instead of being described
as determinism. Stdlib-only.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from ipaddress import ip_address
from urllib.parse import urlsplit, urlunsplit

DEFAULT_PORT = 11434


class OllamaError(RuntimeError):
    """An Ollama request failed or returned no usable content."""


def _is_loopback(host: str) -> bool:
    """Whether ``host`` resolves to this machine, decided on the parsed HOSTNAME.

    ⭐ Prefix-matching the URL string was a data-residency lie waiting to happen:
    ``http://localhost.evil.com`` and ``http://127.0.0.1.evil.com`` both start with the guarded
    prefixes, so a report would have asserted "inference stayed on this machine" about traffic that
    left it, and titled itself "(Ollama, local)" as well. In a PHI-adjacent artifact that is the
    wrong way to be wrong, which the comment below already said while the code did the opposite.

    Note the failure direction is now safe: an unparseable or unusual host reads as non-loopback,
    so the harness under-claims rather than over-claims about where the data went.
    """
    try:
        hostname = urlsplit(host).hostname
    except ValueError:
        return False
    if hostname is None:
        return False
    if hostname == "localhost":
        return True
    try:
        return ip_address(hostname).is_loopback
    except ValueError:
        return False


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
        seed: int = 0,
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
            resolved = urlunsplit(parsed._replace(netloc=f"{parsed.netloc}:{DEFAULT_PORT}"))
        self._host = resolved
        self._timeout = timeout
        self.seed = seed

    def generate(self, system: str, user: str) -> str:
        body = json.dumps(
            {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "stream": False,
                # temperature 0 is greedy decoding; the seed pins the remaining sampler state.
                # Neither makes a served model bit-for-bit reproducible -- batching, quant and
                # server defaults still move -- which is why the options are RECORDED in the
                # report rather than described as determinism.
                "options": {"temperature": 0, "seed": self.seed},
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
        if not isinstance(data, dict):
            raise OllamaError(
                f"Ollama returned {type(data).__name__}, expected an object, for {self.model!r}"
            )
        message = data.get("message") or {}
        content = str(message.get("content") or "")
        if not content.strip():
            snippet = str(data)[:160]
            raise OllamaError(f"Ollama returned empty content for {self.model!r}: {snippet}")
        return content.strip()

    @property
    def provenance(self) -> dict[str, str]:
        """Run facts recorded into the report so it can be audited against its conditions."""
        local = _is_loopback(self._host)
        return {
            "model": self.model,
            "backend": "ollama /api/chat",
            "sampling": f"temperature=0, seed={self.seed}, stream=false",
            # Deliberately does not claim to know WHERE a non-loopback host is. It may be
            # another box, or this one reached by its own LAN/VPN address. The harness can see
            # that the traffic left the loopback interface and nothing more, so that is all it
            # says; a report that guessed would be asserting a data-residency fact it cannot
            # establish, which for a PHI-adjacent artifact is the wrong way to be wrong.
            "host kind": (
                "loopback (inference stayed on this machine)"
                if local
                else "non-loopback address (traffic left the loopback interface; "
                "confirm where that host is before sending anything sensitive)"
            ),
        }
