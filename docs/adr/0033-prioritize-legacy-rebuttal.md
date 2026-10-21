# 0033. Prioritize the legacy rebuttal

Date: 2026-09-23

## Status

accepted

## Context

The user has prioritized responding to reviews #1322A-C and requested revisions based on `legacy/`. The submitted study contains 1,220 labeling candidates and 1,126 analyzed branch instances from six repositories. The separate monthly study does not reproduce this population.

## Decision

Prioritize the legacy rebuttal and maintain its evidence and response tracker in [Rebutal.md](../../Rebutal.md). Extend existing modules under `legacy/`, preserving original inputs, model outputs and published results, and save supplementary outputs separately. Unresolved experimental choices remain proposed in [ADR 0034](0034-legacy-rebuttal-validation.md).

This addresses ACM SIGSOFT Repository Mining requirements to define observation units and describe preprocessing, and General requirements to align evidence with claims. Validation is not yet complete.

## Alternatives

- **Replace the submitted corpus with the monthly study:** changes the population and units while answering reviews of a different study.
- **Revise only the prose:** leaves independent annotation, measurement validity and aggregation concerns unresolved.

## Consequences

- Easier: supplementary evidence remains comparable with submitted results.
- Harder: historical recovery and human validation remain necessary.
- If reverted: revisit revision scope and comparability. Existing monthly ADRs remain unchanged; this priority decision does not stop any running collector.
