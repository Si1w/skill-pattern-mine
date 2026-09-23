# 0025. Confirmed study repositories

Date: 2026-09-22

## Status

accepted

## Context

The purpose review recommended 31 repositories in the main scope. The user confirmed every repository in that list except `tt-a1i/archify`, whose primary deliverable requires clarification.

## Decision

Record the other 30 repositories as approved study repositories in `configs/skill-pattern-mine.yaml` and the purpose review YAML and CSV. Their identities are the main recommendations marked `human_decision: include`; preserve the existing four confirmed exclusions. Keep archify pending rather than infer its inclusion or exclusion from the user's question.

This confirms repository membership, not the completion of statistical calibration or fork acquisition. Do not invent a package file ratio cutoff or modify frozen acquisition snapshots. Before production acquisition, align the runner with the confirmed membership and create a new run because configuration has changed. Sensitivity candidates and other unconfirmed decisions remain separate.

## Alternatives

- Leave all 31 as provisional: loses the user's explicit approval of 30 repositories.
- Include or exclude archify automatically: treats a request for evidence as a selection decision.

## Consequences

- Easier: the approved research scope is explicit and traceable to the user's decision.
- Harder: archify remains unresolved, and the existing runner still requires a calibrated threshold for formal acquisition.
- If reverted: revise membership in a new ADR and rebuild affected acquisition runs. Implementation records: `configs/skill-pattern-mine.yaml`, `data/skill-pattern-mine/repository-purpose-review.yaml`, and its CSV companion.
