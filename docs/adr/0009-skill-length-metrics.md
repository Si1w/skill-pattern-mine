# 0009. Length metrics for RQ3

Date: 2026-09-15

## Status

proposed

## Context

RQ3 asks whether skills get shorter over time and whether modifications shift from net growth to net shrinkage as model intelligence improves. The measure must be independent of language, deterministic, and comparable between the skill baseline and the modification.

## Decision

Primary measure is character count; secondary measure is the number of structural units (markdown headings plus list items); both are computed separately for prose and for fenced code blocks. File count per skill package is a supplement for the whole package. For each instance of monthly net change under [ADR 0013](0013-monthly-net-change-as-labeling-unit.md), measure the complete package at its before and after revisions, including unchanged files. Report the baseline and net change (after minus before), also relative to the baseline where defined. Verified activity with no net change has equal endpoint measurements and zero delta. These are package observations conditional on modification activity, not monthly snapshots of all existing skills. Translation handling within monthly intervals, eligible file types, code structural units, zero baselines and the global trend test remain unresolved.

## Alternatives

- **Token count with a fixed public tokenizer**: closer to what a model reads, but adds a tokenizer dependency and a proxy argument; trends would not differ from characters for before/after comparisons; rejected.
- **Word count**: no stable segmentation for CJK text; rejected.
- **Line count**: sensitive to wrapping and list conventions across repositories; rejected.

## Consequences

- Easier: shares the labeling endpoints; complete package trees are required in addition to content of changed files.
- Harder: absolute comparison across languages is unfair; mitigated by the relative measure and translation exclusion.
- If reverted: only the RQ3 measurement script changes.
