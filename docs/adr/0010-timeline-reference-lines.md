# 0010. Reference lines on the timeline

Date: 2026-09-15

## Status

proposed

## Context

ADR 0001 now reports monthly net changes under ADR 0013 and uses reference lines instead of epochs defined by releases. The lines provide context about model, harness and specification timing; they cannot attribute observed changes to those events. "Model intelligence" refers to frontier capability available to the ecosystem, not to one vendor's product line.

## Decision

Three classes of reference lines, stored as a verified date table in `configs/`: (1) major model releases from Anthropic (Claude) and OpenAI (GPT), drawn with one line style per vendor; (2) Agent Skills specification milestones; (3) major Claude Code feature releases, the latter two sharing a third line style. Other vendors' releases are mentioned in the text only. Every date is verified against the vendor's announcement before entering the table; nothing is filled from memory.

## Alternatives

- **Claude releases only**: the skills spec is now used across vendors and "model intelligence" is a frontier notion; rejected.
- **All vendors on the figure**: illegible; rejected.

## Consequences

- Easier: one table drives every figure; readers can compare changes with model or harness timing without causal attribution.
- Harder: the table must be maintained if the observation window is extended.
- If reverted: only plotting changes.
