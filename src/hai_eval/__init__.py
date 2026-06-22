"""Healthcare AI Evaluation Starter-Kit.

A vendor-neutral framework plus a small worked-example harness for
resource-constrained health systems to evaluate a clinical AI tool before
adoption. The package ships:

- A typed rubric model (:mod:`hai_eval.models`) loaded from a YAML scoring
  definition, organised along the evaluation axes documented in ``framework/``.
- A tool-under-test seam (:mod:`hai_eval.tool`) so a deterministic mock stands
  in for a real vendor tool during the worked example, and a real tool can be
  dropped in behind the same interface later.
- Synthetic, clearly-fabricated clinical vignettes (:mod:`hai_eval.loader`).
- An evaluator (:mod:`hai_eval.evaluator`) that runs the tool over the
  vignettes, scores its behaviour against the rubric, and a reporter
  (:mod:`hai_eval.report`) that renders a committee-readable report.

No real patient data is present anywhere in this package. All clinical content
is constructed for testing.
"""

from __future__ import annotations

__version__ = "0.1.0"
