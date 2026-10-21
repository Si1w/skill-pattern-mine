# 0040. Compare reconciled human and original model labels

Date: 2026-09-24

## Status

accepted

## Context

The user confirmed manual reconciliation and explicitly classified B002 and B200 as having no applicable labels. Their serialized nulls now represent confirmed empty sets for this comparison. Reviewer C requests model precision and recall; agreement between human raters alone does not answer this question.

## Decision

Evaluate all 293 sampled instances against original outputs in `legacy/data/label/outputs/`, aligned through the coordinator manifest and input identities. Preserve source files and record the two explicit empty judgments in a separate effective reference. Reject any other null, missing prediction, duplicate identity or unknown label. Keep ADR 0039's independent ratings separate.

Reuse per-label binary macro κ and set agreement, and report per-label TP/FP/FN/TN, precision, recall and F1 at pattern and family levels. Report micro summaries and macro summaries over defined denominators, with their label counts; undefined ratios remain null. Findings describe the eligible sample under ADR 0038, not taxonomy completeness, the excluded population or repeated model runs.

Implementation: `legacy/eval/rebuttal/compare_reconciled.py`, models in `models.py`, behavioral checks in `legacy/tests/test_compare_reconciled.py`, and separate runs under `legacy/data/rebuttal/`. Preserve inputs, effective references, aligned predictions, source hashes and execution metadata. This addresses SIGSOFT General supported claims, Data Science justified metrics, Inter-Rater Reliability independent ratings and reconciliation, and Open Science provenance.

## Alternatives

- **Exclude the two records:** contradicts the user's explicit empty judgments.
- **Use corrected analysis labels:** risks comparing human judgments with already corrected labels.
- **Replace human agreement with model agreement:** obscures the separate reliability question.

## Consequences

- Easier: model quality directly addresses the review using all confirmed judgments.
- Harder: empty references can reveal false positives; agreement is not evidence of model rerun stability.
- If reverted: recompute this comparison and the rebuttal; original inputs and earlier runs remain unchanged.
