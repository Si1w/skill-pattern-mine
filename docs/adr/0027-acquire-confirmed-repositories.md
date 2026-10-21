# 0027. Acquire the confirmed repositories

Date: 2026-09-22

## Status

accepted

## Context

ADRs 0025 and 0026 establish 30 approved upstream repositories. The user authorized acquisition using that membership and a pilot with two forks per repository. The original runner required an unset ratio threshold and bounded the repository count together with the fork count.

## Decision

Use an explicit `confirmed_reviews` selection mode. Select only reviews with `exclude: false` and `is_aggregator: false`, preserving the measured package ratio as descriptive evidence. Keep the original calibrated selection mode for historical runs. This replaces the ratio gate for the approved main cohort without claiming that ratio calibration has been completed.

Start a new run from the original candidate run. Copy only approved repository snapshots and their complete tree inventories, preserving source IDs, timestamps, branch SHAs, discovery evidence, and hashes. Record the source run and implementation snapshot; do not modify the source. Missing, duplicate, or inconsistent identities fail preparation. Import all approved repositories even when a pilot limit is set; that limit bounds forks per upstream and comparison commits. Cache live responses for resumption and offline replay.

## Alternatives

- Choose an arbitrary ratio threshold: changes the approved membership without evidence.
- Repeat broad discovery: unnecessary for validating acquisition from the confirmed frozen cohort.

## Consequences

- Easier: every approved upstream is exercised with bounded API work and reproducible input selection.
- Harder: fork enumeration occurs after the upstream snapshot; divergence is not yet a monthly change or evidence of independent origin. Search coverage remains limited by the original candidate retrieval.
- If reverted: prepare a new run with revised selection. Implementation: `src/config.py`, `src/acquisition.py`, `src/retrieve.py`, the acquisition entry point, and their behavioral tests. Existing identity and response caching run during acquisition; content attribution remains in monthly extraction under ADR 0003 and its later refinements.
