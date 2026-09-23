# 0037. Exclude known exposure from the blind sample

Date: 2026-09-23

## Status

superseded by 0038

## Context

The user requires exclusion of previously annotated records and confirmed the 1,126 final analyzed instances as the starting population. The previous sample drew from 1,220 candidates, including 94 excluded after receiving no final labels, and overlapped 67 old audit records and 82 taxonomy bootstrap records.

## Decision

For taxonomy application validation, exclude the union of saved human verdict records, the old audit sample and the known taxonomy bootstrap sample before sampling. Within the 1,126 final instances, these exclude 277 audit records and 280 bootstrap records, with 69 in both: 488 excluded and 638 eligible. Draw 293 without replacement from sorted eligible input filenames using seed 42. Both raters annotate the same records independently with predictions hidden and adjudicate before inspecting predictions. The 209-instance security census is unchanged.

Use run ID `human-unseen-293-20260923` for the revised blind form, preserving the old run and keeping the security form's existing run ID. Record frame counts, exclusion provenance and checksums in the coordinator manifest. Implementation: `legacy/eval/rebuttal/audit_materials.py`, `prepare_collaboration.py`, `models.py`, and `legacy/tests/test_rebuttal.py`; shared forms: `legacy/annotation/`.

This addresses Sampling's population, frame and exclusion requirements and Inter-Rater Reliability's independent-rating requirement under ADR 0034. The estimand is the 638 eligible final instances, not all 1,126 instances or 1,220 candidates. Missing taxonomy iteration logs and unrecorded exposure prevent a strict held-out claim. Zero-label exclusion validity is not tested.

## Alternatives

- Keep the 1,220-candidate frame: could assess zero-label exclusion but does not match the user's selected scope.
- Keep the previous sample: does not exclude known exposure.

## Consequences

Known audit and bootstrap overlap becomes zero. Report the narrower inference scope and retain missing judgments. Old blind exports must not be merged by task ID with the revised run; preserve any existing work separately. The sample size remains 293 and does not guarantee rare-label precision.
