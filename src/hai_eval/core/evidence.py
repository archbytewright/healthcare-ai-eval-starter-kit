"""What a probe is handed: scenarios paired with responses, and the parsed artifacts.

Separating *running the tool* from *scoring what it produced* is what makes profiles possible at
all -- the same collected responses can be re-scored under a different rubric, and every probe is a
pure function that needs no tool to test.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from hai_eval.core.levels import Level
    from hai_eval.core.models import ToolResponse


@dataclass(frozen=True)
class Pair[A]:
    """One scenario, the response to it, and the validated artifact if there was one.

    Generic over the profile's artifact type so a probe reaches its own fields without casting,
    while the core stays ignorant of what those fields are.
    """

    scenario: Any
    """The profile's scenario subclass. Typed loosely here so the core stays domain-neutral."""
    response: ToolResponse
    artifact: A | None = None

    @property
    def level(self) -> Level:
        """The level this response actually reached, after verification."""
        return self.response.level


@dataclass(frozen=True)
class Evidence[A]:
    """Everything a probe needs, with the artifacts already validated."""

    pairs: tuple[Pair[A], ...]

    def at_least(self, level: Level) -> tuple[Pair[A], ...]:
        """Pairs whose response reached ``level`` or better.

        A probe that needs structure uses this rather than assuming: a tool may degrade case by
        case, and silently scoring the ones it managed while ignoring the ones it did not is how a
        subject shrinks its own denominator.
        """
        return tuple(p for p in self.pairs if p.level >= level)

    def scenarios_below(self, level: Level) -> tuple[str, ...]:
        """Scenario ids whose response fell short of ``level`` -- reported, never dropped."""
        return tuple(p.scenario.id for p in self.pairs if p.level < level)
