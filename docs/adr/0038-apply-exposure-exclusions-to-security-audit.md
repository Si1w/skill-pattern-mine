# 0038. Apply the same exposure exclusions to security validation

Date: 2026-09-23

## Status

accepted

## Context

After confirming ADR 0037, the user requested the same population and exclusion rules for other validation materials, explicitly including the security audit.

## Decision

Retain ADR 0037's 293-record blind sample from the 638 eligible final instances. Restrict security validation to detector-positive instances in that same eligible frame. All original 209 positives are within the 1,126 analyzed instances; 64 overlap saved audit records, 48 overlap bootstrap records, and 12 overlap both. Exclude their union of 100, leaving 109 instances and 642 distinct matched lines for both raters to audit independently.

Use `human-unseen-v2-20260923` for both forms. Preserve previous runs locally, do not import old task IDs into the new run, and publish revised forms and counts together. Original descriptive analyses continue to use their stated study populations; the exposure filter governs new human validation, not retrospective alteration of the study corpus. Security outcomes describe only the 109 eligible positive instances, not all 209 positives. Detector recall and zero-label exclusion validity remain untested.

Implementation: `legacy/eval/rebuttal/audit_materials.py`, `prepare_collaboration.py`, `render_report.py`, `legacy/annotation/`, and `legacy/tests/test_rebuttal.py`. Store input hashes, exclusions and task mappings locally; publish aggregate validation scope without model answers. Sampling requirements for explicit filtering, frame and generalization and Inter-Rater Reliability requirements for independent judgments remain applicable as in ADR 0037. Missing iteration logs still prevent a strict held-out claim.

## Alternatives

- Audit all 209 positives: preserves full positive coverage but retains known exposure, contrary to the user's instruction.
- Limit security to the 293 sampled blind records: unnecessarily discards eligible security evidence; the security task instead covers all positives in the common 638-record frame.

## Consequences

All new human validation excludes known exposure and zero-label exclusions. Coverage and claims must distinguish the original corpus from the eligible validation frame. Any prior ratings must remain separately identified and cannot silently enter the new validation results.
