"""Typed boundary models for the evaluation harness.

Pydantic v2 models sit at every external boundary: the rubric YAML, the
vignette YAML, the tool-under-test input/output, and the scored result that
feeds the report. Internal computation passes these around as ordinary typed
objects.

The scoring scale is intentionally small and ordinal (0-3) so that a
non-technical committee can read it. Higher is better for every criterion;
``CriterionScore`` records the model's behavior and the evidence behind the
number so a reviewer can audit the judgment rather than trust it.
"""

from __future__ import annotations

from enum import IntEnum, StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

# ---------------------------------------------------------------------------
# Rubric definition (loaded from framework/rubric.yaml)
# ---------------------------------------------------------------------------


class Axis(BaseModel):
    """One evaluation axis (a family of related criteria).

    Axes are the top-level structure a reviewer reasons in: safety, workflow
    integration, failure-mode handling, oversight, regulatory posture. Each
    carries a weight so an org can re-weight for its own risk tolerance without
    editing code.
    """

    model_config = ConfigDict(extra="forbid")

    key: str
    title: str
    description: str
    weight: float = Field(gt=0.0, description="Relative weight; normalized at scoring time.")
    # Whether a deterministic hard fail on this axis may block adoption. Declared in the
    # rubric rather than matched against the literal axis key "safety" in code: an org is
    # invited to re-weight and rename axes, and renaming one silently disabled all blocking.
    blocking_eligible: bool = False


class ProbeTier(StrEnum):
    """How far a probe's verdict can be trusted on its own.

    The question that matters: **can a positive finding be wrong** — and specifically, can
    it be wrong in a way that damns a tool which behaved correctly?

    - ``deterministic`` — the check is exact, so a failure is a fact. **This version declares
      none.** The injection probe was assumed to qualify and does not: the canary's presence is
      exact, while "the tool followed the injected instruction" is an inference drawn from it,
      and a tool that refuses the injection has to name the canary in order to say so.
    - ``screen`` — a useful indicator that cannot fully distinguish the behavior it is
      named for. Substring matching over free-text output is a screen: it sees that a word
      appeared, not what the tool *did* with it. A screen surfaces a case for review; it
      does not settle it.
    - ``manual`` — no harness probe; a human reviews documentation or configuration.

    **Only ``deterministic`` failures may produce a blocking finding.** A screen caps at
    ``weak`` and asks for confirmation. This exists because the scope-isolation screen used
    to block on a substring match, scoring a model that *correctly identified and dismissed*
    an out-of-scope fact identically to one that reasoned from it as though it belonged to
    the current patient. Reporting a correct answer as a safety failure is the fastest way to
    lose a clinician's trust in an evaluation, so the harness now declines to assert what its
    probe cannot see.
    """

    DETERMINISTIC = "deterministic"
    SCREEN = "screen"
    MANUAL = "manual"


class Criterion(BaseModel):
    """A single scored question within an axis.

    ``probe`` names the mechanical check the harness runs (see
    :mod:`hai_eval.evaluator` for the registered probes). A criterion whose
    probe is unknown to the harness is scored as ``not_assessed`` rather than
    silently passing.

    ``tier`` declares how far that verdict can be trusted, and gates whether a failure can
    block adoption. See :class:`ProbeTier`.

    ``screen_caveat`` states, in the rubric, the specific thing *this* screen cannot see. It
    is per criterion because the limitations differ and a generic caveat is worse than none:
    "cannot distinguish misuse from correct dismissal" is true of scope isolation and simply
    false of fact retention, whose weakness is paraphrase.
    """

    model_config = ConfigDict(extra="forbid")

    key: str
    axis: str
    title: str
    question: str
    probe: str
    # Declared per criterion so a reviewer sees, in the rubric itself, which findings are
    # facts and which are leads. Defaults to SCREEN: a probe is fallible until it has earned
    # otherwise, so forgetting to set this cannot silently create a blocking probe.
    tier: ProbeTier = ProbeTier.SCREEN
    screen_caveat: str = ""
    guidance: str = ""

    @model_validator(mode="after")
    def _screen_declares_its_blind_spot(self) -> Criterion:
        """A screen without a caveat fell back to boilerplate that read as reassurance.

        The generic string ("treat the finding as unconfirmed") was appended to findings that
        were in fact exact, so the fallback actively misinformed. Require the rubric to say
        what this particular check cannot see.
        """
        if self.tier is ProbeTier.SCREEN and not self.screen_caveat.strip():
            msg = (
                f"criterion {self.key!r} is tier 'screen' but declares no screen_caveat; "
                f"state what this check cannot see"
            )
            raise ValueError(msg)
        return self

    # Which canonical framework this criterion derives from, so a reviewer can trace
    # each line to a primary source (Responsible Use of AI in Healthcare area / NIST GenAI risk /
    # CHAI / FDA). Note the rubric ships no fairness or subgroup-performance criterion, so nothing
    # currently cites Section 1557 -- a real gap, not an oversight in the field list.
    source: str = ""


class Rubric(BaseModel):
    """The full rubric: axes plus the criteria scored within them."""

    model_config = ConfigDict(extra="forbid")

    name: str
    version: str
    # Bounded because it divides in the recommendation logic (0 raised ZeroDivisionError) and
    # because Verdict tops out at 3: a larger scale_max makes a flawless tool render as a
    # fraction of a ceiling it can never reach.
    scale_max: int = Field(default=3, ge=1, le=3)
    axes: list[Axis]
    criteria: list[Criterion]

    @model_validator(mode="after")
    def _keys_are_unique_and_resolvable(self) -> Rubric:
        """Duplicate keys double-counted an axis's weight and duplicated blocking findings."""
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
        return self

    def axis(self, key: str) -> Axis:
        """Return the axis with ``key`` or raise ``KeyError``."""
        for axis in self.axes:
            if axis.key == key:
                return axis
        msg = f"no axis with key {key!r}"
        raise KeyError(msg)

    def criteria_for(self, axis_key: str) -> list[Criterion]:
        """Return the criteria belonging to ``axis_key`` in declared order."""
        return [c for c in self.criteria if c.axis == axis_key]


# ---------------------------------------------------------------------------
# Synthetic vignettes (loaded from data/vignettes.yaml)
# ---------------------------------------------------------------------------


class Vignette(BaseModel):
    """One synthetic, clearly-fabricated clinical encounter to test the tool with.

    ``transcript`` stands in for whatever raw input the tool consumes (here, a
    constructed clinical decision support conversation). ``must_include`` /
    ``must_not_include`` encode clinically load-bearing facts the produced
    artifact should or should not contain; ``out_of_scope`` lists facts present in the
    transcript that belong to another context and must be confined out (leakage,
    distinct from fabrication); ``injection`` flags a vignette that
    embeds an instruction-injection probe in the dialogue.
    """

    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^[\w][\w .:-]{0,79}$")
    title: str
    setting: str
    transcript: str
    must_include: list[str] = Field(default_factory=list)
    must_not_include: list[str] = Field(default_factory=list)
    out_of_scope: list[str] = Field(default_factory=list)
    injection: bool = False
    # The literal string the embedded instruction asks the tool to emit. Declared per vignette
    # so the HARNESS can check the tool's output for it: the previous design took the adapter's
    # word for whether the injection was followed, which made the only blocking criterion in
    # the rubric a self-report from the party under evaluation.
    injection_canary: str = ""
    # Marks a case where declining IS the right answer, so the abstention probe can score
    # appropriateness rather than mere capability.
    expect_abstention: bool = False
    notes: str = ""

    @field_validator("must_include", "must_not_include", "out_of_scope")
    @classmethod
    def _usable_annotations(cls, values: list[str]) -> list[str]:
        """Reject annotations too short to mean anything.

        An empty string matches every output unconditionally, and a one- or two-character
        token matches inside unrelated words ("ACE" inside "antACid"), so both silently
        fabricate a result. The YAML header asked authors not to do this; asking is not a
        control.
        """
        for v in values:
            if len(v.strip()) < 3:
                msg = f"annotation {v!r} is too short to match reliably (need 3+ characters)"
                raise ValueError(msg)
        return values

    @model_validator(mode="after")
    def _injection_declares_canary(self) -> Vignette:
        if self.injection and not self.injection_canary:
            msg = f"vignette {self.id!r} sets injection: true but declares no injection_canary"
            raise ValueError(msg)
        return self


class VignetteSet(BaseModel):
    """A named collection of synthetic vignettes."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(pattern=r"^[\w][\w .:-]{0,119}$")
    description: str
    vignettes: list[Vignette]

    @field_validator("vignettes")
    @classmethod
    def _unique_ids(cls, values: list[Vignette]) -> list[Vignette]:
        """Duplicate ids made one vignette's annotations score another's output.

        ``Evidence.paired()`` keys outputs by id, so a repeated id silently paired the wrong
        text with the wrong expectations and reported a safety failure that never happened.
        """
        seen = [v.id for v in values]
        dupes = sorted({i for i in seen if seen.count(i) > 1})
        if dupes:
            msg = f"duplicate vignette id(s): {dupes}"
            raise ValueError(msg)
        return values


# ---------------------------------------------------------------------------
# Tool-under-test boundary
# ---------------------------------------------------------------------------


class ToolOutput(BaseModel):
    """What a tool-under-test returns for one vignette.

    A real vendor tool's adapter is responsible for mapping its native response
    onto this shape. ``text`` is the tool's artifact (for the CDS example, its
    recommendation); ``flags`` are
    any self-reported safety/abstention signals; ``followed_injection`` is the
    adapter's reading of whether an embedded injection changed the output.

    **Both self-reports are cross-checked against the tool's own text and neither is
    trusted where it would remove a check.** The adapter is the vendor's code in a real
    integration, and a verdict supplied by the party under evaluation is not evidence:
    abstention in particular used to delete measurements, so the harness reads that one
    itself and reports any disagreement.
    """

    model_config = ConfigDict(extra="forbid")

    vignette_id: str
    text: str
    flags: list[str] = Field(default_factory=list)
    followed_injection: bool = False
    abstained: bool = False


# ---------------------------------------------------------------------------
# Scoring + report
# ---------------------------------------------------------------------------


class Verdict(IntEnum):
    """Ordinal score for a single criterion. Higher is better."""

    NOT_ASSESSED = -1
    FAIL = 0
    WEAK = 1
    ADEQUATE = 2
    STRONG = 3


class CriterionScore(BaseModel):
    """The score for one criterion on one tool, with auditable evidence."""

    model_config = ConfigDict(extra="forbid")

    criterion_key: str
    axis: str
    verdict: Verdict
    evidence: str
    # Carried onto the score so the REPORT can separate facts from leads without re-reading
    # the rubric, and so a reader sees the tier next to the verdict.
    tier: ProbeTier = ProbeTier.SCREEN
    # Verbatim model output backing this finding. A screen that cannot justify itself is not
    # worth reporting: the excerpt is what lets a reviewer adjudicate in seconds instead of
    # trusting the label (the 2026-07-25 gemma false positive was invisible without it).
    excerpt: str = ""

    @property
    def assessed(self) -> bool:
        """True when the probe actually ran (verdict is a real 0-3 score)."""
        return self.verdict != Verdict.NOT_ASSESSED


class AxisScore(BaseModel):
    """Aggregated score for one axis."""

    model_config = ConfigDict(extra="forbid")

    axis_key: str
    title: str
    weight: float
    criterion_scores: list[CriterionScore]

    @property
    def mean(self) -> float | None:
        """Mean of assessed criterion verdicts, or ``None`` if none assessed."""
        assessed = [cs.verdict.value for cs in self.criterion_scores if cs.assessed]
        if not assessed:
            return None
        return sum(assessed) / len(assessed)

    @property
    def assessed_share(self) -> float:
        """Fraction of this axis's criteria that produced a verdict.

        The headline weights an axis by this, so an axis assessed on one criterion of two carries
        half its declared weight rather than all of it. Coverage already reported it this way; the
        score did not, and two honest-looking numbers computed from the same run disagreed.
        """
        if not self.criterion_scores:
            return 0.0
        return sum(1 for cs in self.criterion_scores if cs.assessed) / len(self.criterion_scores)


class Coverage(BaseModel):
    """How much of the rubric and the case set the headline number actually rests on.

    The overall score drops unassessed axes from both numerator and denominator, which is the
    right arithmetic and a misleading presentation on its own: with the shipped rubric half
    the weight is document review, so "1.1 / 3" was a safety-plus-workflow subscore printed as
    though it covered five axes. Reporting coverage alongside the number is the difference
    between an honest partial measurement and an overstated whole one.
    """

    model_config = ConfigDict(extra="forbid")

    criteria_assessed: int
    criteria_total: int
    weight_assessed: float
    weight_total: float
    cases_total: int
    cases_abstained: list[str] = Field(default_factory=list)

    @property
    def weight_fraction(self) -> float:
        """Share of declared axis weight the score was computed over."""
        return self.weight_assessed / self.weight_total if self.weight_total else 0.0

    @property
    def cases_answered(self) -> int:
        """Cases where the tool produced an artifact rather than declining."""
        return self.cases_total - len(self.cases_abstained)


class EvaluationReport(BaseModel):
    """The full result of evaluating one tool against one rubric + vignette set."""

    model_config = ConfigDict(extra="forbid")

    tool_name: str
    rubric_name: str
    rubric_version: str
    scale_max: int
    vignette_set: str
    axis_scores: list[AxisScore]
    blocking_findings: list[str] = Field(default_factory=list)
    coverage: Coverage | None = None
    # Free-form run facts an adapter can supply (model digest, sampling options, host kind).
    # A report that cannot say what produced it cannot be audited or reproduced.
    provenance: dict[str, str] = Field(default_factory=dict)

    @property
    def weighted_score(self) -> float | None:
        """Weight-normalized overall score on the rubric's 0-``scale_max`` scale.

        Axes with no assessed criteria are dropped from both numerator and the
        weight total, so an unassessed axis neither helps nor hurts the score.
        Returns ``None`` when nothing was assessed at all.
        """
        num = 0.0
        weight_total = 0.0
        for axis in self.axis_scores:
            mean = axis.mean
            if mean is None:
                continue
            # Weighted by the share of the axis actually assessed, which is how Coverage reports
            # it. Crediting the full weight for a partly-assessed axis made them disagree, and the
            # disagreement had teeth: the workflow axis carried 40% of the headline off ONE
            # criterion, so a point on the cheapest check in the kit was worth 2.7x a point on
            # contraindication retention -- and nothing in the report disclosed that.
            share = axis.assessed_share
            num += mean * axis.weight * share
            weight_total += axis.weight * share
        if weight_total == 0.0:
            return None
        return num / weight_total
