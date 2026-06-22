# Healthcare AI Evaluation Starter-Kit

A vendor-neutral framework and a small worked-example harness for evaluating a
clinical AI tool before a health system adopts it. It is built for
resource-constrained organisations: small hospitals, specialty groups, and
clinics that have clinicians who can judge clinical fit and IT staff who can
judge integration, but no one positioned to independently test whether a tool's
*actual behaviour* matches the sales deck.

It is a due-diligence aid. It is not an assurance lab, a certification, or an
approval. It produces an analysis the org acts on, not a seal it relies on.

## Why this exists

The regulatory floor for clinical AI transparency is being reworked. ONC's HTI-1
rule made model-card disclosure mandatory for decision-support tools; a later
proposed rule would remove that mandate. When a federal floor is uncertain, the
evaluation and governance burden shifts onto the adopting organisation, exactly
where help is scarce. The voluntary frameworks the field is converging on (CHAI
and Joint Commission playbooks, NIST AI RMF) describe *what good looks like* but
leave each org to do its own local evaluation.

This kit is the local-evaluation discipline made concrete: a structured method,
a re-weightable scoring rubric, a report a non-technical committee can act on, a
minimal governance map, and runnable code that demonstrates the method end to
end on synthetic data.

## The method, decomposed

The method has four parts, each documented in `framework/` and each independently
usable.

### 1. Inputs (`framework/01-input-categories.md`)

Three categories are gathered before scoring: vendor claims and documentation,
synthetic test inputs, and organisational context. They come from different
sources and feed different parts of the rubric, so they are kept separate.

### 2. The evaluation axes (`framework/02-scoring-rubric.md`)

A clinical AI tool is scored along five axes:

- **Safety properties.** Does the tool's behaviour preserve clinically
  load-bearing facts, avoid fabricating or leaking facts, and resist adversarial
  input? Weighted highest, because it is closest to patient harm.
- **Workflow integration.** Does the tool fit the workflow it claims to support,
  and does it degrade gracefully when it cannot finish a task?
- **Failure-mode handling.** When the tool is wrong, is the error visible to the
  clinician rather than buried in fluent prose?
- **Human oversight and monitoring.** Is there a defined human checkpoint and a
  post-deployment monitoring plan?
- **Regulatory and transparency posture.** Does the vendor supply
  model-card-equivalent transparency, whether or not a mandate currently
  requires it?

Each axis holds criteria scored on a 0 (fail) to 3 (strong) scale, where higher
is better. Axis weights are data, not code, so an org can re-weight them for its
own risk tolerance.

### 3. Scoring and the blocking-finding rule

Criteria roll up to axis scores, and axes roll up to one weight-normalised
overall score. The overall is a summary, not a gate. A single hard fail on a
safety-relevant criterion becomes a *blocking finding*, and any blocking finding
forces a "do not adopt as-is" result regardless of the headline number. A safety
hard-fail is not offset by strength elsewhere.

About half the rubric is assessed by document and governance review rather than
by running the model, because oversight, monitoring, and transparency are
properties of the deployment and the vendor, not of the model's text output. The
harness scores what behaviour can measure and reports the rest as *not assessed*,
which is neither a pass nor a fail. An unmeasured property is never recorded as a
pass.

### 4. The report and the governance map

The deliverable is a short Markdown report (`framework/03-report-template.md`):
recommendation first, then blocking findings, then per-axis detail with the
evidence behind every score. Alongside it sits a minimal governance map
(`framework/04-governance-map.md`): the five scaffolding items an org needs to
adopt a tool safely, each aligned to the CHAI / Joint Commission / NIST
frameworks and mapped back to a rubric axis.

## The worked example (runnable code)

The kit ships a complete, self-contained example so the method is not just
described. It evaluates a *mock clinical decision support (CDS) tool* over four synthetic,
PHI-free vignettes and emits a report.

The example uses a deterministic mock so it runs offline and byte-reproducibly,
with no model weights and no network calls. The mock is built behind a clean
seam (`hai_eval.tool.ToolUnderTest`): a real vendor tool is integrated by writing
an adapter that implements one method, and nothing else in the harness changes.
The mock deliberately exhibits several realistic failure modes (it drops a stated
contraindication, leaks an out-of-scope fact present in its input, follows an
instruction embedded in the transcript, and never abstains) so the rubric has real
behaviour to catch.

```bash
uv sync
uv run hai-eval run --out -        # print the worked-example report to stdout
uv run hai-eval run                # or write it to reports/<tool>.md
```

### Architecture

```
framework/        # the method as docs: inputs, rubric, report template, governance map
  rubric.yaml     # the rubric as data (re-weightable without touching code)
data/
  vignettes.yaml  # synthetic, clearly-fabricated clinical vignettes
src/hai_eval/
  models.py       # pydantic boundary models (rubric, vignettes, tool I/O, report)
  loader.py       # validated YAML loading
  tool.py         # the tool-under-test seam + the deterministic mock CDS tool
  evaluator.py    # the harness: run the tool, score behaviour via registered probes
  report.py       # render a committee-readable Markdown report
  cli.py          # `hai-eval run`
tests/            # behavioural + differential tests (probes must discriminate)
```

## Data and safety posture

All clinical content in this repository is **synthetic and clearly fabricated**.
No real patient data is present in any vignette, fixture, test, or generated
report. Synthetic inputs are a design choice, not a limitation: pre-purchase
evaluation happens before a tool ever touches real data, the suite carries no PHI
or BAA liability, it is reproducible, and it can be shared. Local validation on
an organisation's own population is a separate, later, data-governed step, and is
out of scope for this kit by design.

## Status

v0.1 draft. The framework and the worked example are complete; the rubric and
vignette set are starting points meant to be extended for a specific tool type
and organisation. See `framework/` for the method and `tests/` for the behaviour
the harness guarantees.

## License

MIT. See `LICENSE`.
