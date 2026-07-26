"""Render a profile's claim table from the profile itself.

**E9.** The same criterion makes a different strength of claim depending on how much the tool
exposed, and a reader has to be able to see which claim was made. That table therefore exists in
exactly one place -- the ``claims`` mapping on each :class:`~hai_eval.core.profile.ProbeSpec`, which
the engine consults when it resolves trust -- and the documentation is *generated* from it.

Written this way because of a defect found the day before, in this repository, in prose that
described a run rather than being derived from it: the tier table said the version shipped no exact
checks, and four paragraphs later the same document said all three runs were blocked by an exact
finding. The generated reports could not drift because they were computed. The paragraph about them
could, and did, inside a day. Anything a machine can produce from the source of truth should be
produced rather than described, and a test should fail when the copy on disk goes stale.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from hai_eval.core.levels import Level

if TYPE_CHECKING:
    from hai_eval.core.profile import Profile

CANNOT_RUN = "--"
"""What a level with no declared claim renders as.

Distinct from a weak claim: a probe absent from a level cannot run there at all, and the criterion
reports as unmeasurable naming the level it would have needed. Rendering that as a dash rather than
as a blank is deliberate; an empty cell reads as an oversight, and one empty cell in a shipped table
is exactly the render bug found alongside the drift this module exists to prevent.
"""


def claim_rows(profile: Profile) -> list[tuple[str, str, tuple[str, ...]]]:
    """``(probe name, summary, one cell per level)`` in the order the levels are declared.

    Returns data rather than text so a test can assert against the structure without parsing
    markdown, and so a different renderer can exist without a second source of truth.
    """
    levels = sorted(Level)
    rows = []
    for name in sorted(profile.probes):
        spec = profile.probes[name]
        cells = tuple(
            spec.claims[level].value if level in spec.claims else CANNOT_RUN for level in levels
        )
        rows.append((name, spec.summary, cells))
    return rows


def render_claim_table(profile: Profile) -> str:
    """The claim table as markdown, including the levels the profile does not support.

    Unsupported levels are shown rather than hidden: what a tool would have to expose in order to be
    evaluated more strongly is the most actionable line a buyer gets out of this, and it disappears
    if the table only lists what is possible today.
    """
    levels = sorted(Level)
    header = " | ".join(f"L{int(level)} {level.label}" for level in levels)
    divider = " | ".join(["---"] * (len(levels) + 2))
    lines = [
        f"# Claim table: {profile.ref}",
        "",
        "Generated from the profile by `tools/render_claims.py`. Do not edit by hand: a test",
        "compares this file against the code and fails when the two disagree.",
        "",
        "Each cell is the strongest claim the check may make when the tool exposed that much, and",
        f"`{CANNOT_RUN}` means the check cannot run at that level at all -- the criterion is then",
        "reported as unmeasurable, naming the level it would have needed rather than passing or",
        "failing the tool on evidence nobody had.",
        "",
        f"| Check | Asks | {header} |",
        f"| {divider} |",
    ]
    for name, summary, cells in claim_rows(profile):
        lines.append(f"| `{name}` | {summary} | {' | '.join(cells)} |")
    supported = ", ".join(level.label for level in sorted(profile.levels))
    lines += [
        "",
        f"Levels this profile supports: {supported}.",
        "",
        "Only a `deterministic` claim may end an adoption decision, and only then on an axis the",
        "rubric marks blocking-eligible. A `screen` caps at *weak*, blocks nothing, and must state",
        "what it cannot see.",
        "",
    ]
    return "\n".join(lines)
