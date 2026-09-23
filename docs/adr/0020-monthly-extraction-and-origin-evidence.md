# 0020. Monthly extraction and origin evidence

Date: 2026-09-16

## Status

proposed

## Context

The user authorized implementing monthly extraction and a live pilot. RQ1 to RQ4 require actual endpoint contents rather than comparison metadata. Satisfies Repository Mining requirements for preprocessing and operational measures, and Longitudinal requirements for subject identity and temporal ordering. This operationalizes ADRs 0013, 0015 and 0018 for engineering validation; screening and annotation remain separate.

## Decision

Collect complete reachable commit metadata from frozen fork and upstream heads through the GitHub API, without date filters. Reconstruct the default branch through ordered first parents. Side histories remain available as evidence; they do not create extra observations before integration. Group changes by UTC committer month along that lineage. Reject histories that cross month boundaries backwards, or cross the cutoff and then return below it, rather than inventing a chronological lineage. Compare the state before the first package change with the state after its last change in the selected month. Intermediate changes remain in the evidence, including cancellations.

Require an existing package manifest at a shared ancestor preceding the interval. Retain package paths as identities; a removed root accompanied by a newly added root is unresolved identity and needs review. Record within-package moves as deletion and addition. Compare complete tree entries, including modes, and fetch complete endpoint blobs. Preserve binary bytes as base64 and submodule pointers as gitlink values. Never interpret missing data as absence.

For each observed package, collect all upstream commits selected by its path at the frozen upstream head and validate those commits against the complete upstream graph. Compare complete parent and child package states to fingerprint file changes without unchanged text context. A matching SHA or patch establishes overlap with upstream, not which repository originated it; later upstream integration therefore remains ambiguous. A merge ending at an upstream parent's exact package state is synchronization evidence. A feature merge can be a candidate when its package exactly equals a side parent's state and every package transition newly introduced from its side history has no observed upstream overlap; preserve those introduced SHAs. Other merges remain unresolved. Retain an interval as a customization candidate only when every changed source step passes these checks. Mixed or ambiguous intervals are excluded under ADR 0018; pure synchronization is not customization activity. No global patch deduplication removes observations across forks or months.

The flow is frozen references, complete histories, lineage reconstruction, package change discovery, upstream evidence, complete endpoints, monthly instances and validation. `--num_samples` limits output candidates, never history completeness. An optional month bounds a pilot. Keep per-instance evidence, full endpoints and explicit omissions. Run exact behavioral fixtures and a real fork pilot; publish no research conclusions from engineering acceptance.

## Alternatives

- Sorting timestamps can join unrelated or reversed historical states.
- Comparing only commits currently ahead of upstream loses changes subsequently integrated upstream.
- Treating every unmatched patch as proof of independent authorship overstates what repository snapshots establish.

## Consequences

- Easier: monthly records have auditable contents, stable IDs and explicit zero changes.
- Harder: rewritten patches, package moves, ambiguous merges and historical branch changes limit attribution. Text patch fingerprints are exact evidence, not semantic equivalence; novel combinations of upstream edits may evade matching. Conservative exclusions may remove genuine customization. Human origin validation remains required before a main analysis.
- If reverted: rebuild monthly instances and annotations. Code locations: `src/domain.py`, `src/extract.py`, `src/config.py`, `eval/skill-pattern-mine/main.py`, and `tests/test_extract.py`.

[Commit API](https://docs.github.com/en/rest/commits/commits) and [blob API](https://docs.github.com/en/rest/git/blobs) specify the source fields and content encoding.
