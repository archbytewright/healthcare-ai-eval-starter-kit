"""Domain-neutral boundary models.

No subject-matter vocabulary may appear here -- enforced by ``tests/test_core_boundary.py``, not by
discipline. The words are deliberately generic: a *scenario* is a unit of input, a *fact* is a
labeled piece of that input, a *response* is what the tool produced. What those mean in a
particular field is a profile's business.

Facts carry IDs, and that is the load-bearing decision of v0.2. A declared basis expressed as free
text has to be compared against expectations by matching strings, which is the exact failure this
rewrite exists to end: two phrasings of the same thing are the same thing to a reader and different
strings to a matcher, and closing that gap is what cue lists were for. Scenarios are authored, so
their ground truth is ours by construction -- label the facts, render them identified into the
prompt, and require the tool to cite identifiers. Every downstream check is then a set operation
with no matching anywhere.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator

from hai_eval.core.levels import Level
from hai_eval.core.verdicts import ProbeTier, Verdict

_ID = r"^[A-Za-z0-9][\w.:-]{0,79}$"


class Fact(BaseModel):
    """One labeled piece of a scenario's input."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^[A-Za-z0-9][\w-]{0,15}$")
    text: str = Field(min_length=1)
    cue: str = ""
    """A short literal by which this fact might be recognized in free text.

    For level-0 screening only, and it is the honest expression of what that level can do: with no
    identifiers to work with, recognizing a fact in prose means matching a string, and a string
    match cannot tell a paraphrase from an omission. Optional, because a fact nobody needs to spot
    in prose does not need one, and an empty cue is treated as "cannot be screened for" rather than
    as "never appears" -- the difference between those two was how an absence used to read as a
    pass.
    """


class Scenario(BaseModel):
    """One unit of input the tool is run against, plus the labeled facts inside it.

    Profiles subclass this to add their own annotation vocabulary -- what "required" or "forbidden"
    means in that subject area. The core needs only the identity and the facts.
    """

    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=_ID)
    facts: list[Fact] = Field(default_factory=list)
    notes: str = ""

    @model_validator(mode="after")
    def _fact_ids_unique(self) -> Scenario:
        seen = [f.id for f in self.facts]
        dupes = sorted({i for i in seen if seen.count(i) > 1})
        if dupes:
            msg = f"scenario {self.id!r} repeats fact id(s): {dupes}"
            raise ValueError(msg)
        return self

    @property
    def fact_ids(self) -> frozenset[str]:
        """The ground-truth set every citation is checked against."""
        return frozenset(f.id for f in self.facts)

    def fact(self, fact_id: str) -> Fact | None:
        return next((f for f in self.facts if f.id == fact_id), None)


class ScenarioSet(BaseModel):
    """A named collection of scenarios."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(pattern=r"^[\w][\w .:-]{0,119}$")
    description: str = ""
    scenarios: list[Scenario] = Field(min_length=1)
    """At least one. A run over nothing reported every criterion as the rubric's gap and returned a
    clean report -- in a package whose thesis is that an absence is not a result."""

    @model_validator(mode="after")
    def _ids_unique(self) -> ScenarioSet:
        """Duplicate ids used to pair one scenario's expectations with another's output."""
        seen = [s.id for s in self.scenarios]
        dupes = sorted({i for i in seen if seen.count(i) > 1})
        if dupes:
            msg = f"duplicate scenario id(s): {dupes}"
            raise ValueError(msg)
        return self


class ToolResponse(BaseModel):
    """What the tool produced for one scenario.

    ``narrative`` is always present and is the only thing an excerpt is ever quoted from.
    ``artifact`` is the profile-defined structured payload, validated by the engine rather than
    trusted -- ``level`` is a CLAIM until that validation passes.

    Note what is absent: no ``followed_injection``, no ``abstained``. Those were booleans the
    adapter asserted about the subject it was adapting, and for a vendor integration the adapter is
    the vendor's code. A self-report from the party under evaluation is not evidence; anything of
    that kind is now derived from the artifact by a probe.
    """

    model_config = ConfigDict(extra="forbid")

    scenario_id: str
    narrative: str = ""
    level: Level = Level.PROSE
    artifact: dict[str, object] | None = None


class Axis(BaseModel):
    """A family of related criteria, weighted."""

    model_config = ConfigDict(extra="forbid")

    key: str = Field(pattern=_ID)
    title: str
    description: str = ""
    weight: float = Field(gt=0.0, le=1000.0, allow_inf_nan=False)
    """Bounded and finite: an infinite weight made the whole headline NaN, which then compared
    False against every threshold in both directions rather than failing loudly."""
    blocking_eligible: bool = False
    """Whether a deterministic hard fail here may block adoption.

    Declared in the rubric rather than matched against an axis named "safety" in code. The literal
    string match meant renaming an axis silently disabled every blocking finding, and no test could
    see it because all the deterministic criteria happened to live under that one name.
    """


class Criterion(BaseModel):
    """One scored question, and the check that answers it."""

    model_config = ConfigDict(extra="forbid")

    key: str = Field(pattern=_ID)
    axis: str = Field(pattern=_ID)
    title: str
    question: str
    probe: str
    tier: ProbeTier = ProbeTier.SCREEN
    """Fail-safe default: a check is fallible until it has earned otherwise, so a forgotten
    declaration cannot silently create something that blocks."""
    screen_caveat: str = ""
    guidance: str = ""
    source: str = ""

    @model_validator(mode="after")
    def _screen_states_its_blind_spot(self) -> Criterion:
        """A screen with no caveat fell back to boilerplate that read as reassurance.

        The generic string ("treat this finding as unconfirmed") got appended to findings that were
        in fact exact, so the fallback actively misinformed. Make the rubric say what THIS check
        cannot see, or refuse to load.
        """
        if self.tier is ProbeTier.SCREEN and not self.screen_caveat.strip():
            msg = (
                f"criterion {self.key!r} is tier 'screen' but declares no screen_caveat; "
                f"state what this check cannot see"
            )
            raise ValueError(msg)
        return self


class Rubric(BaseModel):
    """Axes plus the criteria scored within them, for one profile."""

    model_config = ConfigDict(extra="forbid")

    name: str
    version: str
    profile: str
    """``name@version`` of the domain profile this rubric is written against."""
    scale_max: int = Field(default=3, ge=1, le=3)
    """Bounded: it divides in the recommendation logic, and ``Verdict`` tops out at 3, so a larger
    ceiling would render a flawless tool as a fraction of something unreachable."""
    axes: list[Axis] = Field(min_length=1)
    criteria: list[Criterion] = Field(min_length=1)

    @model_validator(mode="after")
    def _keys_unique_and_resolvable(self) -> Rubric:
        axis_keys = [a.key for a in self.axes]
        dupe_axes = sorted({k for k in axis_keys if axis_keys.count(k) > 1})
        if dupe_axes:
            msg = f"duplicate axis key(s): {dupe_axes}"
            raise ValueError(msg)
        crit_keys = [c.key for c in self.criteria]
        dupe_crits = sorted({k for k in crit_keys if crit_keys.count(k) > 1})
        if dupe_crits:
            msg = f"duplicate criterion key(s): {dupe_crits}"
            raise ValueError(msg)
        dangling = sorted({c.axis for c in self.criteria} - set(axis_keys))
        if dangling:
            msg = f"criteria reference undeclared axes: {dangling}"
            raise ValueError(msg)
        return self

    def axis(self, key: str) -> Axis:
        for axis in self.axes:
            if axis.key == key:
                return axis
        msg = f"no axis with key {key!r}"
        raise KeyError(msg)

    def criteria_for(self, axis_key: str) -> list[Criterion]:
        return [c for c in self.criteria if c.axis == axis_key]


class CriterionScore(BaseModel):
    """The scored result for one criterion, carrying everything a reader needs to audit it."""

    model_config = ConfigDict(extra="forbid")

    criterion_key: str
    axis: str
    verdict: Verdict | None
    """``None`` when the criterion was not measurable -- see ``unmeasurable_cause``."""
    evidence: str
    tier: ProbeTier
    excerpt: str = ""
    level_used: Level | None = None
    unmeasurable_cause: str = ""
    scenarios_relevant: tuple[str, ...] = ()
    """Every scenario this check applies to. The denominator, stated rather than implied."""
    scenarios_judged: tuple[str, ...] = ()
    """The ones it actually reached a view on."""
    scenarios_unjudged: tuple[str, ...] = ()
    """The ones it could not. ``judged`` and ``unjudged`` must partition ``relevant`` exactly --
    enforced in :func:`hai_eval.core.engine.check_conservation`, because every disappearing-evidence
    bug this core has had was something leaving the calculation with nobody deciding it should."""
    counts_against_tool: bool = False
    """True when an absence is the tool's or the integration's doing.

    The distinction the whole scoring model turns on: a criterion the rubric cannot automate leaves
    the score alone, while a criterion the tool prevented from running is scored against it. Without
    this, declining was a way to delete checks rather than fail them.
    """

    @property
    def assessed(self) -> bool:
        return self.verdict is not None
