# 0006. API labeling pipeline with a fixed model and structured output

Date: 2026-09-14 (revised 2026-09-15)

## Status

proposed

## Context

Legacy labeling ran inside Claude Code agents, which exposed no stable model snapshot or sampling control, a threat to the validity of conclusions the paper had to acknowledge. Labeling monthly net changes under ADR 0013 requires batch execution and output checked by code.

## Decision

Label through a direct API pipeline with GPT-5.6 Luna at reasoning effort `medium`, unchanged for the whole corpus, executed via the Batch API. A frozen system prompt carries evidence rules, scope rules, rules for judging security changes and the injected taxonomy. Each request labels one nonzero monthly package net diff under [ADR 0013](0013-monthly-net-change-as-labeling-unit.md), with before/after content and matches from security rules. Source commits are retained for traceability; their intermediate labels are not unioned. Output is enforced by a strict JSON schema containing `patterns` (taxonomy `name` from an enum plus `confidence` high, medium, low), `diff_sufficiency` (sufficient, truncated, empty) and `security` (`rule_id` plus `direction` hardening, relaxation, neutral, false_positive). Explicit records with no net change need no API call and carry empty labels with no model provenance. Each record returned by the API stores model, system fingerprint, prompt version, taxonomy version, effort, request id and usage. A low, medium, high effort agreement comparison on the bootstrap sample is reported in the appendix.

## Alternatives

- **Claude Code agents** (legacy): no fixed model snapshot; rejected.
- **Evidence and rationale fields in the output**: not used in statistics and still require human review; dropped, evidence discipline stays as a prompt rule.
- **Switching model or effort during corpus labeling**: would confound annotator change with time; forbidden.

## Consequences

Before implementation, verify the actual API model identifier and supported options. Preserve raw requests, responses, failures, retry attempts and configuration hashes. Validate taxonomy membership, duplicate labels and the requested package identity; a schema description alone does not enforce these constraints. A refusal, truncation or missing package must not become an empty successful label.

- Easier: reproducible calls, invalid labels rejected by the schema, annotator independent of the studied Claude ecosystem.
- Harder: model identifier and schema limits must be verified before the run; a model update by the provider (fingerprint change) must be reported.
- If reverted: all labels must be regenerated.
