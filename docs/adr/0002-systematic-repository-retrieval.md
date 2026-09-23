# 0002. Systematic repository retrieval protocol

Date: 2026-09-14 (revised 2026-09-15)

## Status

proposed

## Context

The legacy corpus used six seed repositories selected by keyword search, a threshold of 20,000 stars and an unrecorded manual exclusion step. Retrieval based only on the presence of `SKILL.md` would also admit repositories where skills are incidental to a larger software project. We need a reproducible protocol with recorded counts at every step.

## Decision

The aggregator exclusion is clarified by [ADR 0022](0022-exclude-repackaged-skill-collections.md): repositories primarily collecting skills from other sources are excluded even when they store actual package files; references or accompanying reused skills alone do not disqualify a substantive skill workflow. The narrower wording about lists of links below records the earlier interpretation and no longer governs this exclusion.

The file counts follow [ADR 0017](0017-skill-centricity-over-tracked-files.md), including Markdown in both numerator and denominator. Preserve membership in every retrieval channel. An unassessed candidate is not a retained repository; record screening completion separately. Do not exclude forks based on the five minute interval previously introduced in the interface. Establish qualifying modification activity from commit history.

Retrieve candidates through two channels: (1) repository intent, via GitHub repository search on topics about skills and description keywords, the topic list derived from topic frequencies of known skill repositories; (2) distribution manifests, via repositories carrying plugin or marketplace manifests plus pointers from public skill registries. `SKILL.md` code search is used only to estimate coverage relative to that search frame, not absolute recall against an unknown population. Apply, in order: a hard minimum of 1,000 forks on the GitHub metadata fork count, justified as a proxy available before mining for modification volume, with sensitivity analysis at 500 and 2,000 and no star threshold; then a package file ratio rule (tracked files under skill packages divided by all tracked files), with the threshold calibrated on a calibration set stratified by membership in retrieval channels, validated on a separate validation set, and a narrow boundary band reviewed manually; then an aggregator exclusion for repositories organized as lists of links, flagged by name, description or topic keywords (awesome, collection, curated) and confirmed by a manual pass over the whole retained pool, which the fork threshold keeps small. Any manual exclusion is published as an explicit list with reasons. Every step reports counts.

## Alternatives

- **`SKILL.md` code search as the inclusion source**: admits repositories where skills are incidental; rejected.
- **No fork threshold, or a threshold derived from the fork distribution**: repositories with few forks yield too few modifications to observe patterns; a fixed, reportable number is preferred.
- **Star threshold**: popularity is not modification volume; junk repositories are handled by the content rules and bot filtering; dropped.
- **Structural rule "only skill packages and docs in the tree"**: excludes legitimate skill repositories with helper scripts; rejected.
- **Keeping aggregators organized as lists of links**: multiple sources per repository break attribution and analyses of each repository; excluded.
- **Aggregator rule based on similar lineage detection**: unnecessary once the retained pool is small enough to check by hand; rejected.

## Consequences

- Easier: selection is fully parameterised in `configs/` and reproducible; rule quality (precision, recall, kappa between auditors) is reportable.
- Harder: two auditors must label the calibration sample and a separate validation sample before screening is finalized.
- If reverted: the corpus and all downstream counts must be rebuilt.
