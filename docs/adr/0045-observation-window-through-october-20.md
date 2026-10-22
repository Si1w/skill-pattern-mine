# 0045. Observation window through 2026-10-20

Date: 2026-10-21

## Status

accepted

## Context

ADR 0016 fixed October 1, 2026 as the cutoff for collection after September. Acquisition now starts on 2026-10-21, so the fork histories being collected contain twenty further days that the cap would discard. The user asked on 2026-10-21 to extend the window to October 20.

## Decision

Set the exclusive observation cutoff to 2026-10-21T00:00:00Z, so that source changes committed through 2026-10-20 UTC are observed. October 2026 is a partial month and follows the rules ADR 0016 gave for a partial September: it stays in the data, is labeled partial with its observed interval in tables and figures, and is never extrapolated to a full month. Every run freezes the earlier of this cutoff and its own start time; the previous pair of settings, a cap and an optional cutoff, collapses into the single setting `observation.cutoff_utc`.

## Alternatives

- **Keep October 1**: discards twenty days that are collected anyway and leaves the final full month four weeks behind acquisition.
- **Freeze the cutoff at acquisition start of each run**: gives runs created on different days different windows; a fixed timestamp keeps the candidate run, the pilot and the full run comparable.

## Consequences

- Easier: the window ends as close as possible to acquisition while remaining one fixed, reproducible bound.
- Harder: the final month covers twenty days and must be handled as partial in every monthly analysis, as ADR 0016 already required.
- If reverted: set `cutoff_utc` back to 2026-10-01T00:00:00Z and recreate the runs. This supersedes ADR 0016. Implementation: `configs/skill-pattern-mine.yaml`, `src/config.py`, `src/run.py`.
