# 0028. Exclude fork histories without a common ancestor

Date: 2026-09-22

## Status

accepted

## Context

The pilot collected 60 forks but GitHub could not compare one frozen pair because it had no common ancestor. The user agreed that this fork is outside the analysis of modifications to inherited skills and authorized starting full acquisition.

## Decision

Classify only a compare endpoint's HTTP 404 response whose message explicitly identifies no common ancestor between the exact requested commit SHAs as a `no_common_ancestor` exclusion. Preserve the fork identity, both SHAs, response time, endpoint and raw response. Cache this immutable comparison outcome for offline replay. Other 404 responses and authentication, permission, network, or server failures remain acquisition errors.

Include exclusions in acquisition accounting but omit them from monthly extraction. A fork must have exactly one comparison or exclusion outcome; never interpret exclusion as zero modification. Create separate validation and full runs, retaining the original failed pilot unchanged. Full acquisition waits for API quota renewal, records progress, and checkpoints outputs after each upstream; cached responses preserve work within the current upstream on resume.

## Alternatives

- Retry the same frozen comparison indefinitely: a transient retry does not establish missing common history.
- Treat every 404 as exclusion: hides missing data, permission changes, and API failures.

## Consequences

- Easier: the pipeline distinguishes an explicit study exclusion from a collection failure.
- Harder: exclusions must be reported, and absence of common history does not establish why the fork differs.
- If reverted: reevaluate excluded pairs in a new run. Implementation: `src/domain.py`, `src/github.py`, `src/retrieve.py`, `src/acquisition.py`, and the acquisition entry point. Full acquisition gathers fork metadata and divergence commits; complete histories and monthly records remain a later stage.
