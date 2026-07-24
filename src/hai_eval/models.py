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

from enum import IntEnum

from pydantic import BaseModel, ConfigDict, Field

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


class Criterion(BaseModel):
    """A single scored question within an axis.

    ``probe`` names the mechanical check the harness runs (see
    :mod:`hai_eval.evaluator` for the registered probes). A criterion whose
    probe is unknown to the harness is scored as ``not_assessed`` rather than
    silently passing.
    """

    model_config = ConfigDict(extra="forbid")

    key: str
    axis: str
    title: str
    question: str
    probe: str
    guidance: str = ""
    # Which canonical framework this criterion derives from, so a reviewer can trace
    # each line to a primary source (RUAIH area / NIST GenAI risk / CHAI / FDA / 1557).
    source: str = ""


class Rubric(BaseModel):
    """The full rubric: axes plus the criteria scored within them."""

    model_config = ConfigDict(extra="forbid")

    name: str
    version: str
    scale_max: int = 3
    axes: list[Axis]
    criteria: list[Criterion]

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

    id: str
    title: str
    setting: str
    transcript: str
    must_include: list[str] = Field(default_factory=list)
    must_not_include: list[str] = Field(default_factory=list)
    out_of_scope: list[str] = Field(default_factory=list)
    injection: bool = False
    notes: str = ""


class VignetteSet(BaseModel):
    """A named collection of synthetic vignettes."""

    model_config = ConfigDict(extra="forbid")

    name: str
    description: str
    vignettes: list[Vignette]


# ---------------------------------------------------------------------------
# Tool-under-test boundary
# ---------------------------------------------------------------------------


class ToolOutput(BaseModel):
    """What a tool-under-test returns for one vignette.

    A real vendor tool's adapter is responsible for mapping its native response
    onto this shape. ``text`` is the tool's artifact (for the CDS example, its
    recommendation); ``flags`` are
    any self-reported safety/abstention signals; ``followed_injection`` records
    whether an embedded injection probe changed the output (the adapter detects
    this, not the harness, because only the adapter knows the tool's contract).
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
            num += mean * axis.weight
            weight_total += axis.weight
        if weight_total == 0.0:
            return None
        return num / weight_total
