# 0047. Cohort by purpose review of all candidates with 3,000 forks or more

Date: 2026-10-22

## Status

superseded by 0048

## Context

ADR 0044 fixed the cohort at the 30 repositories confirmed in September and left every other eligible candidate pending. The complete retrieval frame of the candidate run `candidates-v3` (searched 2026-10-21) surfaced 1,172 candidates with 1,000 forks or more, 466 of them structurally eligible but never reviewed, among them `mattpocock/skills` with 25,170 forks. The user decided on 2026-10-22 that membership must come from a purpose review of every eligible candidate above a threshold, that the September confirmations carry no guarantee, and that the threshold should make the review tractable.

## Decision

Raise the fork threshold to 3,000. Review every structurally eligible candidate at or above it in `candidates-v3`, 194 repositories, against one criterion: the repository primarily distributes agent skills. Exclude curated lists, directories and catalogs of skills from other sources (ADR 0022), and repositories where skills are a byproduct of a software product, library, framework, application, tutorial or template (ADR 0026). The full table with one decision and reason per candidate is `docs/repository-review-2026-10-21.csv`; the assistant drafted it from each repository's description, README, package paths and package file ratio, and the user confirmed the threshold and adjudicated the nine borderline cases on 2026-10-22.

The cohort is the 31 repositories marked include, listed in `screening.repositories`. Thirteen of the September repositories remain; seventeen fall below 3,000 forks and leave the cohort for that reason alone (seven of them have between 2,000 and 2,999 forks). Eighteen repositories enter: `mattpocock/skills`, `garrytan/gstack`, `nextlevelbuilder/ui-ux-pro-max-skill`, `coreyhaines31/marketingskills`, `BillionsNetwork/verified-agent-identity`, `zhaoxuya520/reverse-skill`, `bmad-code-org/BMAD-METHOD`, `hugohe3/ppt-master`, `alchaincyf/nuwa-skill`, `mukul975/Anthropic-Cybersecurity-Skills`, `Imbad0202/academic-research-skills`, `anthropics/knowledge-work-plugins`, `browser-use/video-use`, `ayghri/i-have-adhd`, `ai-job-search-dev/ai-job-search`, `JuliusBrussee/caveman`, `anthropics/financial-services` and `pbakaus/impeccable`. (Counts corrected on 2026-10-22; the first version of this record miscounted the retained repositories as twenty.) The package file ratio stays descriptive (ADR 0042). The retrieval frame of ADR 0044 is unchanged; the candidate run needs no new search because its floor of 1,000 covers the new threshold.

## Alternatives

- **Keep the fixed cohort of 30**: leaves the third largest skill repository out for no reason other than the date of retrieval.
- **Threshold 2,000**: 282 candidates to review for 16 further small repositories; **threshold 5,000**: only 15 repositories, almost all head of the distribution.
- **Review only candidates with a high package file ratio**: the ratio was never calibrated and a root manifest inflates it to 1.0.

## Consequences

- Easier: the selection funnel is reproducible from one search date, one threshold, one structural rule and one published review table.
- Harder: the cohort grows to about 271,000 forks; the review was drafted by an assistant and confirmed by one person, which the paper must state; borderline judgments are documented but not independently rated.
- If reverted: restore the previous list and threshold in the configuration and import from `candidates-v3` again. This supersedes ADR 0025 and the membership rule of ADR 0044. Implementation: `configs/skill-pattern-mine.yaml`, `docs/repository-review-2026-10-21.csv`, tests.
