# Minimal governance map

Evaluating a tool is one step; standing up enough governance to adopt it safely
is the other. This map is the *minimal* scaffolding a resource-constrained org
needs, aligned to the voluntary frameworks the field is converging on. It is not
a compliance program; it is the floor below which adoption should not proceed.

The map is vendor-neutral and framework-aligned, not framework-authored: it
points at where each item lives in the public playbooks so an org can go deeper.

## The voluntary landscape (why this map looks the way it does)

The federal transparency floor is being reworked: ONC's HTI-1 rule placed source-attribute
transparency obligations on certified health IT developers for decision-support interventions
(commonly described as "model cards", though the rule's own language is narrower), and a later
proposed rule would remove that requirement. When a federal floor is uncertain, the burden shifts
onto voluntary frameworks and local discipline. The frameworks the field is consolidating around
are:

- **CHAI** (Coalition for Health AI): responsible-use guidance jointly with The Joint
  Commission, and a set of governance playbooks (released May 2026, structured around eight
  elements); a membership coalition, not a certifier. An earlier third-party assurance-lab model
  appears not to have held; the surviving artifacts are the playbooks, a model-card template and
  a registry.
- **The Joint Commission**: the **Responsible Use of AI in Healthcare (RUAIH) certification**,
  launched June 2026 — voluntary, for *healthcare organizations* rather than for individual AI
  tools, and organised around five areas: governance; effective data management; risk and bias
  reduction; monitoring, evaluating and validating safety performance, effectiveness and
  responsible use; and transparency, education and training. The direction of travel is org-level
  accreditation rather than model-level certification, and it is now a live programme rather than
  a projected one.
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

This map and the evaluation are **advisor, not certifier**. There is no licensure regime for AI
evaluators, so an assessment can be offered freely, but the method deliberately does not mint a
seal of approval. Two reasons, the first of which is a judgement about exposure and not legal
advice: declaring a tool "good enough" invites responsibility if a patient is later harmed, and a
seal is worth only the issuer's recognized authority. The org-level authority now in the field is
the Joint Commission's RUAIH certification (launched June 2026), so the posture here is to help an
org prepare for *that*, not to substitute for it. Note the exposure argument above stands on its
own regardless of how that programme develops.

## Sources and how current they are

Every regulatory statement in this document is the author's reading as of **2026-07-26**, and none
of it is legal advice. The named programmes, dates and area names were checked against public
sources on that date; the underlying **rule and guidance texts were not read line by line**, so the
characterisations are secondary-source readings even where the existence and naming are confirmed.
The Joint Commission's own pages could not be retrieved directly (they refuse automated requests),
so the RUAIH details rest on its press releases and consistent trade coverage. Rule designators and dates move; the direction of travel is the durable part,
the specifics are not. Before relying on any of it in an engagement, check the current text of:
the ONC/ASTP HTI rules on decision-support transparency, FDA's clinical decision support software
guidance, the NIST AI Risk Management Framework and its generative-AI profile, CHAI's published
guidance, and The Joint Commission's AI-related certification materials.

The rubric's per-criterion `source:` fields are pointers for tracing a line back to a framework,
not citations that have been reconciled against those documents.
