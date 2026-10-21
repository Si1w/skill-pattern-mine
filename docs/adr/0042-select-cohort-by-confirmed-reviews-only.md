# 0042. Select the cohort by confirmed reviews only

Date: 2026-10-21

## Status

accepted

## Context

ADR 0002 proposed a calibrated package file ratio threshold as one screening step. The threshold was never calibrated: ADRs 0025 and 0027 instead confirmed the 30 study repositories by explicit human review, and the ratio has only ever been reported as descriptive evidence. The code still carried a `calibrated_ratio` selection mode with an unset threshold, which no run used and which every test had to switch on to exercise unreviewed candidates.

## Decision

Formal membership in the cohort is defined only by `screening.reviews` in the experiment configuration: a repository is retained when a human review exists and neither excludes it nor marks it as an aggregator. The structural steps of ADR 0002 remain: the fork threshold, the presence of a regular `SKILL.md` manifest, and the recorded ratio under ADR 0017. Unreviewed candidates remain pending and may only be collected in a bounded pilot. The `repositories` step discovers and screens candidates when no source run is given, and imports the approved cohort from a candidate run when `--source_run` is given. The `selection_mode` and `skill_centricity_threshold` settings are removed. This replaces the calibrated ratio rule of ADR 0002; its retrieval channels, fork threshold and aggregator exclusion are unchanged.

## Alternatives

- **Keep the mode for a future calibration**: the threshold would need a calibration set and validation set that the study no longer plans, and the unused branch costs readability now.
- **Calibrate the threshold now**: changes the confirmed cohort of ADR 0025 after acquisition decisions were made on it.

## Consequences

- Easier: one selection rule, one path through screening, and tests that use pending candidates without changing modes.
- Harder: any later claim about ratio based selection must be made as a new decision with its own calibration.
- If reverted: restore the two settings and the ratio exclusion branch in `src/repositories.py`. Implementation: `src/config.py`, `src/repositories.py`, `src/verify.py`, `src/review.py`, `eval/skill-pattern-mine/main.py`, `configs/skill-pattern-mine.yaml` and the behavioral tests.
