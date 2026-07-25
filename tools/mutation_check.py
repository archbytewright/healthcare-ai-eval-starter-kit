"""E7 — assert the suite actually bites, by breaking things on purpose.

A green suite proves nothing on its own. The 2026-07-25 review found twenty-four invariants whose
tests passed happily while the invariant was deleted, including the one guarding the only check
permitted to block adoption. The fix is not more tests, it is a way to *know* which tests are load
bearing, so every invariant this design rests on is paired here with the edit that must break it.

Each entry is a claim: "if you make this change, the suite must go red." An entry that survives is
either a missing test or a genuinely equivalent mutation, and the difference matters -- so surviving
entries are reported rather than hidden, and an entry known to be equivalent says so in its note.

Runs on a COPY of the tree. An earlier hand-run mutated the working tree and relied on
``git checkout`` to undo it, which silently failed on files git had never seen. Nothing here touches
the repository.

    uv run python tools/mutation_check.py            # all mutations
    uv run python tools/mutation_check.py --list     # just show them
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Mutation:
    """One deliberate break, and the invariant it is testing the tests for."""

    name: str
    invariant: str
    path: str
    find: str
    replace: str
    equivalent: bool = False
    note: str = ""


MUTATIONS: tuple[Mutation, ...] = (
    Mutation(
        name="screen-can-block",
        invariant="a fallible check may never end a procurement conversation",
        path="src/hai_eval/core/engine.py",
        find="and score.tier is ProbeTier.DETERMINISTIC",
        replace="and score.tier is not None",
        equivalent=True,
        note=(
            "Equivalent while the cap holds: nothing below DETERMINISTIC can carry a FAIL by the "
            "time the gate reads it, so no test can tell the two apart. Kept as defence in depth "
            "against a future edit that moves the cap, and declared equivalent rather than left "
            "looking like a guarded invariant -- the cap itself is guarded by screen-cap-removed."
        ),
    ),
    Mutation(
        name="axis-eligibility-ignored",
        invariant="blocking is opt-in per axis, declared in the rubric",
        path="src/hai_eval/core/engine.py",
        find="and axis.blocking_eligible",
        replace="and True",
    ),
    Mutation(
        name="screen-cap-removed",
        invariant="a screen's hard fail caps at weak",
        path="src/hai_eval/core/engine.py",
        find="verdict = Verdict.WEAK if verdict == Verdict.FAIL else verdict",
        replace="pass",
    ),
    Mutation(
        name="withholding-is-free",
        invariant="a tool cannot raise its score by producing less",
        path="src/hai_eval/core/engine.py",
        find="if cs.verdict is not None or cs.counts_against_tool",
        replace="if cs.verdict is not None",
    ),
    Mutation(
        name="rubric-gap-punishes-the-tool",
        invariant="a criterion the rubric cannot automate must not be scored against the subject",
        path="src/hai_eval/core/engine.py",
        find="counts_against_tool=outcome.cause in (Cause.TOOL, Cause.ADAPTER),",
        replace="counts_against_tool=True,",
    ),
    Mutation(
        name="claimed-level-trusted",
        invariant="a declared capability level is verified, not believed",
        path="src/hai_eval/core/engine.py",
        find="    except ValidationError as exc:",
        replace=(
            "    except ValidationError as exc:  # noqa\n"
            '        return claimed, None, ""\n    if False:'
        ),
    ),
    Mutation(
        name="level-gate-removed",
        invariant="a probe cannot run below the evidence level it requires",
        path="src/hai_eval/core/profile.py",
        find="usable = [lvl for lvl in self.claims if lvl <= level]",
        replace="usable = list(self.claims)",
    ),
    Mutation(
        name="tier-can-be-raised",
        invariant="a probe may lower its own trust, never raise it",
        path="src/hai_eval/core/profile.py",
        find="return max(present, key=lambda t: TIER_ORDER[t])",
        replace="return min(present, key=lambda t: TIER_ORDER[t])",
    ),
    Mutation(
        name="profile-mismatch-allowed",
        invariant="a rubric may only be run against the profile it targets",
        path="src/hai_eval/core/engine.py",
        find="    if rubric.profile != profile.ref:",
        replace="    if False:",
    ),
    Mutation(
        name="screen-needs-no-caveat",
        invariant="a screen must declare what it cannot see",
        path="src/hai_eval/core/models.py",
        find="if self.tier is ProbeTier.SCREEN and not self.screen_caveat.strip():",
        replace="if False:",
    ),
    Mutation(
        name="duplicate-scenario-ids-allowed",
        invariant="scenario ids are unique, so expectations pair with the right response",
        path="src/hai_eval/core/models.py",
        find='            msg = f"duplicate scenario id(s): {dupes}"',
        replace="            msg = None  # type: ignore[assignment]\n            dupes = []",
    ),
    Mutation(
        name="duplicate-fact-ids-allowed",
        invariant="fact ids are unique, so a citation resolves to one thing",
        path="src/hai_eval/core/models.py",
        find='            msg = f"scenario {self.id!r} repeats fact id(s): {dupes}"',
        replace='            dupes = []\n            msg = ""',
    ),
    Mutation(
        name="dangling-axis-allowed",
        invariant="every criterion belongs to a declared axis",
        path="src/hai_eval/core/models.py",
        find="        dangling = sorted({c.axis for c in self.criteria} - set(axis_keys))",
        replace="        dangling = []",
    ),
    Mutation(
        name="boundary-guard-vacuous",
        invariant="the domain-vocabulary check actually inspects files",
        path="tests/test_core_boundary.py",
        find='    return sorted({word for word in FORBIDDEN if re.search(rf"\\b{word}", lowered)})',
        replace="    return []",
        note="mutating a test to prove the test is not vacuous",
    ),
    Mutation(
        name="run-wide-level-gate",
        invariant="evidence level is resolved per criterion, not from the run's weakest response",
        path="src/hai_eval/core/engine.py",
        find="    usable = tuple(p for p in relevant if spec.tier_at(p.level) is not None)",
        replace=(
            "    _worst = min((p.level for p in evidence.pairs), default=Level.PROSE)\n"
            "    usable = tuple(p for p in relevant if spec.tier_at(_worst) is not None)"
        ),
    ),
    Mutation(
        name="unknown-probe-silently-dropped",
        invariant="a check the profile does not supply is a load error, not a quiet exclusion",
        path="src/hai_eval/core/engine.py",
        find="    if unknown:",
        replace="    if False:",
    ),
    Mutation(
        name="disagreement-skips-the-cap",
        invariant="every verdict passes through one capping path, whatever its outcome type",
        path="src/hai_eval/core/engine.py",
        find="    if tier is not ProbeTier.DETERMINISTIC and verdict < Verdict.STRONG:",
        replace="    if tier is ProbeTier.SCREEN and verdict < Verdict.STRONG:",
    ),
    Mutation(
        name="relabelling-allowed",
        invariant="a response must answer the scenario it was handed",
        path="src/hai_eval/core/engine.py",
        find="            if response.scenario_id != scenario.id:",
        replace="            if False:",
    ),
    Mutation(
        name="conservation-check-removed",
        invariant="nothing leaves the calculation between rubric and report",
        path="src/hai_eval/core/engine.py",
        find="    check_conservation(report, rubric)",
        replace="    pass",
    ),
    Mutation(
        name="criterion-silently-dropped",
        invariant="every declared criterion appears in the report",
        path="src/hai_eval/core/engine.py",
        find="            criterion_scores.append(score)",
        replace=(
            "            if score.verdict is not None:\n"
            "                criterion_scores.append(score)"
        ),
    ),
    Mutation(
        name="scenario-partition-broken",
        invariant="judged and unjudged partition the relevant set exactly",
        path="src/hai_eval/core/engine.py",
        find="        scenarios_judged=tuple(",
        replace="        scenarios_judged=(),",
    ),
    Mutation(
        name="concealment-turns-a-fail-into-a-pass",
        invariant="hiding a scenario you would fail is never cheaper than failing it",
        path="src/hai_eval/core/engine.py",
        find="        if verdict != Verdict.FAIL:",
        replace="        if False:",
    ),
    Mutation(
        name="observed-failure-erased-by-concealment",
        invariant="a violation the check SAW survives concealment elsewhere",
        path="src/hai_eval/core/engine.py",
        find="        if verdict != Verdict.FAIL:",
        replace="        if True:",
    ),
    Mutation(
        name="probe-passes-over-nothing",
        invariant="a check may not award a pass over scenarios it could not look at",
        path="tests/doubles/echo_profile.py",
        find="    unobserved = tuple(",
        replace="    unobserved = () or (",
    ),
    Mutation(
        name="unobserved-not-intersected",
        invariant="a probe cannot report scenarios outside its own relevance as unjudged",
        path="src/hai_eval/core/engine.py",
        find=" & {p.scenario.id for p in relevant}",
        replace="",
    ),
    Mutation(
        name="empty-scenario-set-allowed",
        invariant="a run must have something to measure",
        path="src/hai_eval/core/models.py",
        find="    scenarios: list[Scenario] = Field(min_length=1)",
        replace="    scenarios: list[Scenario] = Field(default_factory=list)",
    ),
    Mutation(
        name="infinite-axis-weight-allowed",
        invariant="axis weights are finite, so the headline cannot become NaN",
        path="src/hai_eval/core/models.py",
        find="    weight: float = Field(gt=0.0, le=1000.0, allow_inf_nan=False)",
        replace="    weight: float = Field(gt=0.0)",
    ),
    Mutation(
        name="unjudged-scenarios-vanish",
        invariant="a scenario nothing could judge scores zero rather than disappearing",
        path="src/hai_eval/core/engine.py",
        find="    if unjudged:\n        judged = len(relevant) - len(unjudged)",
        replace="    if False:\n        judged = len(relevant) - len(unjudged)",
    ),
    Mutation(
        name="adapter-fault-blamed-on-tool",
        invariant="a broken integration is attributed to the adapter, not the subject",
        path="src/hai_eval/core/engine.py",
        find="Cause.ADAPTER if short and all(p.scenario.id in faulted for p in short)",
        replace="Cause.ADAPTER if False",
    ),
    Mutation(
        name="provenance-not-namespaced",
        invariant="adapter-supplied provenance cannot impersonate an engine finding",
        path="src/hai_eval/core/engine.py",
        find='        f"adapter-declared: {key}": str(value)',
        replace='        f"{key}": str(value)',
    ),
    Mutation(
        name="unverifiable-level-accepted",
        invariant="a profile cannot declare a level the engine has no verifier for",
        path="src/hai_eval/core/profile.py",
        find="    if unverifiable:",
        replace="    if False:",
    ),
    Mutation(
        name="relevance-ignored",
        invariant="a scenario set that asks nothing is the rubric's gap, not the tool's failure",
        path="src/hai_eval/core/engine.py",
        find="    relevant = tuple(p for p in evidence.pairs if spec.relevant(p.scenario))",
        replace="    relevant = tuple(evidence.pairs)",
    ),
    Mutation(
        name="best-sample-wins",
        invariant="a scenario is scored at its weakest sample",
        path="src/hai_eval/core/evidence.py",
        find="        return min(s.level for s in self.samples)",
        replace="        return max(s.level for s in self.samples)",
    ),
    Mutation(
        name="samples-drawn-once",
        invariant="every scenario is drawn the requested number of times",
        path="src/hai_eval/core/engine.py",
        find="        for index in range(samples):",
        replace="        for index in range(1):",
    ),
    Mutation(
        name="empty-claims-allowed",
        invariant="a probe must declare at least one level it can speak at",
        path="src/hai_eval/core/profile.py",
        find="        if not self.claims:",
        replace="        if False:",
    ),
)


def _apply(root: Path, mutation: Mutation) -> bool:
    path = root / mutation.path
    text = path.read_text(encoding="utf-8")
    if mutation.find not in text:
        return False
    path.write_text(text.replace(mutation.find, mutation.replace, 1), encoding="utf-8")
    return True


def _suite_is_red(root: Path) -> bool:
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-x", "--no-header", "-p", "no:randomly"],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode != 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--list", action="store_true", help="list the mutations and exit")
    args = parser.parse_args()

    if args.list:
        for mutation in MUTATIONS:
            print(f"{mutation.name:32} {mutation.invariant}")
        return 0

    survivors: list[Mutation] = []
    unapplied: list[Mutation] = []
    caught = 0

    with tempfile.TemporaryDirectory(prefix="hai-mutants-") as tmp:
        pristine = Path(tmp) / "pristine"
        shutil.copytree(
            REPO,
            pristine,
            ignore=shutil.ignore_patterns(
                ".git", ".venv", "__pycache__", ".pytest_cache", ".mypy_cache"
            ),
        )
        for mutation in MUTATIONS:
            work = Path(tmp) / f"work-{mutation.name}"
            shutil.copytree(pristine, work)
            if not _apply(work, mutation):
                unapplied.append(mutation)
                print(f"  ??  {mutation.name}: anchor not found -- the mutation is stale")
                continue
            red = _suite_is_red(work)
            if red:
                caught += 1
                print(f"  ok  {mutation.name}")
            else:
                survivors.append(mutation)
                tag = " (declared equivalent)" if mutation.equivalent else ""
                print(f"  XX  {mutation.name}{tag}  <-- SURVIVED: {mutation.invariant}")
            shutil.rmtree(work)

    real_survivors = [m for m in survivors if not m.equivalent]
    print(
        f"\ncaught {caught} / survived {len(survivors)} "
        f"({len(real_survivors)} unguarded) / stale {len(unapplied)}"
    )
    if unapplied:
        print("A stale anchor means the code moved and this claim is no longer being made.")
    return 1 if real_survivors or unapplied else 0


if __name__ == "__main__":
    raise SystemExit(main())
