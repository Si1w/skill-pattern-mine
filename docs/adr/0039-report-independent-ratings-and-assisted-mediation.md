# 0039. Report original ratings separately from assisted mediation

Date: 2026-09-24

## Status

accepted

## Context

The user confirmed completed annotation, stated that disagreements were not yet reconciled, requested independent results first, and then requested AI assistance as a mediator. Security raters shared evidence descriptions but assigned categories independently; all 109 task descriptions and 642 line descriptions match. All security A completion flags remain false despite complete fields and explicit user confirmation.

## Decision

Preserve and hash all four exports. Accept the user's explicit completion confirmation without rewriting flags or inferring completion from label presence. Apply ADR 0038's frame and existing agreement definitions, reporting original A/B judgments and security category distributions separately. Disclose shared security descriptions, including their potential influence on category judgments. Do not treat either rater as a gold standard.

Provide evidence grounded AI mediation suggestions separately, preserve unresolved cases and require human adjudication before claiming human consensus. Do not read model predictions during mediation or calculate model accuracy against AI suggestions. Suggestions must identify the task, disputed judgment, patch evidence and rationale; missing patch content is not evidence of no adaptation. This authorization permits assistance, not fabrication of human endorsement or retrospectively improved independent agreement.

Implementation: `legacy/eval/rebuttal/human_results.py`, annotation models in `models.py`, behavioral checks in `legacy/tests/test_human_results.py`, and supplementary outputs under `legacy/data/rebuttal/`. Results and reviewer replies are maintained in `Rebuttal.md`. Annotator backgrounds, human resolution, model reruns and venue limits remain outstanding.

## Alternatives

- Merge by union, intersection or preferred rater: changes labels without resolving their evidence.
- Describe AI suggestions as human consensus: misstates the validation provenance.

## Consequences

Original agreement remains auditable and separate from assistance. Lower agreement and incomplete historical evidence limit accuracy and risk claims. Inter-Rater Reliability and Open Science requirements are addressed through explicit provenance and preserved judgments, not through a claim of complete validation.
