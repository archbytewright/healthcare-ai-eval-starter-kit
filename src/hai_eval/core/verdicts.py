"""The ordinal verdict scale and the trust tier attached to a check.

Separated from ``outcomes`` so the two ideas stay distinct: a **verdict** is how well the subject
did, a **tier** is how far the check's answer can be trusted. Conflating them is what let a
substring match end a procurement conversation.
"""

from __future__ import annotations

from enum import IntEnum, StrEnum


class Verdict(IntEnum):
    """Ordinal score for one criterion. Higher is better."""

    FAIL = 0
    WEAK = 1
    ADEQUATE = 2
    STRONG = 3

    @property
    def label(self) -> str:
        return {0: "fail", 1: "weak", 2: "adequate", 3: "strong"}[int(self)]


class ProbeTier(StrEnum):
    """How far a check's verdict can be trusted -- a claim about the CHECK, not the subject.

    - ``DETERMINISTIC`` -- exact, and the claim is narrow enough to be a fact. Only these may block.
    - ``SCREEN`` -- an indicator that cannot fully separate the behavior it names from its opposite.
      Caps at ``WEAK``, never blocks, and must declare what it cannot see.
    - ``MANUAL`` -- no automated check; a human reviews documentation or configuration.

    The v0.1 lesson, kept here because it is the whole reason this enum exists: a check earns
    ``DETERMINISTIC`` by the narrowness of its CLAIM, not by the crispness of its implementation.
    "The canary string is present" is exact. "The tool followed the injected instruction" is an
    inference from it, and treating the second as the first hard-failed a tool that named the canary
    in order to refuse it.
    """

    DETERMINISTIC = "deterministic"
    SCREEN = "screen"
    MANUAL = "manual"


TIER_ORDER: dict[ProbeTier, int] = {
    ProbeTier.DETERMINISTIC: 0,
    ProbeTier.SCREEN: 1,
    ProbeTier.MANUAL: 2,
}
