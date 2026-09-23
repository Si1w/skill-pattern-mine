# 0004. Each commit and skill package as the unit of analysis

Date: 2026-09-14 (revised 2026-09-15)

## Status

superseded by 0013

## Context

The legacy unit was a fork branch compared to upstream, labeled on the merged diff. A branch spans several commits with different dates, so labels for branches cannot be placed on a timeline without a convention for choosing a representative date that misdates part of the change. A bare commit has two weaknesses of its own: counts depend on committing habits (thirty small commits versus one squash), which may themselves change over time, and one commit can touch several skill packages, leaving labels and length metrics without a skill to attach to.

## Decision

One instance is one (commit, skill package) pair: a substantive commit unique to the fork owner that changes an existing skill package in a fork branch. Its timestamp is the commit author date; labels and length metrics attach to that skill. Make one labeling call per commit, group its input by package, and expand the returned package labels into instances. Report prevalence per instance and monthly presence among active pairs of owners and skills as specified in [ADR 0012](0012-monthly-active-owner-skill-prevalence.md). The latter is the primary temporal measure and reduces weighting by commit frequency without removing dependence between repeated observations. Reconstruct branch views as unions for comparison with the legacy paper.

## Alternatives

- **Labels for branches with a representative date**: misdates branches containing activity across several months; rejected.
- **Bare commit**: inflation caused by commit habits and no skill attribution; rejected.
- **Hunk or file level**: patterns span hunks; fragmentary labels and unmanageable counts; rejected.
- **Editing sessions (commits by one owner clustered in a time window)**: adds a window parameter and a date compromise; kept only as a sensitivity check.

## Consequences

- Easier: time and labels at the same granularity; every label has a skill; RQ3 baselines are defined per skill; API calls stay at commit count; human audit size is fixed by ADR 0008 regardless of instance count.
- Harder: more API volume than branch labeling; deduplication using patch identifiers for each package becomes critical.
- If reverted: labeling must be redone on merged branch diffs.
