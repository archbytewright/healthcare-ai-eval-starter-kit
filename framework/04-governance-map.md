# Minimal governance map

Evaluating a tool is one step; standing up enough governance to adopt it safely
is the other. This map is the *minimal* scaffolding a resource-constrained org
needs, aligned to the voluntary frameworks the field is converging on. It is not
a compliance program; it is the floor below which adoption should not proceed.

The map is vendor-neutral and framework-aligned, not framework-authored: it
points at where each item lives in the public playbooks so an org can go deeper.

## The voluntary landscape (why this map looks the way it does)

The federal transparency floor is being reworked: ONC's HTI-1 rule made model
cards mandatory for decision-support interventions, and a later proposed rule
(HTI-5) would remove that mandate. When a federal floor is uncertain, the burden
shifts onto voluntary frameworks and local discipline. The frameworks the field
is consolidating around are:

- **CHAI** (Coalition for Health AI): responsible-use guidance and governance
  playbooks; a membership coalition, not a certifier. (An earlier third-party
  assurance-lab model did not hold; the surviving artifact is the playbooks.)
- **The Joint Commission**: responsible-use guidance jointly with CHAI, and a
  forthcoming voluntary AI certification for *healthcare organisations* (the
  credential is becoming org-level accreditation, not model-level certification).
- **NIST AI Risk Management Framework**: the general govern / map / measure /
  manage structure that the healthcare-specific guidance sits on top of.

An org's practical posture: use the playbooks, prepare for org-level
certification, and evaluate the vendor tools that no central lab will vet for it.

## The minimal scaffolding (five items)

Each item maps to a rubric axis so the evaluation and the governance plan stay
coupled.

### 1. An intended-use and risk record per tool
*(rubric: regulatory)*: Write down, per tool, what it is used for, on which
population, and the risk tier. This is the anchor everything else references and
the first thing an accreditor will ask for.

### 2. A human-oversight checkpoint
*(rubric: oversight)*: Define the required human review/sign-off before the
tool's output enters the record or a decision. For a clinical decision support tool this is the
clinician's edit-and-sign step; name it explicitly and make it non-skippable.

### 3. A pre-adoption evaluation record
*(rubric: safety, failure_modes)*: The output of this kit: the evaluation
report, the synthetic vignette set used, and the resolution of any blocking
findings. Retain it; it is the evidence of due diligence.

### 4. A post-deployment monitoring plan
*(rubric: oversight)*: A lightweight, owned plan: what is watched after go-live
(e.g. clinician override rate, reported errors), how often, and the trigger that
forces a re-evaluation. Local monitoring is the under-served frontier; even a
simple plan beats none.

### 5. A transparency-artifact file
*(rubric: regulatory)*: Collect the vendor's model-card-equivalent disclosure.
If the vendor does not supply one, that absence is recorded as a finding and
raised, regardless of whether a federal mandate currently requires it.

## Authority posture

This map and the evaluation are **advisor, not certifier**. No one licenses AI
evaluators, so an assessment can be offered freely, but the method deliberately
does not mint a seal of approval. Two reasons: a certifier who declares a tool
"good enough" assumes a duty if a patient is later harmed, and a seal is worth
only the issuer's recognised authority. The recognised authority being built is
the Joint Commission's org-level certification, so the posture here is to help an
org prepare for *that*, not to substitute for it.
