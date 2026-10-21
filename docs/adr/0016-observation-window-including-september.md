# 0016. Observation window including September 2026

Date: 2026-09-16

## Status

proposed

## Context

The user requested including September rather than ending the study in August. Under ADR 0015, months are defined by committer timestamps in UTC. Collection during September yields a partial final month that must remain distinguishable from completed months. Satisfies: General/Essential "describes in detail what, where, when and how data were collected"; Longitudinal/Essential "explains how missing data are handled".

## Decision

Retain available history from the earliest verifiable eligible fork modification through September 2026. At acquisition start, freeze one common UTC observation cutoff for the run: acquisition start if it occurs during September, otherwise October 1, 2026 at 00:00:00 UTC for collection after September. Include source changes strictly before that cutoff. No acquisition timestamp or dataset snapshot has yet been recorded by this decision.

Use the same cutoff for every fork even if retrieval finishes later, retaining each fork's actual retrieval time and frozen head SHA separately. Preserve older ancestry when required to resolve the first observed baseline; that context is not an additional observed modification. If the cutoff is within September, retain September's observations and label the month as partial in analysis tables and figures, with its exact observed interval and active denominator. Do not extrapolate the observed changes to an assumed full month. The inference plan must explicitly handle unequal observation periods before statistical testing.

## Alternatives

- **Stop at the end of August**: rejected by the user because September should be included.
- **Assume all of September is observed before the end of the month**: would imply access to unobserved future activity.
- **Use each fork's retrieval time as its observation cutoff**: gives forks unequal upper bounds within the same run.

## Consequences

- Easier: includes the requested recent activity while keeping one reproducible upper bound.
- Harder: a partial September has a shorter opportunity to accumulate net changes; prevalence among active pairs alone does not remove this exposure difference. Historical coverage gaps remain separately reportable.
- If reverted: rebuild affected monthly instances and downstream samples/results. Code locations: planned `configs/skill-pattern-mine.yaml` and a persisted run manifest for the resolved cutoff, `eval/skill-pattern-mine/main.py` for interval selection and reporting of partial months; `src/domain.py` retains each instance's month and each fork's retrieval metadata.
