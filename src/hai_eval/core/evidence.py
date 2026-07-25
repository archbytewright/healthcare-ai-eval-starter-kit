"""What a probe is handed: scenarios paired with responses, and the parsed artifacts.

Separating *running the tool* from *scoring what it produced* is what makes profiles possible at
all -- the same collected responses can be re-scored under a different rubric, and every probe is a
pure function that needs no tool to test.

**A scenario carries SAMPLES, not a response.** A stochastic subject asked the same question twice
may answer differently, and one draw cannot distinguish a tool that is right from one that is right
*this time*. Repeated sampling is in the shape from the start rather than bolted on later: one
sample is the degenerate case, not the assumed one.

Multi-turn is deliberately absent. An exchange is much harder to score honestly -- the tool's own
earlier turns become part of the input, so a finding can no longer be attributed to the scenario
alone -- and single-turn should be right before that difficulty is taken on.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from hai_eval.core.levels import Level
    from hai_eval.core.models import ToolResponse


@dataclass(frozen=True)
class Sample[A]:
    """One draw from the tool for one scenario, with its artifact if it produced a valid one."""

    response: ToolResponse
    artifact: A | None
    level: Level
    """The level this draw was VERIFIED at, which may be lower than the one it claimed."""


@dataclass(frozen=True)
class Pair[A]:
    """One scenario and every sample drawn against it.

    Generic over the profile's artifact type so a probe reaches its own fields without casting,
    while the core stays ignorant of what those fields are.
    """

    scenario: Any
    """The profile's scenario subclass. Typed loosely here so the core stays domain-neutral."""
    samples: tuple[Sample[A], ...]

    @property
    def level(self) -> Level:
        """The WEAKEST level across samples.

        Conservative on purpose: a subject that produces a checkable artifact three times in four
        has not reliably produced one, and taking the best draw would let a tool buy a level with
        variance.
        """
        return min(s.level for s in self.samples)

    @property
    def artifacts(self) -> tuple[A, ...]:
        """Every valid artifact across samples, in draw order."""
        return tuple(s.artifact for s in self.samples if s.artifact is not None)

    @property
    def narratives(self) -> tuple[str, ...]:
        return tuple(s.response.narrative for s in self.samples)

    @property
    def sample_count(self) -> int:
        return len(self.samples)


@dataclass(frozen=True)
class Evidence[A]:
    """Everything a probe needs, with the artifacts already validated."""

    pairs: tuple[Pair[A], ...]
    samples_requested: int = 1

    def at_least(self, level: Level) -> tuple[Pair[A], ...]:
        """Pairs whose every sample reached ``level`` or better.

        The engine no longer pre-filters the whole run to its weakest response. That made one
        degraded scenario demote every criterion in the rubric, so a tool could delete a blocking
        finding by degrading something unrelated. Shortfalls are handled per criterion now, and
        scored as zeros rather than erased.
        """
        return tuple(p for p in self.pairs if p.level >= level)

    def scenarios_below(self, level: Level) -> tuple[str, ...]:
        """Scenario ids that fell short of ``level`` -- reported, never dropped."""
        return tuple(p.scenario.id for p in self.pairs if p.level < level)
