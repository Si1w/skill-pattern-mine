# 0012. Monthly prevalence among active pairs of owners and skills

Date: 2026-09-16

## Status

superseded by 0013

## Context

ADR 0004 defines presence for each owner and skill but leaves its temporal aggregation unspecified. The user confirmed monthly prevalence among active pairs on 2026-09-16. This clarifies pattern/family prevalence in RQ2 and category prevalence in RQ4; conditional proportions of security directions remain a separate decision. Satisfies: Repository Mining/Essential "defines unit(s) of analysis or observation" and "describes and justifies measures or metrics used"; Longitudinal/Essential "subjects (humans or artifacts) are identifiable between waves".

## Decision

For each calendar month, the denominator is the number of distinct pairs of owners and skills with at least one eligible modification in that month, within ADR 0011's population. Owner means fork owner; skill identity is scoped to its upstream repository. For a pattern, family, or security category, the numerator counts those pairs with at least one occurrence during that month, once per pair regardless of commit count. Family presence is the union of its constituent patterns. The same pair may contribute again in later months; inactive pairs are absent from the month's denominator. A month with no eligible pairs has undefined prevalence, not zero. Multiple types may occur for one pair, so percentages need not sum to 100%.

## Alternatives

- **Prevalence per instance as the primary temporal measure**: weights pairs by their number of commits; retain only as the complementary view specified in ADR 0004.
- **One presence count over the entire observation window**: cannot locate recurring behavior in individual months.
- **All observed pairs in every month's denominator**: changes the question to activity among a standing population and requires an explicit definition of the observed population at risk.

## Consequences

- Easier: each active pair has equal weight within a month; estimates describe behavior conditional on modification activity.
- Harder: repeated pairs, shared owners/upstreams, and labels that occur together remain dependent. Monthly aggregation reduces weighting by commit frequency but does not eliminate effects of splitting commits across months. The inference procedure, timezone, stable identity across renames, and handling of incomplete labels remain unresolved.
- If reverted: temporal aggregates and figures must be recomputed; instance labels need not change. Code locations: `src/domain.py` for the documented observation/aggregation distinction; planned `eval/skill-pattern-mine/main.py` for monthly presence aggregation and `configs/skill-pattern-mine.yaml` for temporal parameters.
