# 0034. Validate the legacy rebuttal evidence

Date: 2026-09-23

## Status

proposed

## Context

Reviews #1322A-C question annotation independence, security validity, aggregation, repository concentration and repeatability. [ADR 0033](0033-prioritize-legacy-rebuttal.md) fixes revision scope. The user has since specified a two day window and two independent raters for 293 common candidates. [ADR 0035](0035-two-day-local-rebuttal-analysis.md) records completed local analyses and [ADR 0036](0036-blind-audit-293-candidates.md) records the accepted sampling decision. The remaining proposals below, including model configuration, atomic relabeling and full paired security validation, are not completed; venue response rules and model budget remain unknown.

## Decision

Propose targeted validation using the modules below. These are recommendations, not completed experiments or approval of unresolved protocols.

| Work | Proposed method and implementation mapping |
| --- | --- |
| Annotation | Add blind mode to `legacy/src/audit/build_audit.py`. About 300 randomly sampled candidates from all 1,220, including zero-label records; two independent raters, then adjudication before model comparison. Use `legacy/eval/audit/metrics.py` for per-label support, precision/recall and set agreement. Verify discovery membership before claiming held-out status. A separate 50-80 record open-coding subset assesses taxonomy coverage. |
| Security | Extend `legacy/eval/label/rq4.py`; prefer auditing all 209 positive instances with context. Code textual meaning and change direction separately; report per-rule precision and instance outcomes. Compare identical packages at frozen baseline/head revisions. Sample negatives to check omissions. |
| Aggregation | Recover complete fixed-SHA histories using `legacy/src/mine/` evidence; relabel same-skill, same-commit modifications. Extend `legacy/eval/label/rq3.py` with support, prevalence and lift comparisons; report missing histories and repeated commits. Never propagate branch labels. |
| Concentration | Extend `legacy/eval/label/rq1.py`, `rq2.py`, `rq3.py` and `utils.py`: per-repository results, all repository exclusions, fork-cluster uncertainty within repositories and skill sensitivity. Fork resampling alone does not address shared skills. |
| Repeatability | Reuse `legacy/src/label/` inputs and fixed taxonomy for two independent recorded runs; compare raw predictions and downstream summaries separately from consensus labels. |
| Clarifications | Extend `rq2.py` with script availability and conditional modification. Recover PR associations at the original cutoff. Verify agreement aggregation in `legacy/eval/audit/metrics.py`. |

Before execution, settle sampling probabilities, annotator exposure, adjudication, risk categories, historical endpoints, uncertainty estimand/method, model configuration and budget. A sample size for one proportion does not guarantee precise rare-label recall. Keep targeted samples separate from population estimates, preserve ratings and failures, and identify post-review analyses as supplementary validation or sensitivity work.

## Alternatives

- **Reuse visible-label audits or regex counts as validation:** leaves anchoring and construct validity unresolved.
- **Redesign the entire study:** exceeds the focused revision and changes the population.

## Consequences

- Easier: evidence maps to reviewer questions and existing code.
- Harder: human effort, historical recovery and rare-label support limit conclusions.
- If reverted: narrow claims where evidence is unavailable. Applicable [ACM SIGSOFT standards](https://www2.sigsoft.org/EmpiricalStandards/docs/standards) cover Repository Mining (units and validated measures), Sampling (frame and rationale), Inter-Rater Reliability (independent ratings) and Open Science (reproducible materials); compliance remains incomplete.
