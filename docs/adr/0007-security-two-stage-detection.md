# 0007. Detect changes relevant to security in two stages

Date: 2026-09-14

## Status

proposed

## Context

The legacy study detected changes relevant to security using only regular expressions (`security_rules.yaml`). Rules identify candidates but cannot decide whether a change hardens or relaxes a constraint.

## Decision

Stage one: rule matching on added and deleted lines of each monthly package net diff under [ADR 0013](0013-monthly-net-change-as-labeling-unit.md), with the rule set revised once after taxonomy open coding surfaces new categories. Stage two: for monthly instances with matches, the labeling model judges each match as hardening, relaxation, neutral or false positive inside the same labeling call. Instances without matches receive no model security judgement; the rule miss rate is estimated from monthly instances relevant to security found by auditors in the validation sample. Reported quality metrics are rule precision and miss rate. Changes fully reversed within the month are not security net changes; independent audit representation and match identity remain to be resolved.

## Alternatives

- **Rules only**: no direction; rejected.
- **Model only over all commits**: recall not measurable against a fixed rule set; rejected.

## Consequences

Before implementation, give each rule match an identity tied to its source location. Allow auditors to record relevance, category, direction and evidence without requiring a rule hit. Define rule precision, false negatives among human positives, prevalence among rule negatives, and final direction accuracy separately. The existing `rule_id` alone cannot express these observations reliably.

- Easier: RQ4 yields monthly category prevalence and hardening vs relaxation curves with reportable detector quality.
- Harder: misses outside the rule set are only estimated, not recovered.
- If reverted: security fields in labels must be regenerated.
