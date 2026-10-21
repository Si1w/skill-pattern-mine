# 0036. Independently annotate 293 legacy candidates

Date: 2026-09-23

## Status

superseded by 0037

## Context

The user confirmed two human raters and chose 293 common records instead of 150 within the two day revision window. The original visible-model audit cannot substitute for independent annotation.

## Decision

Draw 293 records without replacement from the sorted 1,220 labeling inputs with seed 42. Both raters independently apply the fixed taxonomy with model answers and rationale hidden, then adjudicate before comparing against original predictions. Include zero-label candidates through the common frame. Prepare a separate census of all 209 security-positive instances with per-line textual meaning and change-direction judgments. Implementation: `legacy/eval/rebuttal/audit_materials.py`; forms and coordinator manifests: `legacy/data/rebuttal/human-293-20260923/human/`.

This sample gives approximately five percentage points of worst-case precision for one overall binary proportion under simple random sampling with finite-population correction. It does not guarantee per-label precision/recall or correct labels. Record annotator experience and prior exposure. The sampled records overlap 82 known taxonomy bootstrap records and iteration membership is unavailable, so no held-out claim is justified. The audit validates application of the taxonomy, not independent taxonomy derivation. These choices address Sampling and Inter-Rater Reliability requirements for an explicit frame and independent ratings under ADR 0034.

## Alternatives

- **150 common records:** faster, but about 7.5 percentage points of worst-case precision; the user selected 293.
- **Disjoint samples per rater:** cannot measure agreement on all sampled records.

## Consequences

- Easier: ready-to-use forms support independent ratings and preserve missing judgments.
- Harder: 586 blind ratings plus security judgments require substantial human time; prior exposure remains a limitation.
- If reverted: report the actual completed probability sample and missingness; do not silently stop based on observed results or claim the original precision target.
