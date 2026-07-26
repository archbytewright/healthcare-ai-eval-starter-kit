"""Direct tests for the one fold every literal comparison goes through.

Written because a mutation sweep found that the fold had **no direct test at all**: deleting the
dash folding, or changing control characters from a space to a deletion, left the whole suite green.
The comparisons that depend on it were tested; the thing itself was not, so its behaviour was
guarded only where some other test happened to notice.

Each case below names the evasion it closes. They are grouped by Unicode category rather than by
the particular characters anyone thought of, because "the three characters I remembered" is how
this defect survived three separate repairs.
"""

from __future__ import annotations

import pytest

from hai_eval.textfold import contains_folded, fold_for_match


class TestFold:
    """What the fold normalises, one property per test."""

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("​stage 4", "stage 4"),  # Cf - zero-width space
            ("st­age 4", "stage 4"),  # Cf - soft hyphen
            ("stage͏ 4", "stage 4"),  # Mn - combining grapheme joiner
            ("ＳＴＡＧＥ 4", "stage 4"),  # NFKC - fullwidth
            ("STAGE 4", "stage 4"),  # case
        ],
    )
    def test_invisible_and_compatibility_forms_fold_away(self, raw: str, expected: str) -> None:
        assert fold_for_match(raw) == expected

    @pytest.mark.parametrize("dash", ["‐", "‑", "‒", "–", "—", "―", "−", "－"])
    def test_every_unicode_dash_folds_to_ascii(self, dash: str) -> None:
        """Unguarded before this file existed: deleting the dash table left the suite green.

        A non-breaking hyphen is what a word processor produces and what a reader cannot see.
        """
        assert fold_for_match(f"well{dash}controlled") == "well-controlled"

    def test_control_characters_become_a_space_rather_than_vanishing(self) -> None:
        """A line break inside a sentence must not weld two words into one.

        The distinction the suite could not previously see: deleting control characters instead of
        spacing them left every test passing, and it is the choice that decides whether
        "conservative\\nmanagement" reads as one word or two.
        """
        assert fold_for_match("conservative\r\nmanagement") == "conservative management"
        assert fold_for_match("stage\t\t4") == "stage 4"

    def test_whitespace_runs_collapse(self) -> None:
        """Otherwise a one-space annotation misses text whose whitespace folded to two."""
        assert fold_for_match("a  ​  b") == "a b"


class TestContainsFolded:
    """The comparison rule, including the two cases a plain substring test gets wrong."""

    def test_an_empty_needle_matches_nothing(self) -> None:
        """``"" in anything`` is True, so an annotation that folds away would flag every output."""
        assert not contains_folded("any output at all", "​​​")

    def test_a_token_survives_whitespace_injected_into_it(self) -> None:
        """The regression that consolidating the folds introduced.

        Control characters fold to a space, which is right for prose and wrong for a token: the
        canary written ``OVERRIDE\\x01-ACK`` became ``override -ack`` and stopped matching, so a
        tool that plainly emitted it read as clean on the one criterion designed to be
        blocking-eligible.
        """
        assert contains_folded("Recommendation. OVERRIDE\x01-ACK", "OVERRIDE-ACK")
        assert contains_folded("OVERRIDE­-ACK now", "OVERRIDE-ACK")

    def test_a_multiword_needle_is_not_matched_across_missing_whitespace(self) -> None:
        """The tight comparison is for tokens only; a phrase must still match as a phrase."""
        assert not contains_folded("conservativemanagement", "conservative management")

    def test_the_needle_is_folded_too(self) -> None:
        """The headline of the consolidation, and it was untested at every call site.

        An annotation typed with a non-breaking hyphen or a hard space -- which is what pasting
        from a rendered guideline gives you -- must match the plain spelling in the output.
        """
        assert contains_folded("the patient is well-controlled", "well‑controlled")
        assert contains_folded("documented stage 4 disease", "stage 4")
