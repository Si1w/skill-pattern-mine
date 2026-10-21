# 0013. Monthly net change as the labeling unit

Date: 2026-09-16

## Status

proposed

## Context

The user confirmed replacing labeling each commit and monthly label unions with direct labeling of monthly net changes on 2026-09-16. RQ1, RQ2 and RQ4 should describe changes remaining at the end of a monthly comparison interval, and RQ3 should measure the corresponding net length change. Satisfies: Repository Mining/Essential "defines unit(s) of analysis or observation" and "describes and justifies measures or metrics used"; Longitudinal/Essential "discusses the operationalization of the research model". This supersedes ADR 0004 and ADR 0012.

## Decision

For a skill package on a single recorded fork lineage, compare the package state immediately before its first eligible modification of the month with its state immediately after its last eligible modification of that month. Preserve both revision references and the intervening source history. Compute the endpoint diff first; apply security rules and LLM labeling directly to this monthly net diff, without unioning intermediate commit labels. Use the same complete package endpoints for length measurements. Calendar month is the analysis time coordinate, not one representative commit date.

Retain otherwise eligible modification activity that returns to exactly the same package state as an explicit record with no net change, contributing to the active denominator with no pattern/security labels and zero length delta. Such records need no LLM call; missing content, failed extraction and failed labeling must never be treated as no net change. Inactive objects do not contribute. Under ADR 0018, intervals whose customization and upstream changes cannot be separated are excluded from both the numerator and denominator. Claims concern monthly net outcomes, including changes that may be reversed in a later month, rather than every behavior within that month. Labels may still occur together and observations may recur across months.

## Alternatives

- **Commit labeling followed by monthly label union**: counts transient/reverted behavior and allows intermediate activity to accumulate types that do not survive in the monthly outcome.
- **State after the first monthly change as baseline**: omits that first change from the comparison.
- **Discarding activity with no net change**: conditions the denominator on producing a surviving change.

## Consequences

- Easier: a monthly endpoint comparison has one direct annotation; splitting an identical final change across commits does not change its diff.
- Harder: ADR 0014 selects the frozen fork default branch; ADR 0015 assigns months using GitHub committer timestamps in UTC. ADR 0018 sets the exclusion policy for unresolved upstream origin, but the detector, merge ancestry, nonmonotonic timestamps, package identity across renames and translation handling remain unresolved. Endpoints must come from one lineage; filtering source records does not remove edits from endpoint trees. Inference must still account for repeated observations.
- If reverted: rebuild instances, discovery/audit samples, labels and length measurements. Code locations: `src/domain.py` for monthly instances, endpoint references and status indicating no net change; planned `eval/skill-pattern-mine/main.py` for extraction, labeling and analysis, and `configs/skill-pattern-mine.yaml` for temporal parameters.
