"""The domain seam: what a profile must supply, and how one is registered.

The core evaluates; a profile knows what is being evaluated. Everything field-specific -- the shape
of a scenario's annotations, the shape of the tool's artifact, the checks that read them -- lives
behind this boundary. Swapping the profile swaps the domain without touching the engine.

Deliberately one dictionary. No entry points, no discovery, no configuration-driven registry: those
are for a plugin ecosystem, and this has one real profile and one test double. A seam earns
machinery when it has consumers, not when it might.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from hai_eval.core.levels import Level
from hai_eval.core.verdicts import TIER_ORDER, ProbeTier

if TYPE_CHECKING:
    from pydantic import BaseModel

    from hai_eval.core.evidence import Evidence
    from hai_eval.core.models import Criterion
    from hai_eval.core.outcomes import Outcome

Probe = Callable[["Criterion", "Evidence[Any]"], "Outcome"]


@dataclass(frozen=True)
class ProbeSpec:
    """A check, plus the strength of claim it can make at each evidence level.

    ``claims`` **is** the claim table from the design spec, stored as data rather than described in
    prose. Documentation renders from it and a test asserts the code agrees with it, because a table
    that lives only in a document drifts from the code that is supposed to implement it -- both
    2026-07-25 review rounds found exactly that kind of drift.

    A probe absent from a level cannot run there at all: the criterion reports as unmeasurable,
    naming the level it would have needed.
    """

    fn: Probe
    claims: Mapping[Level, ProbeTier]
    summary: str = ""
    """One line naming what this check asks, for the rendered claim table.

    Lives beside the claims it describes so the documentation is generated from the same object the
    engine consults. Prose written *about* a table drifts from it -- the public README asserted a
    verdict its own generated reports had stopped issuing, and survived a regeneration because it
    was hand-written rather than derived.
    """
    relevant: Callable[[Any], bool] = lambda _scenario: True
    """Which scenarios this check applies to at all.

    Needed to tell two absences apart, which the first draft conflated and mis-blamed. If NO
    scenario is relevant, the scenario set never asked the question and that is the RUBRIC's gap. If
    relevant scenarios exist but the tool exposed too little on them, that is the TOOL's. Scoring a
    structurally perfect tool zero because the author annotated nothing was the bug.
    """

    def __post_init__(self) -> None:
        if not self.claims:
            msg = "a probe must declare at least one level it can make a claim at"
            raise ValueError(msg)

    @property
    def minimum_level(self) -> Level:
        return min(self.claims)

    def tier_at(self, level: Level) -> ProbeTier | None:
        """The strongest claim this probe may make given the evidence actually available."""
        usable = [lvl for lvl in self.claims if lvl <= level]
        return self.claims[max(usable)] if usable else None


@dataclass(frozen=True)
class Profile:
    """A domain plugged into the core.

    ``scenario_model`` extends :class:`~hai_eval.core.models.Scenario` with the domain's annotation
    vocabulary. ``artifact_model`` is what a structured response must validate against; a profile
    that only supports prose leaves it ``None``.
    """

    name: str
    version: str
    scenario_model: type[BaseModel]
    artifact_model: type[BaseModel] | None
    probes: Mapping[str, ProbeSpec]
    levels: frozenset[Level]

    @property
    def ref(self) -> str:
        """The ``name@version`` string a rubric names."""
        return f"{self.name}@{self.version}"

    @property
    def max_level(self) -> Level:
        return max(self.levels)


_REGISTRY: dict[str, Profile] = {}


VERIFIABLE_LEVELS = frozenset({Level.PROSE, Level.STRUCTURED})
"""Levels the engine can actually verify a claim about today.

``GROUNDED`` is specified and unimplemented, and an unimplemented level was being rubber-stamped:
an adapter could declare it, ship an ordinary structured payload with no spans, and be believed --
in the package whose whole thesis is that a claimed level is verified rather than trusted. Declaring
a level with no verifier is a registration error, and this set is what to extend when spans land.
"""


def register_profile(profile: Profile) -> Profile:
    """Register under ``name@version``. Re-registration is an error, not a silent swap."""
    if profile.ref in _REGISTRY:
        msg = f"profile {profile.ref!r} is already registered"
        raise ValueError(msg)
    if profile.artifact_model is None and Level.STRUCTURED in profile.levels:
        msg = f"profile {profile.ref!r} claims STRUCTURED but supplies no artifact_model"
        raise ValueError(msg)
    unverifiable = sorted(lvl.label for lvl in profile.levels - VERIFIABLE_LEVELS)
    if unverifiable:
        msg = (
            f"profile {profile.ref!r} declares level(s) {unverifiable} that the engine cannot "
            f"verify; a level nobody can check is a claim taken on trust"
        )
        raise ValueError(msg)
    _REGISTRY[profile.ref] = profile
    return profile


def get_profile(ref: str) -> Profile:
    """Resolve ``name@version``, or raise with the list of what is available."""
    try:
        return _REGISTRY[ref]
    except KeyError:
        msg = f"unknown profile {ref!r}; registered: {sorted(_REGISTRY) or '(none)'}"
        raise KeyError(msg) from None


def registered_profiles() -> frozenset[str]:
    return frozenset(_REGISTRY)


def weakest(*tiers: ProbeTier | None) -> ProbeTier:
    """The least trusted of several tier claims.

    Trust is the minimum of what the rubric declared, what the probe can support at the evidence
    level available, and what the probe said about this particular finding. A probe may confess to
    being less reliable than the rubric assumed; it can never award itself more, because that would
    move the decision about what may end a procurement conversation out of the rubric -- where a
    reviewer reads it -- and into code.
    """
    present = [t for t in tiers if t is not None]
    if not present:
        return ProbeTier.SCREEN
    return max(present, key=lambda t: TIER_ORDER[t])
