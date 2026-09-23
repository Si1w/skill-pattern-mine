# 0018. Exclude changes whose upstream origin cannot be resolved

Date: 2026-09-16

## Status

proposed

## Context

A monthly package diff can combine customization in a fork with changes imported from upstream. Removing synchronization commits from a list does not remove their effects from the endpoint versions. The user approved excluding intervals whose contributions cannot be separated reliably and requested no separate results for them. This applies to RQ1 to RQ4. Satisfies: Repository Mining/Essential "describes data preprocessing steps"; General/Essential "discloses all major limitations".

## Decision

Exclude the affected package and month from the main analysis when its endpoint diff contains both customization and upstream changes whose origins cannot be distinguished reliably. Exclusion applies to both the numerator and denominator, including length analysis and the main annotation audit. Do not exclude the entire fork or unaffected months. Do not infer customization solely from a commit message or the fork owner's identity.

Keep the raw history, affected observation identity, exclusion reason and supporting evidence in the extraction records so the retained sample can be reproduced. Do not produce a separate analysis, table or figure for excluded intervals. The sampling method must state the exclusion rule; ordinary extraction counts remain available without adding a dedicated results section. The detector and evidence needed to establish origin remain to be specified before this rule can be executed.

## Alternatives

- **Include the combined diff as customization**: attributes changes from upstream to the fork.
- **Remove synchronization commits and compare the same endpoints**: imported changes remain in the endpoint content.
- **Analyze excluded intervals separately**: not requested by the user.

## Consequences

- Easier: the main results concern changes that can be attributed to customization without requiring an additional analysis.
- Harder: the sample may underrepresent forks that synchronize frequently. Record this limitation; do not describe the retained sample as all default branch activity.
- If reverted: rebuild the affected sample, labels and results. Code locations: `src/domain.py` for the observation's exclusion reason, `configs/skill-pattern-mine.yaml` for the policy, and planned extraction and analysis stages for filtering. The origin detector is not implemented by this ADR.
