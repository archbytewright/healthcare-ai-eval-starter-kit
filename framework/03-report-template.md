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

**Recommendation:** one of:
- *Do not adopt as-is* (any blocking finding).
- *Reasonable candidate for a scoped local-validation pilot* (no blockers, strong score).
- *Proceed with caution* (no blockers, several weak areas).
- *Weak across the board* (no single hard fail, but a poor fit).

### Blocking findings

Each item is a hard fail on a safety-relevant criterion. Resolve with the vendor
or rule the tool out before adoption proceeds. "None" is a valid and common
result.

### Per-axis detail

For each axis: the axis score, then a table of its criteria with the verdict and
the evidence behind each verdict. The evidence column is what makes the report
auditable: a reader can disagree with a number by reading why it was assigned.

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
