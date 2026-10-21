# 0021. PyDriller compatibility pilot

Date: 2026-09-16

## Status

proposed

## Context

The user authorized a bounded comparison before deciding whether PyDriller can replace history acquisition. This supports the extraction inputs to RQ1 to RQ4. Satisfies Repository Mining requirements for acquisition and preprocessing, General requirements for reproducible analysis and limitations, and Sampling requirements for an explicit engineering sample.

## Decision

Subsequent production adoption is recorded in [ADR 0023](0023-use-pydriller-for-monthly-history.md). The protocol below describes the preceding compatibility experiment.

Compare the saved March and August observations from `lucianghinda/superpowers-ruby` at their frozen fork and upstream heads. Select these cases for existing merge and upstream overlap evidence, without claiming representativeness. Compare complete reachable commit identifiers, ordered parents, trees and UTC timestamps against fresh GitHub API reads; report message differences and unavailable GitHub account mappings separately. Compare complete endpoint bytes, modes, monthly boundaries, net diffs and origin evidence against the saved API records. Use deterministic local fixtures for ordinary edits, merges, deletion, binary and mode changes, and cancellation.

Evaluate both direct PyDriller modifications and a thin adapter reading complete Git trees and blobs through GitPython while retaining our monthly and origin rules. Any missed relevant transition prevents a direct replacement claim. Pin dependencies and references, record raw comparisons and failures, separate fetch time from processing, and report three repeated history reads with API cache state explicit. Timings are descriptive for this sample, with no population speedup claim. Keep compact results and reproducible code; remove temporary repositories and API caches after the experiment. Production acquisition remains governed by ADR 0019 until a separate migration decision.

## Alternatives

- Documentation alone cannot establish compatibility with our merge and monthly semantics.
- A full corpus migration before testing would expose expensive collection to unverified changes.

## Consequences

- Easier: adoption can be judged against frozen records and deliberately constructed edge cases.
- Harder: one repository network cannot establish operational reliability or cost across the corpus; shared research logic is not independently validated by backend agreement.
- If reverted: rerun this engineering comparison. Implementation: `configs/pydriller-pilot.yaml`, `eval/pydriller-pilot/main.py`, and `src/pydriller_pilot.py`. Existing behavioral tests remain the baseline for research logic.
