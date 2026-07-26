"""Regenerate the shipped claim table from the profile that defines it.

Run after changing what any check may claim:

    uv run python tools/render_claims.py

A test compares the file on disk against this output and fails when they disagree, so the document
cannot quietly describe a version of the code that no longer exists. That is not a hypothetical
failure mode: the public README asserted a verdict its own generated reports had stopped issuing,
and survived a regeneration because it was prose about the runs rather than derived from them.
"""

from __future__ import annotations

from pathlib import Path

from hai_eval.core.claims import render_claim_table
from hai_eval.profiles.cds import CDS_PROFILE

DOC = Path(__file__).resolve().parent.parent / "framework" / "05-claim-table.md"


def main() -> None:
    DOC.write_text(render_claim_table(CDS_PROFILE), encoding="utf-8")
    print(f"wrote {DOC.relative_to(DOC.parent.parent)}")


if __name__ == "__main__":
    main()
