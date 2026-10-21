# 0035. Execute the two day rebuttal analysis

Date: 2026-09-23

## Status

accepted

## Context

The user authorized immediately executable analyses and requested completed results, human tasks and infeasible work in `Rebutal.md`, with two days available. ADR 0034 remains the broader proposed validation design.

## Decision

Implement local supplementary analysis in `legacy/eval/rebuttal/` and save each run under `legacy/data/rebuttal/{run_id}/`. Reuse the original corpus, taxonomy and surface definitions. Report all repository exclusions, per-repository results, one-skill and one-retained-commit subsets, aggregation counts, raw-versus-consensus sensitivity and corrected agreement calculations. Subsets are descriptive sensitivity analyses, not atomic relabeling. Compute exploratory percentile intervals from 2,000 fork-cluster resamples within the six fixed repositories, seed 42; these intervals concern this corpus composition, not a population of repositories or skill-independent effects.

Read local Git trees at saved baseline SHAs for script availability, separating frozen-index package counts, historical package-version counts and branch-package opportunities. Added scripts are distinct from changes to baseline scripts. Verify history availability and collect read-only PR metadata when accessible, separating branch associations from exact frozen-head matches. Prepare unfilled human audit materials, never AI substitutes for independent human judgments. Correct unsupported manuscript wording without inventing validation results.

## Alternatives

- **Wait for all human work:** wastes the limited window for deterministic checks.
- **Treat new AI labels as human validation:** does not answer the reviewers' concern.

## Consequences

- Easier: executable evidence and human work proceed independently; supplementary outputs preserve the original artifacts.
- Harder: partial histories, annotation exposure, rare labels and clustering across skills remain explicit limits. Sampling size and human capacity remain unresolved under ADR 0034.
- If reverted: retain this supplementary run but remove its claims from the response. ACM SIGSOFT Repository Mining, Sampling, Inter-Rater Reliability and Open Science obligations are addressed through explicit units, methods, provenance and limitations; they are not all satisfied.
