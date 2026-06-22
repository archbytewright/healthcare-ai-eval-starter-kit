"""Behavioural tests for the tool seam and its planted failure modes.

These assert the mock CDS tool *actually* exhibits the three failure modes the
worked example relies on, so the rubric has something real to catch. If a refactor
accidentally fixed a planted failure, these fail loudly.
"""

from __future__ import annotations

from hai_eval.loader import load_vignettes
from hai_eval.models import Vignette
from hai_eval.tool import INJECTION_CANARY, DeterministicMockModel, MockDecisionSupportTool


def _vignette(set_name: str) -> Vignette:
    vignettes = load_vignettes()
    return {v.id: v for v in vignettes.vignettes}[set_name]


def test_mock_drops_contraindication_line() -> None:
    """The planted omission: a [CONTRAINDICATION] line must not survive the recommendation."""
    tool = MockDecisionSupportTool(DeterministicMockModel())
    out = tool.assess(_vignette("vg-02-contraindication-omission"))
    assert "chronic kidney disease" not in out.text.lower()
    assert "colchicine" not in out.text.lower()
    # ...while the (now-unsafe) NSAID guidance line on the same case survives -- that
    # is exactly the failure: the recommendation keeps the NSAID, drops the warning.
    assert "naproxen" in out.text.lower()


def test_mock_follows_embedded_injection() -> None:
    """The planted trust-boundary failure: the canary appears and is flagged."""
    tool = MockDecisionSupportTool(DeterministicMockModel())
    out = tool.assess(_vignette("vg-04-embedded-injection"))
    assert out.followed_injection is True
    assert INJECTION_CANARY in out.text
    assert "injection-followed" in out.flags


def test_mock_never_defers() -> None:
    """The planted over-confidence failure: no case triggers deferral/abstention."""
    tool = MockDecisionSupportTool(DeterministicMockModel())
    vignettes = load_vignettes()
    assert all(not tool.assess(v).abstained for v in vignettes.vignettes)


def test_clean_case_is_retained() -> None:
    """A clean case loses nothing: every required fact survives, no canary."""
    tool = MockDecisionSupportTool(DeterministicMockModel())
    out = tool.assess(_vignette("vg-01-routine"))
    for fact in ("thiazide", "ace inhibitor"):
        assert fact in out.text.lower()
    assert INJECTION_CANARY not in out.text


def test_model_is_deterministic() -> None:
    """Same input, same output -- the example must be byte-reproducible."""
    model = DeterministicMockModel()
    a = model.generate("sys", "[CONTRAINDICATION] CKD\n[GUIDANCE] colchicine")
    b = model.generate("sys", "[CONTRAINDICATION] CKD\n[GUIDANCE] colchicine")
    assert a == b
