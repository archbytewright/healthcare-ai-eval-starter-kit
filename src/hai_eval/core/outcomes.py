"""What a probe concluded, including the ways it can conclude nothing.

The design fault this replaces: "not measured" used to be expressed by *absence* -- a criterion
simply left the denominator -- which is how a tool deleted its own checks. Decline every scenario
and each emptied probe silently dropped out of the mean, so refusing to answer removed checks
instead of failing them, and the result was a maximum score with a pilot recommendation.

**Absence is not a report.** An outcome that could not be reached says so, says why, and says who
prevented it.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from hai_eval.core.levels import Level
    from hai_eval.core.verdicts import ProbeTier, Verdict


class Cause(StrEnum):
    """Who prevented a measurement. This is the scoring rule, expressed as a type."""

    RUBRIC = "rubric"
    """No harness check exists for this criterion -- it needs document or governance review.

    Excluded from the score and disclosed. The rubric asked a question no automated probe answers,
    which is a property of the rubric and says nothing about the tool.
    """

    TOOL = "tool"
    """The tool produced nothing checkable: it declined, or exposed too little to test.

    **Counts against the tool.** A subject does not get to shrink its own denominator. Note the
    judgment about whether an absence is excusable belongs to the PROBE, not here -- declining a
    scenario that expected a deferral is correct behavior, and the probe reports that by excluding
    the scenario rather than by returning this cause.
    """

    ADAPTER = "adapter"
    """The integration could not produce what it claimed -- a declared level it failed to reach.

    Scored like TOOL, reported separately, because "your vendor's connector is broken" and "your
    vendor's model is unsafe" are different conversations with different owners.
    """


@dataclass(frozen=True)
class Assessed:
    """The probe reached a verdict.

    ``tier`` may be lowered by the probe for this finding only (never raised -- see
    ``engine.effective_tier``). ``level_used`` records the evidence depth the verdict actually
    rests on, so a reader can tell a structural fact from a screen over prose.
    """

    verdict: Verdict
    evidence: str
    excerpt: str = ""
    tier: ProbeTier | None = None
    level_used: Level | None = None


@dataclass(frozen=True)
class Unmeasurable:
    """The probe could not reach a verdict, and names why and whose doing it was."""

    reason: str
    cause: Cause


@dataclass(frozen=True)
class Disagreement:
    """Two sources that should agree do not.

    Its own outcome rather than a warning appended to some other criterion's evidence string. Both
    2026-07-25 review rounds found cross-checks that detected a contradiction and then did nothing
    with it -- a glyph on a criterion that could not block. Detection without consequence is a log
    line, not a control, so a disagreement is a first-class result a criterion can be scored on.
    """

    detail: str
    sources: tuple[str, ...]
    excerpt: str = ""


Outcome = Assessed | Unmeasurable | Disagreement
