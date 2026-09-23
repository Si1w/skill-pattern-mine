# 0032. Reuse comparisons with minimal evidence

Date: 2026-09-23

## Status

accepted

## Context

The user approved eliminating repeated frozen comparisons and redundant hashing while retaining the checks necessary for correct data and recovery.

## Decision

Reuse a successful complete comparison within the same upstream and exact base and head SHA pair. Preserve each fork's metadata and point reused results to the original comparison. Never share errors, exclusions or incomplete comparisons. Recovery retains exact cached responses and may reuse listings when both runs use creation ordering; inventory checks remain mandatory. Retain cache key hashes, Git blob verification, patch fingerprints and stable observation identifiers. Keep source snapshots and direct identity/content checks, removing duplicate source and response checksum inventories.

## Alternatives

- Request every fork comparison independently: wastes quota on identical Git objects.
- Remove identity and content checks: can silently associate the wrong evidence with an observation.

## Consequences

- Easier: fewer requests and smaller recovery manifests.
- Harder: reused records must retain an existing complete source comparison in the same upstream.
- If reverted: use the preserved source comparison evidence or recollect in a new run. Implementation: `src/domain.py`, `src/retrieve.py`, `src/acquisition.py`, `src/pydriller_pilot.py` and acquisition/recovery tests. Monthly extraction remains a separate stage and now requires completed acquisition, except for explicit bounded pilot inputs.
