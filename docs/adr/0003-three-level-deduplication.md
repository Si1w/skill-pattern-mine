# 0003. Deduplication at three levels

Date: 2026-09-14 (revised 2026-09-15)

## Status

proposed

## Context

Forks replay commits and rebase; some owners push bulk translations or bot commits. Legacy deduplication only removed shared commit SHAs and collapsed subset branches, so one change could be counted many times. Copies of entire skill repositories are handled by excluding aggregators (ADR 0002) rather than by content similarity.

## Decision

ADR 0018 excludes monthly intervals whose upstream origin cannot be resolved. The detector remains to be designed. Merge, squash and revert names alone do not establish that content is mechanical; the implementation must retain ancestry and must not use these names to discard real changes before endpoint comparison. The patch equivalence mode and handling of changes later integrated upstream also remain unresolved.

Monthly endpoint comparisons follow [ADR 0013](0013-monthly-net-change-as-labeling-unit.md), and [ADR 0014](0014-fork-default-branch-only.md) restricts mining to the frozen default branch of each fork. The original plan below is historical where it requires collecting multiple branches or collapsing subsets; those operations no longer apply to the main corpus. Preserve real changes during endpoint reconstruction, keep identical diffs from different months as separate observations, and retain eligible activity with no net change. Rules for establishing equivalent histories and identifying upstream contributions remain unresolved.

The original plan deduplicated at three levels: (1) commits, using `git patch-id` per package instead of SHA; (2) branches, using common ancestry and commits unique to the fork owner, while recording which subset branches were collapsed; (3) authors, using bot detection and translation flags. Changes limited to translation were kept out of the main analysis. For corpus description, count packages whose normalized `SKILL.md` is identical byte for byte across retained upstreams without merging those packages.

## Alternatives

- **Commit deduplication using SHA only** (legacy): misses replayed commits and rebases; rejected.
- **Merging repository lineages with similar content**: adds a similarity threshold and calibration for a problem the aggregator exclusion and the small retained pool already remove; rejected.
- **Dropping translation commits entirely**: loses a reportable category; flagged instead.

## Consequences

- Easier: one change is counted once within a fork; no similarity threshold to defend.
- Harder: identical skills hosted by two retained upstreams are counted as two skills; the reported overlap count makes this visible.
- If reverted: instance counts and prevalence figures change.
