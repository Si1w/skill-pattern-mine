# 0022. Exclude collections of skills from other repositories

Date: 2026-09-16

## Status

proposed

## Context

The user clarified that Composio's collection must be excluded because it combines skills from other sources. The assistant had incorrectly treated stored package files as sufficient to escape aggregator exclusion. This affects the corpus for RQ1 to RQ4. Satisfies: Repository Mining/Essential "describes and justifies how the repositories are selected"; Sampling/Essential "explains the sampling strategy, in particular the different filtering steps involved".

## Decision

Replace ADR 0002's interpretation of aggregator exclusion: exclude repositories whose primary purpose is collecting or redistributing skills from other repositories, whether they store links or package files. Use README purpose, the delivered workflows and source credits together; record each exclusion and its reason. Neither locally stored packages nor an external citation alone settles this classification.

The user clarified that references, adaptations and accompanying imported skills do not by themselves disqualify a substantive skill workflow. Independent authorship of every package is not an inclusion condition: the study observes fork modifications, not original skill creation. K-Dense's scientific workflows and claude-obsidian's knowledge workflows remain eligible for consideration despite documented external sources. Reserve uncertain status for unclear primary purpose, rather than the mere presence of reuse. Do not invent an import cutoff. Translation handling remains separate.

## Alternatives

- **Exclude only directories of links**: fails the user's intended source boundary and retains repackaged collections.
- **Exclude every repository containing reused material**: confuses workflow dependencies and ordinary contributions with aggregation.

## Consequences

Reassess purpose recommendations before formal selection. A citation proves neither copying nor modification; retain source information and inspect version differences for synchronization and duplicate changes. Aggregation filtering does not replace deduplication. If reverted, screening and downstream counts must be rebuilt. Implementation: `src/review.py` explains the rule; `src/config.py` and `src/retrieve.py` already represent and apply `is_aggregator`; purpose review artifacts store provisional judgments and frozen evidence. `configs/skill-pattern-mine.yaml` receives only finalized reviews; frozen run inputs remain intact.
