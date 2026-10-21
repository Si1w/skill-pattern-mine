# 0005. Taxonomy rebuilt from scratch with two human checkpoints

Date: 2026-09-14

## Status

proposed

## Context

The legacy 46-pattern, 13-family taxonomy saturated on a single static pool and may encode the modification style of one period; seeding the new taxonomy with it would bias the temporal comparison in RQ2. Human review of each batch is too costly for a larger corpus.

## Decision

Build the taxonomy by open coding on the new corpus without the legacy codebook. Bootstrap stage: the labeling model codes a bootstrap sample stratified by time quantile and upstream repository, merges its own proposals, and outputs taxonomy v1. Checkpoint one: a human reviews v1 and fixes the core. Iteration stage: further batches, stratified by time quantile, are fed to the model, which may only append to a candidate list and may not alter reviewed core definitions; saturation is judged per time stratum as two consecutive batches adding nothing. Checkpoint two: a human merges candidates, finalises families, and freezes the version. A mapping table to the legacy taxonomy (direct correspondence, split, merged, new, gone) goes to the appendix; the legacy taxonomy appears only in the discussion.

## Alternatives

- **Seed with the legacy taxonomy**: period bias; rejected.
- **Human review after every batch**: not affordable at the new scale; rejected.
- **Fully autonomous iteration with edits to existing definitions**: definition drift makes saturation meaningless; rejected.

## Consequences

Before implementation, fix batch sizes, sampling without replacement, the definition of a new candidate, and handling of exhausted strata. Store source instance references for each candidate. Keep independent validation examples out of prompt and rule tuning, and define how observations outside the frozen taxonomy are represented.

- Easier: two concentrated review sessions; every batch input, output and version diff is on disk and publishable.
- Harder: results are not directly comparable with the legacy taxonomy without the mapping table.
- If reverted: labeling and all results for each pattern must be redone.
