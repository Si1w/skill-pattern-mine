# 0008. Validation by a statistically sized audited sample

Date: 2026-09-14

## Status

proposed

## Context

Labels come from one model for nonzero monthly net changes, with deterministic empty labels for verified activity with no net change under ADR 0013. The legacy study audited a few hundred branch records with two auditors and replaced audited records with consensus labels. The new audit must sample monthly instances and cover the time dimension; its sampling frame and treatment of records with no net change must be specified before sampling.

## Decision

Audit sample size is derived from Cochran's formula for a proportion at 95% confidence and 5% margin with p = 0.5 and correction for a finite population over the final instance count, and allocated proportionally across time quantiles. Two auditors label independently against the frozen taxonomy; accuracy against model labels and kappa between auditors are reported. Labels with low confidence receive a separate review covering a larger proportion of them reported as an additional quality check. All analyses use model labels; consensus labels are reported but never substituted.

## Alternatives

- **Fixed count or fixed percentage**: arbitrary; the formula gives a defensible count.
- **Substituting consensus labels for audited records** (legacy): mixes two labeling processes inside the analysis of time trends; rejected.

## Consequences

Before sampling, define accuracy for sets of labels, blinded independent annotation, adjudication and undefined agreement statistics. The sample formula supports one specified proportion, not a precision guarantee for every rare category or month. Record inclusion probabilities for any enriched sample and keep targeted review separate from the population estimate. Report insufficient positive support rather than inventing reliable estimates.

- Easier: audit effort is bounded and justified; every time stratum has reviewed labels.
- Harder: the formula bounds the precision of the accuracy estimate only; RQ2 to RQ4 power depends on the full corpus.
- If reverted: only the validation section changes.
