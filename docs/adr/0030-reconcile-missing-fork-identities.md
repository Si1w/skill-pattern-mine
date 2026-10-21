# 0030. Reconcile missing fork identities

Date: 2026-09-22

## Status

superseded by 0031

## Context

Creation ordering returned 26,100 distinct fork IDs without duplicates or order inversions. Two previously listed IDs were absent and returned HTTP 404 by numeric identity. Abandoning that entire upstream would unnecessarily discard valid acquisition work while not resolving these access failures.

## Decision

Retain ADR 0029's ordering, provenance, recovery and checkpoint rules. Duplicate rows or creation order reversals still stop that upstream before comparisons. Reconcile an absent known ID using its numeric repository endpoint. Append an accessible public fork only when its returned identity and parent or source establish membership in the upstream network; preserve the response as evidence. Reorder reconciled rows by creation time and ID.

Keep unresolved missing IDs in coverage and error records, and continue collecting other listed forks. Such failures prevent complete coverage and acceptance; they are neither study exclusions nor zero activity observations. Preserve the original cutoff and cohort. This changes partial progress handling, not the criteria for valid research data.

## Alternatives

- Stop all work on an otherwise consistent upstream: wastes valid acquisition opportunities.
- Silently drop absent IDs or treat a generic 404 as an exclusion: hides missing observations.

## Consequences

- Easier: useful collection continues while missingness remains explicit and auditable.
- Harder: an unresolved access failure still requires later investigation before any complete dataset claim.
- If reverted: keep partial outputs as incomplete and create a new run. Implementation: `src/retrieve.py`, coverage validation in `src/acquisition.py`, and `tests/test_fork_recovery.py`.
