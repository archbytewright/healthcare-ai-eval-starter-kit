"""One text fold, used everywhere a literal string is compared.

⭐ **This module exists because the same defect was fixed three times in three places and stayed
open in a fourth.** A tool's output is chosen by the party being evaluated, so any check that
compares literal strings can be walked past by a character a human reader cannot see. That was
found and closed in the evaluator's matching path; then the adapter's canary detection was left on
an enumerated allowlist; then the abstention detector was left matching raw text entirely; and when
*that* was folded, it was folded for two Unicode categories out of three, so a single control byte
still hid a deferral and doubled a do-nothing tool's score.

Each of those was a real repair to a real call site, and each left a sibling open. The lesson is not
"fold harder" -- it is that a rule enforced by remembering to call something is not enforced. There
is now exactly one function, and the honest test of whether a new comparison is safe is whether it
went through here.

The fold asks what a character IS rather than which invisible ones somebody listed:

- **NFKC**, so a fullwidth or otherwise compatibility-spelled token folds to its plain form.
- **Format and combining marks (``Cf``, ``Mn``) removed** -- zero-width spaces, soft hyphens,
  bidi controls, combining grapheme joiners.
- **Control characters (``Cc``) collapsed to a space** rather than deleted, so a newline inside a
  sentence does not silently join two words into one that matches nothing.
- **Unicode dashes folded to ASCII**, because a non-breaking or typographic hyphen inside a token
  is invisible in rendered output and fatal to a comparison.
- **Case-folded**, last, so every caller gets the same casing rule.

What it deliberately does NOT do: homoglyphs. A Cyrillic look-alike is a legitimate letter
rather than an invisible one, and NFKC does not touch it. Closing that needs a confusables
table, a dependency this kit does not carry -- so it stays in the README's list of what this
version cannot do, stated rather than quietly hoped away.
"""

from __future__ import annotations

import unicodedata

_UNICODE_DASHES = (
    "\u2010\u2011\u2012\u2013\u2014\u2015\u2212\ufe58\ufe63\uff0d"
)
_DASHES = str.maketrans(dict.fromkeys(_UNICODE_DASHES, "-"))


def fold_for_match(text: str) -> str:
    """Fold ``text`` for literal comparison. Never use this for anything a reader will see.

    Excerpts must stay verbatim, so display text is flattened elsewhere; the aggressive folding
    that makes matching robust must never reach the sentence a reviewer is asked to judge.
    """
    folded = unicodedata.normalize("NFKC", text)
    kept: list[str] = []
    for ch in folded:
        category = unicodedata.category(ch)
        if category in {"Cf", "Mn"}:
            continue
        kept.append(" " if category == "Cc" else ch)
    return "".join(kept).translate(_DASHES).lower()
