# 0001. Temporal redesign of the main study

Date: 2026-09-14

## Status

proposed

## Context

The legacy study pooled all fork modifications collected on 2026-04-28 into one static corpus, while frontier model capability changed several times inside the observation window. We want to keep the pattern taxonomy and the security direction but add whether modification behaviour changes over time as model intelligence improves. Coverage of commit messages (legacy RQ5) is out of scope for now.

## Decision

Rerun the study with four research questions: RQ1 patterns and prevalence of monthly net modifications; RQ2 changes in family prevalence over time; RQ3 changes in package length before modification and the net length change each month; RQ4 categories and directions of net modifications relevant to security, and how they vary over time. Calendar month is the analysis time coordinate under [ADR 0013](0013-monthly-net-change-as-labeling-unit.md); source commit timestamps remain provenance. Frontier model releases, Agent Skills spec changes and Claude Code feature releases appear as reference lines from a verified table in `configs/`. No causal claim is made. The temporal inference procedure remains unresolved because observations repeat across months and may have multiple labels.

## Alternatives

- **Discrete epochs split at model releases**: implies a behavioural break on release day that we cannot defend; confounded with ecosystem maturation.
- **A separate regression over time for each family**: originally rejected because it produces many coefficients and comparisons. The proposed replacement, a plain chi squared test of months and families, also needs reconsideration because observations repeat and labels overlap. The choice of a monthly observation unit does not approve an inference procedure; plots must distinguish prevalence of overlapping labels from composition.
- **Lifecycle / survival analysis of pattern instances**: answers retention rather than modification behaviour; rejected as a change of research object.

## Consequences

- Easier: reporting uses monthly net outcomes; raw source history preserves timing within each month for traceability.
- Harder: time, ecosystem maturity and harness evolution are collinear; mitigated by reference lines for each and a sensitivity analysis on repositories present for the whole window.
- If reverted: the retrieval, labeling and validation ADRs (0002 to 0007) still hold; only the analysis scripts change.
