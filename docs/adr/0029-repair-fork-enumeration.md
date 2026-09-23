# 0029. Repair fork enumeration

Date: 2026-09-22

## Status

superseded by 0030

## Context

The first full run returned 26,093 fork rows for `obra/superpowers`, but only 14,781 distinct IDs. Star ordering therefore failed the existing coverage requirement. The user authorized repairing and optimizing acquisition while preserving research validity.

## Decision

Use creation time ascending (`oldest`) for new acquisitions. Before branch collection, check listing ID uniqueness, creation order, and retention of IDs observed in a recovery source. Any inconsistency prevents complete coverage and stops processing that upstream. This repairs acquisition without changing cohort membership, monthly units, or exclusion rules. Pagination remains an observation over time, not an atomic snapshot.

Recover into a new run with the original observation cutoff, source upstreams and sample bounds. Preserve the old run and import only validated metadata, branch and immutable comparison responses, with original timestamps and file hashes. Reacquire listings under the new order. A metadata 404 may be resolved by the listed numeric repository ID; a remaining failure stays an error. Publish intermediate checkpoints within large upstreams.

## Alternatives

- Deduplicate star pages and claim completion: cannot establish missing forks.
- Discard all cached work or alter the old run's frozen configuration: wastes requests or loses provenance.

## Consequences

- Easier: pagination failures are detected before expensive comparisons; recovery preserves acquired references and reduces repeated requests.
- Harder: deletions, visibility changes and concurrent changes can still prevent complete acquisition and require evidence, not automatic exclusions.
- If reverted: create a new run and revalidate coverage. Implementation: `src/github.py`, `src/retrieve.py`, `src/acquisition.py`, the entry point, configuration and behavioral tests.
