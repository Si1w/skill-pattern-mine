# 0019. Repository and fork acquisition

Date: 2026-09-16

## Status

accepted

## Context

The repository and fork pipeline needs a live engineering pilot before calibration or monthly annotation. GitHub search and comparisons can return incomplete results, while branch names can move during collection.

## Decision

Use the GitHub REST API through the authenticated `gh` CLI, with successful responses cached per run, pagination from response links, bounded retries and explicit failure records. Freeze configuration, the observation cutoff, repository IDs and branch SHAs. Derive intent topics from configured seed repositories, combine description searches with manifest searches and configured registry pointers, and retain all retrieval evidence. Search at the lowest sensitivity threshold and record the main threshold separately. Search saturation or incomplete responses prevent a complete retrieval claim. Expand truncated trees through their subtrees before measuring file ratios. Human screening decisions and a calibrated ratio threshold are required for formal inclusion.

The event flow is discovery, metadata and branch freezing, complete tree measurement, screening, fork enumeration, fork branch freezing, then paginated comparison against the frozen upstream SHA. Store comparison commits with ordered parents and both timestamps. These commits establish divergence at retrieval; they do not establish modification origin or monthly observations. Do not use the comparison file list as a complete package diff. Resume with the same configuration and sample bounds; offline replay must use only saved responses.

An explicit `--pilot --num_samples N` processes at most N search hits per query, N candidate repositories and N forks per repository, with at most N comparison commits per fork. Pilot forks are selected by configured order for engineering coverage, not statistical representativeness. Candidates with skill packages may enter this pilot while human review is pending, but remain excluded from the formal retained count. The pilot passes only if both retrieval channels run, complete tree measurements and frozen fork comparisons are produced, and no acquisition errors occur. Store machine readable acceptance results with the run. YAML configuration uses pinned PyYAML.

## Alternatives

- Treating API failure or truncation as empty data would invalidate screening and activity counts.
- Selecting pilot candidates as formally retained would bypass the calibration and manual review in ADR 0002.

## Consequences

- Easier: collection can be tested, resumed and replayed before annotation; errors and engineering bounds remain visible.
- Harder: search coverage, human calibration and monthly origin attribution still require separate validation. Enumeration is acquired over time and is not an atomic GitHub snapshot.
- If reverted: rebuild acquisition artifacts and all dependent observations. Implementation uses `src/github.py`, `src/retrieve.py`, `src/config.py` and `eval/skill-pattern-mine/main.py`; behavioral checks live in `tests/`.

## API references

[Search limits](https://docs.github.com/en/rest/search/search), [fork pagination](https://docs.github.com/en/rest/repos/forks), [tree truncation](https://docs.github.com/en/rest/git/trees) and [comparison limits](https://docs.github.com/en/rest/commits/commits#compare-two-commits) define the collection constraints.
