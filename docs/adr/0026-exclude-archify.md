# 0026. Exclude archify

Date: 2026-09-22

## Status

accepted

## Context

ADR 0025 confirmed 30 main study repositories and left archify unresolved. At frozen commit `4e45fe77a31bcdff35f73a277531c51632da7359`, archify's README describes a Node.js rendering and validation system, with a skill interface and directly usable CLI, renderers, and preview commands.

## Decision

The user explicitly excludes `tt-a1i/archify` because the primary deliverable includes a complete diagram tool rather than solely the skill workflow sought for this corpus. Record a manual purpose exclusion with `is_aggregator: false` and `exclude: true`. This resolves the open case in ADR 0025; its 30 approved inclusions remain unchanged. Do not treat the mere presence of helper code as an exclusion rule for other approved repositories.

## Alternatives

- Include archify as a combined skill and tool: the user declined this boundary case.
- Leave archify pending: no longer reflects the explicit decision.

## Consequences

- Easier: the main recommended inclusion list now matches the 30 user approvals.
- Harder: the primary deliverable boundary requires repository purpose evidence, not only manifest or source file counts.
- If reverted: update the review and acquisition membership through a new ADR. Update the current config and purpose review YAML and CSV; preserve the original frozen acquisition files.
