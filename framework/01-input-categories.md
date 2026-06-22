# Input categories: what to gather before evaluating a clinical AI tool

An evaluation is only as good as its inputs. Before a tool is scored, three
categories of input are assembled. The categories are deliberately separated
because they come from different sources, carry different trust levels, and feed
different parts of the rubric.

## 1. Vendor-supplied claims and documentation

What the vendor asserts, captured verbatim so it can be checked rather than
assumed. Source: sales materials, the model card or its equivalent, the
contract, security questionnaires.

- **Intended use statement**: the population, setting, and task the tool is
  built for. A tool used outside its intended use is an off-label deployment.
- **Validation evidence**: where and on whom the tool was validated, and on
  what outcome. "Validated" with no population is not validation evidence.
- **Claimed performance**: the specific accuracy / quality numbers, with the
  denominator they were measured against.
- **Stated limitations and failure modes**: what the vendor admits the tool
  does poorly. An empty list here is itself a finding.
- **Transparency artifacts**: model-card-equivalent disclosure (intended use,
  training/validation data description, subgroup performance, monitoring).

These map to the *regulatory*, *oversight*, and *failure-mode* axes of the
rubric, which are assessed by document review rather than by running the model.

## 2. Synthetic test inputs

The constructed cases the tool is actually run against. **No real patient data.**
Synthetic inputs are a feature, not a compromise: they carry no PHI or BAA
liability, they are reproducible, and the suite itself can be shared.

- **Constructed clinical vignettes**: realistic encounters written to exercise
  specific properties (a stated allergy that must survive, a back-to-back pair
  that must not cross-contaminate).
- **Adversarial / edge cases**: inputs designed to probe a trust boundary
  (instructions embedded in a transcript) or a degradation path (ambiguous or
  incomplete input where abstaining is the safe answer).
- **Open synthetic sources**: Synthea-generated records and similar public
  generators extend the suite without ever touching real data.

These feed the *safety* and *workflow* axes, which are assessed by running the
tool and inspecting its behaviour.

## 3. Organisational context

The facts that decide which failures matter for *this* org. The same tool can be
a reasonable risk for one setting and unacceptable for another.

- **Use case and setting**: what the org will actually do with the tool.
- **Patient population**: how it differs from the validation population.
- **Existing workflow and oversight**: where a human review checkpoint sits.
- **Risk tolerance**: used to re-weight the rubric axes (see `02-scoring-rubric.md`).

Organisational context does not produce scores directly; it shapes axis weights
and the interpretation of findings.
