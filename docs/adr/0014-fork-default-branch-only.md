# 0014. Observe only each fork's default branch

Date: 2026-09-16

## Status

proposed

## Context

A fork may have divergent branches with no single shared monthly endpoint. The user chose observation restricted to the default branch on 2026-09-16 and accepted omission of changes confined to other branches. This resolves the branch selection required by ADR 0013 and narrows ADR 0011's observable population. Satisfies: Repository Mining/Essential "describes data preprocessing steps" and "discusses threats to external validity"; Longitudinal/Essential "subjects (humans or artifacts) are identifiable between waves".

## Decision

Mine the history reachable from the fork's default branch head frozen at retrieval. Record retrieval time, default branch name and head SHA; do not reselect the branch or follow its moving head during a run. This does not claim to reconstruct which branch was the default at every historical date. Each monthly observation is scoped to `(upstream, fork, skill, calendar month)` on that frozen lineage, with the branch and endpoint SHAs retained as provenance. Exclude histories of branches other than the default unless their changes are represented in the selected lineage.

The primary monthly denominator is distinct active pairs of owners and skills in this default branch population, including verified activity with no net change under ADR 0013. Count each pattern/family/category at most once per pair per month from the monthly net labels. Do not union labels from other branches. ADR 0015 assigns months from GitHub commit committer timestamps in UTC; choice of parent when traversing merges, nonmonotonic history, sync/translation treatment and stable skill identity remain separate decisions.

## Alternatives

- **All nonredundant fork branches**: captures additional work but requires separate lineages and branch weighting/aggregation; rejected by the user for the main study.
- **Most recently active branch each month**: can switch histories and compare states that do not belong to one coherent lineage.

## Consequences

- Easier: one frozen lineage per fork supplies reproducible monthly endpoint comparisons; collapsing branches whose commits are subsets of another branch is unnecessary for the main corpus.
- Harder: changes confined to other branches and history no longer reachable from the frozen default head are outside scope. Record this limitation rather than generalizing to all fork activity.
- If reverted: recollect branch histories and rebuild instances and downstream results. Code locations: `src/domain.py` (`Fork`, `Commit`, `Instance`); planned `configs/skill-pattern-mine.yaml` for retrieval configuration and `eval/skill-pattern-mine/main.py` for extraction of frozen history and monthly accounting.
