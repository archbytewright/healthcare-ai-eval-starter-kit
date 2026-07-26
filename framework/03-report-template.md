# Report template

The deliverable of an evaluation is a short report a non-technical committee can
act on. The harness renders this structure automatically (see
`hai_eval.report`); this template documents the shape so a manually-written
report (covering the document-review axes) matches it.

The ordering is decision-first: the reader sees the recommendation and the
blocking findings before any detail.

---

## Evaluation report: `<tool name>`

> One-line scope note: generated over synthetic, PHI-free vignettes; a
> pre-adoption due-diligence aid, not a certification or approval. Local
> validation on the org's own population remains required before clinical use.

### Executive summary

- **Tool:** `<name and version>`
- **Rubric:** `<rubric name and version>`
- **Vignette set:** `<which synthetic set was used>`
- **Overall weighted score:** `<x.x / 3>`
- **Blocking findings:** `<count>`
- **Coverage:** `<criteria assessed of total, weight assessed of total>` — the score is computed
  over the assessed part only, so this line is what stops a behavior subscore reading as a
  whole-rubric result.
- **Cases:** `<n>` synthetic vignette(s); `<answered>` answered, `<declined>` declined

**Recommendation:** one of:
- *No automated verdict is available* (every check that ran is a screen — **this is what the
  shipped rubric produces today**, since it declares no deterministic criteria).
- *No recommendation possible* (the tool declined every case, so nothing about its behavior
  was measured).
- *Do not adopt as-is* (any blocking finding).
- *Insufficient coverage to recommend either way* (the tool declined most or all cases, or too
  little of the rubric was assessed for the number to mean anything).
- *Reasonable candidate for a scoped local-validation pilot* (no blockers, strong score).
- *Proceed with caution* (no blockers, several weak areas).
- *Weak across the board* (no single hard fail, but a poor fit).

### Blocking findings

Each item is a hard fail on a criterion whose check is *deterministic* — exact, not interpretive
— in an axis the rubric marks blocking-eligible. Each ships the tool's verbatim output too: the
higher the stakes of a finding, the more a reader needs the sentence it rests on. Resolve with
the vendor or rule the tool out before adoption proceeds. "None" is a valid and common result,
and does not mean "clean": the screens below can hold a real problem they are not able to prove.

### Screens -- flagged for human confirmation

Findings from checks that detect a pattern but cannot interpret it. Each line carries the
concern, a note stating what that screen cannot see, and the tool's **verbatim output**, so a
reviewer can settle it by reading rather than by trusting the label. Nothing in this section
blocks adoption on its own. A screen with no output to point at — one that fires on an absence, or one judging the shape of a
reply rather than a sentence inside it — (nothing ever abstained) has no
output to quote, and says so by omission.

### Provenance

What produced this report: the model or tool identifier, the sampling options, whether the case
text was sent with or without its structural tags, and whether inference stayed on the loopback
interface. A served model is not bit-for-bit reproducible, which makes recording the conditions
more necessary rather than less — without them a re-run that disagrees cannot be told apart from
a report that was never produced the way it claims.

### Per-axis detail

For each axis: the axis score, then a table of its criteria with the tier, the verdict, and
the evidence behind each verdict. The tier column tells a reader how much weight a row
carries; the evidence column is what makes the report auditable, since a reader can disagree
with a number by reading why it was assigned.

### How to read this

The scale, the meaning of *not assessed*, and the reminder that the synthetic
vignettes are a screen and not a substitute for local validation.

---

## What the report is not

- Not a certification or a seal of approval. The method is advisor-posture: it
  presents an analysis; the org decides.
- Not a statement that the tool is safe for the org's population. That is local
  validation, a later, scoped, data-governed step.
- Not a substitute for the document-review axes. The harness fills the
  behavior-assessed rows; a human completes the oversight, failure-mode, and
  regulatory rows from vendor documentation.
