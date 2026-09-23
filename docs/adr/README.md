# Architecture decision records

The immediate priority is the legacy rebuttal under [ADR 0033](0033-prioritize-legacy-rebuttal.md), tracked in [Rebuttal.md](../../Rebuttal.md). Its validation protocol is proposed in [ADR 0034](0034-legacy-rebuttal-validation.md). The monthly study decisions below remain separate and unchanged.

Design decisions, implementation mappings and remaining questions are maintained in this directory. Statuses mirror the source ADRs. The Standards column identifies relevant ACM SIGSOFT requirements; it does not claim that all requirements have been satisfied. ADR 0013 replaces 0004 and 0012. The current study uses monthly net changes on frozen fork default branches, UTC committer timestamps, and an observation window that includes September. Routine implementation decisions are delegated to the engineer; changes to research scope, attribution or interpretation still require discussion.

| ID | Title | Status | Date | Standards |
| --- | --- | --- | --- | --- |
| [0001](0001-temporal-redesign-of-main-study.md) | Temporal redesign of the main study | proposed | 2026-09-14 | General: questions, analysis; Longitudinal: temporal design |
| [0002](0002-systematic-repository-retrieval.md) | Systematic repository retrieval | proposed | 2026-09-15 | Repository Mining: selection and validation; Sampling: frame and filtering |
| [0003](0003-three-level-deduplication.md) | Deduplication at three levels | proposed | 2026-09-15 | Repository Mining: preprocessing; Longitudinal: subject identity |
| [0004](0004-commit-level-analysis-unit.md) | Observe each commit and package | superseded by 0013 | 2026-09-15 | Repository Mining: units and measures; Longitudinal: repeated observations |
| [0005](0005-taxonomy-rebuilt-with-two-checkpoints.md) | Taxonomy with two checkpoints | proposed | 2026-09-14 | Mixed Methods: integration; Sampling: discovery; General: construct definitions |
| [0006](0006-api-labeling-pipeline.md) | API labeling with a fixed model | proposed | 2026-09-15 | General: collection and analysis details; Repository Mining: annotation procedure |
| [0007](0007-security-two-stage-detection.md) | Detect security changes in two stages | proposed | 2026-09-14 | Repository Mining: validated measures; General: construct validity |
| [0008](0008-validation-by-audited-sample.md) | Validation using an audited sample | proposed | 2026-09-14 | Sampling: rationale for sample size; Agreement between raters: independent ratings |
| [0009](0009-skill-length-metrics.md) | Skill length metrics | proposed | 2026-09-15 | Repository Mining: measures; Longitudinal: operationalization |
| [0010](0010-timeline-reference-lines.md) | Timeline reference lines | proposed | 2026-09-15 | General: supported interpretation; Visualization: clear annotations |
| [0011](0011-target-population-of-fork-modifications.md) | Target population of fork modifications | proposed | 2026-09-16 | Sampling: target population; Repository Mining: external validity |
| [0012](0012-monthly-active-owner-skill-prevalence.md) | Monthly prevalence among active pairs of owners and skills | superseded by 0013 | 2026-09-16 | Repository Mining: units and measures; Longitudinal: repeated observations |
| [0013](0013-monthly-net-change-as-labeling-unit.md) | Monthly net change as the labeling unit | proposed | 2026-09-16 | Repository Mining: units and metrics; Longitudinal: operationalization |
| [0014](0014-fork-default-branch-only.md) | Observe only each fork's default branch | proposed | 2026-09-16 | Repository Mining: preprocessing and external validity; Longitudinal: identity |
| [0015](0015-github-committer-time-in-utc.md) | GitHub commit timestamps and UTC calendar months | proposed | 2026-09-16 | General: collection details; Repository Mining: measures |
| [0016](0016-observation-window-including-september.md) | Observation window including September 2026 | proposed | 2026-09-16 | General: collection period; Longitudinal: observation coverage |
| [0017](0017-skill-centricity-over-tracked-files.md) | Package file ratio over all tracked files | proposed | 2026-09-16 | Repository Mining: measures and preprocessing |
| [0018](0018-exclude-unresolved-upstream-changes.md) | Exclude changes whose upstream origin cannot be resolved | proposed | 2026-09-16 | Repository Mining: preprocessing; General: limitations |
| [0019](0019-repository-and-fork-acquisition.md) | Repository and fork acquisition | accepted | 2026-09-16 | Repository Mining: data collection; General: reproducibility and pilot validation |
| [0020](0020-monthly-extraction-and-origin-evidence.md) | Monthly extraction and origin evidence | proposed | 2026-09-16 | Repository Mining: preprocessing and measures; Longitudinal: temporal ordering |
| [0021](0021-pydriller-compatibility-pilot.md) | PyDriller compatibility pilot | proposed | 2026-09-16 | Repository Mining: acquisition; General: reproducibility; Sampling: engineering cases |
| [0022](0022-exclude-repackaged-skill-collections.md) | Exclude collections of skills from other repositories | proposed | 2026-09-16 | Repository Mining: selection and attribution; Sampling: filtering |
| [0023](0023-use-pydriller-for-monthly-history.md) | Use PyDriller for monthly history acquisition | proposed | 2026-09-17 | Repository Mining: acquisition and preprocessing; General: reproducibility |
| [0024](0024-fixed-project-paths.md) | Fixed project paths | accepted | 2026-09-22 | Implementation convention |
| [0025](0025-confirmed-study-repositories.md) | Confirmed study repositories | accepted | 2026-09-22 | Sampling: explicit membership |
| [0026](0026-exclude-archify.md) | Exclude archify | accepted | 2026-09-22 | Sampling: purpose boundary |
| [0027](0027-acquire-confirmed-repositories.md) | Acquire the confirmed repositories | accepted | 2026-09-22 | Repository Mining: acquisition and reproducibility |
| [0028](0028-exclude-unrelated-fork-histories.md) | Exclude fork histories without a common ancestor | accepted | 2026-09-22 | Repository Mining: exclusions and acquisition accounting |
| [0029](0029-repair-fork-enumeration.md) | Repair fork enumeration | superseded by 0030 | 2026-09-22 | Repository Mining: coverage and evidence recovery |
| [0030](0030-reconcile-missing-fork-identities.md) | Reconcile missing fork identities | superseded by 0031 | 2026-09-22 | Repository Mining: missingness and partial progress |
| [0031](0031-skip-unavailable-forks.md) | Skip unavailable forks | accepted | 2026-09-23 | Repository Mining: missingness and available corpus |
| [0032](0032-reuse-comparisons-with-minimal-evidence.md) | Reuse comparisons with minimal evidence | accepted | 2026-09-23 | Acquisition efficiency and reproducibility |
| [0033](0033-prioritize-legacy-rebuttal.md) | Prioritize the legacy rebuttal | accepted | 2026-09-23 | Repository Mining: units and preprocessing; General: supported claims |
| [0034](0034-legacy-rebuttal-validation.md) | Validate the legacy rebuttal evidence | proposed | 2026-09-23 | Repository Mining: validated measures; Sampling; Inter-Rater Reliability; Open Science |
| [0035](0035-two-day-local-rebuttal-analysis.md) | Execute the two day rebuttal analysis | accepted | 2026-09-23 | Repository Mining: units and validation; Sampling: conditional uncertainty; Open Science |
| [0036](0036-blind-audit-293-candidates.md) | Independently annotate 293 legacy candidates | accepted | 2026-09-23 | Sampling: explicit frame and precision; Inter-Rater Reliability: independent ratings |

## Implementation order

The two day local analysis under ADR 0035 is complete: per-repository and exclusion tables, aggregation subsets, conditional fork intervals, historical script availability, PR metadata, agreement checks and upstream security file context. Results are in `legacy/data/rebuttal/local-final-20260923/` and `legacy/data/rebuttal/full-20260923/prs/`, with interpretation in `Rebuttal.md`. Under ADR 0036, two raters will independently complete the same 293 random candidates; blank forms are in `legacy/data/rebuttal/human-293-20260923/human/`. Human outcomes and model reruns are not complete. Four behavioral tests passed. The working bibliography is pre-existing and empty; an isolated copy builds successfully using a recovered Git HEAD bibliography, pending confirmation of that source.

First address the submitted study through `legacy/` as recorded in ADR 0033; use ADR 0034 for pending validation decisions and code mappings. The remainder of this section describes the separate monthly study, not the rebuttal execution order.

ADRs [0025](0025-confirmed-study-repositories.md) and [0026](0026-exclude-archify.md), accepted on 2026-09-22, record the user's approval of 30 main study repositories and exclusion of archify. Confirmed decisions are in the purpose review YAML and CSV and in `screening.reviews`; the original acquisition snapshot remains unchanged. [ADR 0027](0027-acquire-confirmed-repositories.md) implements acquisition from this cohort with `confirmed_reviews` selection and `--source_run`, preserving ratios as descriptive evidence. Pilot limits apply to forks per upstream and comparison commits while all approved repositories are included.

ADR [0024](0024-fixed-project-paths.md), accepted on 2026-09-22, moves conventional paths from YAML into the evaluation entry points. Existing artifact locations remain unchanged; historical settings retain compatibility through `src/config.py`. This is an implementation convention and does not alter research measures or sampling.

Follow domain modeling, event flow, behavioral tests and implementation in that order for each resolved module. Repository discovery, complete tree screening, fork enumeration and comparisons of frozen revisions are implemented. Monthly extraction includes complete histories, package endpoints, net diffs and conservative origin evidence under ADR 0020. Origin rules still require human validation; annotation is not implemented.

| Stage | Input and output | Code location |
| --- | --- | --- |
| Retrieve | Intent and manifest queries produce raw responses, candidates, frozen branches and fork comparisons | `src/github.py`, `src/retrieve.py`, `src/acquisition.py` |
| Screen | Complete trees produce descriptive ratios; confirmed reviews select the main cohort, with calibrated selection retained for historical runs | `src/preprocess.py`, `src/retrieve.py`, `src/acquisition.py` |
| Extract | PyDriller histories and complete Git objects produce monthly endpoints, source evidence, net diffs and exclusion records | `src/git_objects.py`, `src/extract.py` |
| Discover | A recorded sample produces candidate patterns and a frozen taxonomy | Planned `src/taxonomy.py` |
| Label | Monthly diffs produce raw API results and validated labels | Planned `src/label.py` |
| Measure | Complete package endpoints produce length measurements and security evidence | Planned `src/measure.py` |
| Acquire and verify | Separate collection stages and artifact validation | `eval/skill-pattern-mine/main.py` |
| Compare history readers | Frozen API observations and constructed Git histories test optional PyDriller compatibility | `src/pydriller_pilot.py`, `eval/pydriller-pilot/main.py` |
| Audit and analyze | Independent ratings and retained observations produce quality estimates, tables and figures | Not implemented |

`configs/skill-pattern-mine.yaml` contains confirmed settings and the operational extraction rules in ADR 0020. The acquisition cutoff is frozen at run creation; the calibrated threshold remains unset. The entry point exposes `--step repositories`, `forks`, `verify`, `all` and `extract`, with `--num_samples` for bounded collection and `--pilot` for engineering validation. Extraction samples output candidates while collecting their complete ancestry. Raw responses and derived records live under `data/skill-pattern-mine/runs/{run_id}/`. Model outputs will live under `results/{model_name}/` within the data directory, and final figures/tables under `eval/tables-and-figures/`.

## Remaining design work

- **Corpus and endpoints, ADRs 0002, 0003, 0013 to 0020 and 0027:** the main cohort uses confirmed membership; ratio calibration remains unperformed and must not be claimed. Validate the implemented origin rules. ADR 0028 excludes frozen pairs explicitly reported by GitHub as having no common ancestor, preserving the raw evidence. ADR 0031 permits recorded HTTP 404 skips for individual forks; other failures remain errors. Package moves remain omitted pending identity review; histories crossing month boundaries backwards fail extraction. Merge attribution is deliberately conservative. Bot and translation handling remain unresolved. An unmatched patch is not proof of independent authorship.
- **Taxonomy and annotation, ADRs 0005 and 0006:** fix discovery batch sizes and stopping rules, preserve candidate evidence, isolate independent validation, verify the API model, and define failure handling.
- **Measurements and audit, ADRs 0007 to 0009:** specify file types and structural units, independent security findings, precise denominators, adjudication, rare category support and undefined statistics.
- **Analysis, ADRs 0001 and 0016:** account for repeated observations and overlapping labels, define effect summaries and uncertainty, and handle sparse or partial months. Ordinary contingency testing is not yet an approved solution.
- **Execution and replication:** acquisition bounds and replay follow ADR 0019; annotation costs, human audit costs and artifact release scope remain to be fixed. Do not publish personal or sensitive source content merely because it appears in a public repository.

## Validation

The current full collector is `confirmed-forks-full-optimized-20260923`, launched after stopping the previous recovery process. It preserves the original cutoff and recovers the existing caches and creation ordered listings. Inspect its live progress and eventual acceptance. The 2026-09-23 optimization pilot passed with 59 comparisons, one HTTP 404 skip, 16 reused comparisons and zero errors across all 30 upstreams. All 119 behavioral tests passed; isolated offline replay reproduced the seven acquisition artifacts without network requests, and successful comparison contents match the source pilot.

ADRs 0031 and 0032 are implemented in the acquisition models, reader, collector and verifier. Fork HTTP 404 skips no longer block acceptance, but remain explicit missing observations. Comparison reuse requires a complete source result and matching upstream and SHAs. Ordinary monthly extraction now requires finished, accepted acquisition; `--allow_partial` is limited to bounded pilot runs and reports its partial scope. Source snapshots remain, while duplicate checksum inventories are removed.

Under ADR 0028, `confirmed-forks-validation-20260922` reproduced the same frozen pilot selection with 59 comparisons and one evidenced exclusion, no acquisition errors, and passing acceptance. All 90 behavioral tests passed. Offline replay exactly reproduced comparisons, exclusions, coverage, and errors without network calls. The original failed pilot remains unchanged. Full acquisition was launched separately as `confirmed-forks-full-20260922`, with no sample limit; inspect `progress.json`, `collector.log`, and the eventual `acceptance.json` rather than inferring completion from launch.

The first full run was paused after unstable star ordering returned 26,093 rows but only 14,781 distinct fork IDs for `obra/superpowers`. ADR 0029 implements creation ordering, inventory checks before comparisons, identity recovery for metadata 404 responses, and checkpoints every 250 forks. A new recovery run preserves the original cutoff and imports individually hashed cached responses without reusing the failed listings. Other unresolved API failures remain acquisition errors.

ADR 0030 refines partial progress handling after the complete creation order diagnostic returned 26,100 unique IDs, including 11,321 absent from the old listing, with two previously known IDs unavailable by numeric lookup. Missing identities are reconciled when possible; unresolved cases retain errors and incomplete coverage while available forks continue processing. The ordering pilot and its recovery produced 59 identical successful comparisons and one identical metadata error, with 209 and 32 requests respectively. Their acquisition acceptance remains failed. All 105 behavioral tests passed.

The 2026-09-22 full recovery is `confirmed-forks-full-recovery-20260922`, preserving the original cutoff, 24,617 reusable responses, and all 30 confirmed upstreams. The original collector is stopped. The recovery records unresolved missing IDs and continues acquisition; it has not passed complete acceptance. A descriptive performance audit found 520 distinct commit pairs among 8,166 successful fork comparison requests in the original run. ADR 0032 now implements reuse of complete comparisons for the same upstream and SHA pair while preserving individual fork attribution and the source comparison.

The 2026-09-22 run `confirmed-forks-pilot-20260922` imported all 30 approved upstreams and froze two forks per upstream. It produced 59 successful comparisons and one failure: GitHub reported no common ancestor for `noah-1106/openmontage-zh-mcp`. Acceptance remains failed because this error is unresolved. All 86 behavioral tests passed; isolated offline replay reproduced the successful artifacts with zero network requests and preserved the original error evidence. See the run's `pilot_validation.json` and `comparison_diagnostics.json`. This pilot does not establish complete histories, monthly attribution, or representative sampling.

Run behavioral checks with `uv run python -m unittest discover -s tests -v`. Checks cover acquisition and monthly extraction, including cancellation, unchanged endpoint files, patch overlap, mixed origin, mode changes, binary content, missing or corrupt data and stable observation identities. These fixtures do not replace human validation of origin attribution or statistical procedures.

Before a main study, validate origin attribution on independent human ratings, resolve omitted identities and filtering policies, and establish annotation effort. A bounded engineering pilot does not establish a final corpus, annotation quality or the accuracy of the origin heuristic.
