"""Capability levels: how much a tool can prove about itself.

A level is a statement about the *evidence an integration exposes*, not about quality. It decides
what the harness is allowed to claim, which is the inversion this package exists for: rather than
requiring structured output and excluding everything else, a tool declares what it can produce and
the harness scales its claims to match.

Declared by the adapter, **verified** by the engine. An adapter that claims ``STRUCTURED`` and then
fails to produce a valid artifact does not crash and does not silently degrade -- it produces an
``Unmeasurable`` outcome naming the adapter as the cause, which is a finding about the integration
rather than about the tool's behavior.
"""

from __future__ import annotations

from enum import IntEnum


class Level(IntEnum):
    """What a single tool response managed to expose. Ordered; higher subsumes lower.

    Deliberately per RESPONSE rather than per adapter. A tool can degrade case by case -- emitting a
    clean artifact for three scenarios and falling back to prose on the fourth when it gets confused
    -- and a per-adapter declaration would hide exactly that behavior. The adapter declares a
    ceiling; each response declares what it actually reached; a gap between them is itself
    reportable.
    """

    PROSE = 0
    """Narrative text only. Screens only; nothing may block."""

    STRUCTURED = 1
    """A validated artifact: what the tool did, and which inputs it says it relied on."""

    GROUNDED = 2
    """STRUCTURED plus spans tying each cited input back to where it came from.

    Specified, not implemented in v0.2. It earns its place in the lattice because it constrains the
    STRUCTURED design -- it is why a cited basis is a list of identifiers rather than free prose,
    since spans attach to identified things.
    """

    @property
    def label(self) -> str:
        """Short human name, used in reports where a bare enum would be noise."""
        return {0: "prose", 1: "structured", 2: "grounded"}[int(self)]
