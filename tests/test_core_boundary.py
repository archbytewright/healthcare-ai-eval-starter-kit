"""E1 — the core/profile boundary, enforced rather than asked for.

An architectural rule nobody checks is a comment. This one is cheap to check and expensive to
violate: the moment a clinical noun appears in the core, the seam has leaked and the next profile
will not fit. Catching it here costs a grep; catching it at profile number two costs a refactor.

Deliberately a vocabulary test rather than an import test. Leakage does not usually arrive as an
import -- it arrives as a field named ``patient_id``, a docstring reasoning about contraindications,
or a default that assumes a drug list.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

CORE = Path(__file__).resolve().parent.parent / "src" / "hai_eval" / "core"

# Clinical and product vocabulary that has no business in a domain-neutral engine. Generic
# testing words (case, scenario, subject) are intentionally absent: the core needs SOME noun for
# the unit of evaluation, and forbidding all of them would make the rule unusable rather than
# strict.
FORBIDDEN = (
    "patient",
    "clinic",  # clinical, clinician
    "diagnos",  # diagnosis, diagnostic
    "contraindicat",
    "drug",
    "medication",
    "dose",
    "dosage",
    "allerg",
    "vignette",
    "warfarin",
    "naproxen",
    "nitrofurantoin",
    "metformin",
    "nsaid",
    "ehr",
    "phi",
)


def domain_hits(text: str) -> list[str]:
    """Forbidden vocabulary found in ``text``. Extracted so it can be tested in both directions.

    A detector only ever used by the check it powers is untestable by construction: blank it out and
    every assertion still passes. The mutation runner found exactly that, so the detector is now a
    function with its own positive test.
    """
    lowered = text.lower()
    return sorted({word for word in FORBIDDEN if re.search(rf"\b{word}", lowered)})


def _core_sources() -> list[Path]:
    return sorted(CORE.rglob("*.py"))


def test_core_package_exists_and_is_populated() -> None:
    """Guards the guard: a boundary test over an empty directory passes vacuously."""
    sources = _core_sources()
    assert len(sources) >= 6, f"expected the core package to be populated, found {sources}"


@pytest.mark.parametrize("path", _core_sources(), ids=lambda p: p.name)
def test_core_contains_no_domain_vocabulary(path: Path) -> None:
    """No clinical noun anywhere in the core -- code, comments or docstrings."""
    hits = domain_hits(path.read_text(encoding="utf-8"))
    assert not hits, (
        f"{path.name} contains domain vocabulary {hits}. The core must not know what it is "
        f"evaluating -- move this to a profile."
    )


def test_core_does_not_import_a_profile() -> None:
    """Dependencies point one way: profiles import the core, never the reverse."""
    for path in _core_sources():
        text = path.read_text(encoding="utf-8")
        assert "profiles." not in text and "from hai_eval.profiles" not in text, (
            f"{path.name} imports a profile; the core must not depend on any domain"
        )


def test_the_detector_detects() -> None:
    """Guards the guard: a blanked-out detector would make every check above pass vacuously."""
    assert domain_hits("the clinician reviewed the patient's medication") == [
        "clinic",
        "medication",
        "patient",
    ]
    assert domain_hits("a scenario, a response, a criterion, a weight") == []
