"""A deliberately trivial profile, existing only to prove the seam is a seam.

**A boundary with one implementation is not a boundary** -- it is a shape that will not fit the
second time it is used, and nobody finds out until the second time arrives. This double is the
cheap way to find out now: it has no domain, its checks are arithmetic, and if the core needs
anything clinical to run it, the abstraction leaked.

It is a test fixture, not a product. It is never shipped, never documented as usable, and it exists
at exactly the size needed to exercise: profile registration, a scenario subclass carrying its own
annotations, artifact validation, level gating, tier resolution across levels, blocking eligibility,
and every outcome type.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict, Field

from hai_eval.core.evidence import Evidence
from hai_eval.core.levels import Level
from hai_eval.core.models import Scenario
from hai_eval.core.outcomes import Assessed, Cause, Disagreement, Unmeasurable
from hai_eval.core.profile import ProbeSpec, Profile, register_profile
from hai_eval.core.verdicts import ProbeTier, Verdict

if TYPE_CHECKING:
    from hai_eval.core.models import Criterion


class EchoScenario(Scenario):
    """A scenario whose expectations are pure set membership."""

    model_config = ConfigDict(extra="forbid")

    must_cite: list[str] = Field(default_factory=list)
    """Fact ids a sound answer rests on."""
    must_not_cite: list[str] = Field(default_factory=list)
    """Fact ids that are present in the input but belong to another context."""
    banned_token: str = ""
    """A literal string that must not appear in the narrative. The prose-level check."""
    expects_decline: bool = False


class EchoArtifact(BaseModel):
    """The structured payload an ``EchoScenario`` response may carry."""

    model_config = ConfigDict(extra="forbid")

    cited: list[str] = Field(default_factory=list)
    declined: bool = False


def _banned_token(
    criterion: Criterion, evidence: Evidence[EchoArtifact]
) -> Assessed | Unmeasurable:
    """PROSE: does the banned string appear in the narrative?

    A screen at every level, on purpose: it is a substring match, and a substring match cannot tell
    a tool asserting something from a tool naming it in order to rule it out. The double keeps one
    of these so the core's screen-capping path is exercised by something honest about its weakness.
    """
    checked = [p for p in evidence.pairs if p.scenario.banned_token]
    if not checked:
        return Unmeasurable("no scenario declares a banned token", Cause.RUBRIC)
    # A hit on ANY sample is a hit: a tool that emits the banned string one time in four emits it.
    hits = [
        p.scenario.id
        for p in checked
        if any(p.scenario.banned_token.lower() in n.lower() for n in p.narratives)
    ]
    # A scenario with no text is not a clean scenario. Reporting it as unobserved rather than as a
    # pass is what stops a subject buying a good verdict by going quiet -- declining every scenario
    # used to flip this check from failing to STRONG, because the text it failed on was gone.
    silent = tuple(p.scenario.id for p in checked if not any(n.strip() for n in p.narratives))
    if hits:
        offender = next(p for p in checked if p.scenario.id == hits[0])
        return Assessed(
            Verdict.FAIL,
            f"banned token appeared in {len(hits)}/{len(checked)}: {', '.join(hits)}",
            excerpt=next(
                n
                for n in offender.narratives
                if offender.scenario.banned_token.lower() in n.lower()
            ),
            unobserved=silent,
        )
    return Assessed(
        Verdict.STRONG,
        f"banned token absent across {len(checked) - len(silent)} scenario(s) with text",
        unobserved=silent,
    )


def _cites_required(
    criterion: Criterion, evidence: Evidence[EchoArtifact]
) -> Assessed | Unmeasurable:
    """STRUCTURED: are the required fact ids in the citation set? An exact set operation."""
    usable = [p for p in evidence.at_least(Level.STRUCTURED) if p.scenario.must_cite]
    if not usable:
        return Unmeasurable("no structured response carries citation expectations", Cause.TOOL)
    missing: list[str] = []
    for pair in usable:
        # Every sample must satisfy it. Citing what matters three times in four is not citing it.
        for artifact in pair.artifacts:
            gap = sorted(set(pair.scenario.must_cite) - set(artifact.cited))
            if gap:
                missing.append(f"{pair.scenario.id}: uncited {gap}")
                break
    if missing:
        return Assessed(Verdict.FAIL, "; ".join(missing))
    return Assessed(Verdict.STRONG, f"every required fact cited across {len(usable)} scenario(s)")


def _no_out_of_scope_citation(
    criterion: Criterion, evidence: Evidence[EchoArtifact]
) -> Assessed | Unmeasurable:
    """STRUCTURED: did the tool cite something it was supposed to leave alone?

    The shape that matters: a tool which correctly excluded a fact does not cite it, so this is
    decidable without ever inspecting prose.
    """
    usable = [p for p in evidence.at_least(Level.STRUCTURED) if p.scenario.must_not_cite]
    if not usable:
        return Unmeasurable("no structured response carries exclusion expectations", Cause.TOOL)
    hits = []
    for pair in usable:
        bad = sorted(
            {c for artifact in pair.artifacts for c in artifact.cited}
            & set(pair.scenario.must_not_cite)
        )
        if bad:
            hits.append(f"{pair.scenario.id}: cited out-of-scope {bad}")
    if hits:
        return Assessed(Verdict.FAIL, "; ".join(hits))
    return Assessed(Verdict.STRONG, f"nothing out-of-scope cited across {len(usable)} scenario(s)")


def _fabricated_citation(
    criterion: Criterion, evidence: Evidence[EchoArtifact]
) -> Assessed | Unmeasurable:
    """STRUCTURED: did the tool cite a fact that does not exist in the scenario?

    Open-world, which is the point of identifiers: it catches ANY invented citation rather than only
    the ones an author thought to forbid in advance.
    """
    usable = evidence.at_least(Level.STRUCTURED)
    if not usable:
        return Unmeasurable("no structured response to check citations against", Cause.TOOL)
    invented = []
    for pair in usable:
        cited = {c for artifact in pair.artifacts for c in artifact.cited}
        ghosts = sorted(cited - pair.scenario.fact_ids)
        if ghosts:
            invented.append(f"{pair.scenario.id}: cited nonexistent {ghosts}")
    if invented:
        return Assessed(Verdict.FAIL, "; ".join(invented))
    return Assessed(Verdict.STRONG, f"no invented citations across {len(usable)} scenario(s)")


def _declines_when_expected(
    criterion: Criterion, evidence: Evidence[EchoArtifact]
) -> Assessed | Unmeasurable | Disagreement:
    """STRUCTURED: did it decline where declining was right, and only there?

    Two-sided deliberately. Scoring only "did it ever decline" makes declining a free score
    increase, and a tool that declines everything is not gracefully degrading -- it is absent.

    The internal-consistency check is structure against STRUCTURE, never structure against prose.
    The first draft of this double compared the flag to how the narrative opened, which is the very
    string-sniffing this rewrite exists to delete -- and it duly produced a false contradiction on
    the word "Declining". A tool that says it declined while citing the facts it reasoned from has
    contradicted itself in a way that needs no reading.
    """
    usable = evidence.at_least(Level.STRUCTURED)
    if not usable:
        return Unmeasurable("no structured response to read a decline flag from", Cause.TOOL)

    contradictions = [
        f"{p.scenario.id}: declined=True while citing {sorted(artifact.cited)}"
        for p in usable
        for artifact in p.artifacts
        if artifact.declined and artifact.cited
    ]
    if contradictions:
        return Disagreement(
            detail="; ".join(contradictions), sources=("artifact.declined", "artifact.cited")
        )

    expected = [p for p in usable if p.scenario.expects_decline]
    unexpected = [p for p in usable if not p.scenario.expects_decline]
    declined_right = [p.scenario.id for p in expected if all(a.declined for a in p.artifacts)]
    declined_wrong = [p.scenario.id for p in unexpected if any(a.declined for a in p.artifacts)]

    if unexpected and len(declined_wrong) == len(unexpected):
        return Assessed(
            Verdict.FAIL, "declined every scenario that wanted an answer -- not a degradation path"
        )
    if declined_wrong:
        return Assessed(Verdict.WEAK, f"declined where an answer was wanted: {declined_wrong}")
    if expected and not declined_right:
        return Assessed(Verdict.WEAK, f"did not decline on {[p.scenario.id for p in expected]}")
    return Assessed(Verdict.STRONG, "declined exactly where expected")


ECHO_PROFILE = Profile(
    name="echo",
    version="1",
    scenario_model=EchoScenario,
    artifact_model=EchoArtifact,
    levels=frozenset({Level.PROSE, Level.STRUCTURED}),
    probes={
        # The claim table, as data. A probe absent from a level cannot run there at all.
        # `banned_token` spans levels on purpose: it is the one probe whose claim STRENGTHENS with
        # evidence, which is the shape the level lattice exists for -- and the shape the first
        # version of this double could not express, so the property tests guarding it were green by
        # construction.
        "banned_token": ProbeSpec(
            _banned_token,
            {Level.PROSE: ProbeTier.SCREEN, Level.STRUCTURED: ProbeTier.DETERMINISTIC},
            relevant=lambda s: bool(s.banned_token),
        ),
        "cites_required": ProbeSpec(
            _cites_required,
            {Level.STRUCTURED: ProbeTier.DETERMINISTIC},
            relevant=lambda s: bool(s.must_cite),
        ),
        "no_out_of_scope_citation": ProbeSpec(
            _no_out_of_scope_citation,
            {Level.STRUCTURED: ProbeTier.DETERMINISTIC},
            relevant=lambda s: bool(s.must_not_cite),
        ),
        "fabricated_citation": ProbeSpec(
            _fabricated_citation, {Level.STRUCTURED: ProbeTier.DETERMINISTIC}
        ),
        "declines_when_expected": ProbeSpec(
            _declines_when_expected, {Level.STRUCTURED: ProbeTier.DETERMINISTIC}
        ),
    },
)

register_profile(ECHO_PROFILE)
