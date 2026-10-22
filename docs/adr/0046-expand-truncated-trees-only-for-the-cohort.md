# 0046. Expand truncated trees only for confirmed repositories

Date: 2026-10-21

## Status

accepted

## Context

ADR 0019 expands a truncated recursive tree response through its subtrees so that the package file ratio of ADR 0017 is measured on a complete inventory. The complete intent frame of ADR 0044 brings very large repositories into the candidate pool: 1,172 candidates have 1,000 forks or more and 101 of them exceed 500 MB. In the run started on 2026-10-21, `gradle/gradle` and `twentyhq/twenty` alone consumed 23,836 tree requests, the whole hourly quota for more than four hours, while the cohort is fixed at 30 repositories under ADR 0044 and none of these candidates can join it.

## Decision

Expand a truncated tree only for a repository listed in `screening.repositories`. For any other candidate, record the frozen branch and tree SHA, leave `tree_complete` false, measure nothing and keep the candidate pending; report the count as `trees_truncated` in the repository summary. The screening funnel therefore distinguishes candidates without a `SKILL.md` from candidates whose tree exceeded the API limits and was not inspected.

## Alternatives

- **Expand every truncated tree**: hundreds of thousands of requests for descriptive evidence about repositories outside the cohort.
- **Check only conventional paths such as `skills/`**: a partial inventory cannot support an absence claim and contradicts ADR 0017.

## Consequences

- Easier: a complete candidate run finishes within a few quota hours; the 30 confirmed repositories keep complete trees.
- Harder: the number of unreviewed candidates with a `SKILL.md` is a lower bound; truncated candidates are reported separately as not inspected.
- If reverted: expand all trees in a new run. Implementation: `src/repositories.py` (`complete_tree`, `freeze_and_screen`) and the tree tests.
