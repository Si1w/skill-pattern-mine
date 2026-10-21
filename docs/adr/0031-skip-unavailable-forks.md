# 0031. Skip unavailable forks

Date: 2026-09-23

## Status

accepted

## Context

The user approved skipping HTTP 404 failures during fork acquisition instead of blocking acceptance of the remaining corpus.

## Decision

Record unavailable forks in `fork_skips.jsonl` with their numeric identity, acquisition stage and HTTP status. Keep numeric identity fallback for renamed repositories. A remaining 404 during reconciliation, metadata, branch or comparison acquisition skips that fork and does not fail acceptance. An upstream listing failure still blocks enumeration because its missing population is unknown. Other errors remain failures. Keep explicit no common ancestor exclusions separate. Missing inventory IDs accounted for by 404 skips no longer block acceptance.

## Alternatives

- Block the entire corpus on every 404: rejected by the user.
- Drop unavailable forks without records: loses the missingness denominator.

## Consequences

- Easier: acquisition and extraction can proceed with available forks.
- Harder: corpus coverage excludes inaccessible forks; a large corpus does not establish absence of selection bias.
- If reverted: retry skipped identities in a new run. Preserve previous runs. Implementation: `src/domain.py`, `src/github.py`, `src/retrieve.py`, `src/acquisition.py`, extraction selection and acquisition tests.
