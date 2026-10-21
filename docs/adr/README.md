# Architecture decision records

Design decisions, their implementation mapping and the remaining design questions live in this directory. Statuses mirror the source ADRs. The Standards column names the relevant ACM SIGSOFT requirements; it does not claim that all of them are satisfied. The study observes monthly net changes of skill packages on frozen fork default branches, assigns months by UTC committer time, and uses an observation window that includes September 2026. Routine implementation decisions are delegated to the engineer; changes to research scope, attribution or interpretation require discussion.

| ID | Title | Status | Date | Standards |
| --- | --- | --- | --- | --- |
| [0001](0001-temporal-redesign-of-main-study.md) | Temporal redesign of the main study | proposed | 2026-09-14 | General: questions, analysis; Longitudinal: temporal design |
| [0002](0002-systematic-repository-retrieval.md) | Systematic repository retrieval | proposed | 2026-09-15 | Repository Mining: selection and validation; Sampling: frame and filtering |
| [0003](0003-three-level-deduplication.md) | Deduplication at three levels | proposed | 2026-09-15 | Repository Mining: preprocessing; Longitudinal: subject identity |
| [0004](0004-commit-level-analysis-unit.md) | Observe each commit and package | superseded by 0013 | 2026-09-15 | Repository Mining: units and measures |
| [0005](0005-taxonomy-rebuilt-with-two-checkpoints.md) | Taxonomy with two checkpoints | proposed | 2026-09-14 | Mixed Methods: integration; Sampling: discovery; General: construct definitions |
| [0006](0006-api-labeling-pipeline.md) | API labeling with a fixed model | proposed | 2026-09-15 | General: collection and analysis details; Repository Mining: annotation procedure |
| [0007](0007-security-two-stage-detection.md) | Detect security changes in two stages | proposed | 2026-09-14 | Repository Mining: validated measures; General: construct validity |
| [0008](0008-validation-by-audited-sample.md) | Validation using an audited sample | proposed | 2026-09-14 | Sampling: rationale for sample size; Inter-Rater Reliability: independent ratings |
| [0009](0009-skill-length-metrics.md) | Skill length metrics | proposed | 2026-09-15 | Repository Mining: measures; Longitudinal: operationalization |
| [0010](0010-timeline-reference-lines.md) | Timeline reference lines | proposed | 2026-09-15 | General: supported interpretation; Visualization: clear annotations |
| [0011](0011-target-population-of-fork-modifications.md) | Target population of fork modifications | proposed | 2026-09-16 | Sampling: target population; Repository Mining: external validity |
| [0012](0012-monthly-active-owner-skill-prevalence.md) | Monthly prevalence among active pairs of owners and skills | superseded by 0013 | 2026-09-16 | Repository Mining: units and measures |
| [0013](0013-monthly-net-change-as-labeling-unit.md) | Monthly net change as the labeling unit | accepted | 2026-09-16 | Repository Mining: units and metrics; Longitudinal: operationalization |
| [0014](0014-fork-default-branch-only.md) | Observe only each fork's default branch | accepted | 2026-09-16 | Repository Mining: preprocessing and external validity; Longitudinal: identity |
| [0015](0015-github-committer-time-in-utc.md) | GitHub commit timestamps and UTC calendar months | accepted | 2026-09-16 | General: collection details; Repository Mining: measures |
| [0016](0016-observation-window-including-september.md) | Observation window including September 2026 | accepted | 2026-09-16 | General: collection period; Longitudinal: observation coverage |
| [0017](0017-skill-centricity-over-tracked-files.md) | Package file ratio over all tracked files | accepted | 2026-09-16 | Repository Mining: measures and preprocessing |
| [0018](0018-exclude-unresolved-upstream-changes.md) | Exclude changes whose upstream origin cannot be resolved | accepted | 2026-09-16 | Repository Mining: preprocessing; General: limitations |
| [0019](0019-repository-and-fork-acquisition.md) | Repository and fork acquisition | accepted | 2026-09-16 | Repository Mining: data collection; General: reproducibility and pilot validation |
| [0020](0020-monthly-extraction-and-origin-evidence.md) | Monthly extraction and origin evidence | accepted | 2026-09-16 | Repository Mining: preprocessing and measures; Longitudinal: temporal ordering |
| [0021](0021-pydriller-compatibility-pilot.md) | PyDriller compatibility pilot | superseded by 0023 | 2026-09-16 | Repository Mining: acquisition; General: reproducibility |
| [0022](0022-exclude-repackaged-skill-collections.md) | Exclude collections of skills from other repositories | accepted | 2026-09-16 | Repository Mining: selection and attribution; Sampling: filtering |
| [0023](0023-use-pydriller-for-monthly-history.md) | Use PyDriller for monthly history acquisition | accepted | 2026-09-17 | Repository Mining: acquisition and preprocessing; General: reproducibility |
| [0024](0024-fixed-project-paths.md) | Fixed project paths | accepted | 2026-09-22 | Implementation convention |
| [0025](0025-confirmed-study-repositories.md) | Confirmed study repositories | accepted | 2026-09-22 | Sampling: explicit membership |
| [0026](0026-exclude-archify.md) | Exclude archify | accepted | 2026-09-22 | Sampling: purpose boundary |
| [0027](0027-acquire-confirmed-repositories.md) | Acquire the confirmed repositories | accepted | 2026-09-22 | Repository Mining: acquisition and reproducibility |
| [0028](0028-exclude-unrelated-fork-histories.md) | Exclude fork histories without a common ancestor | accepted | 2026-09-22 | Repository Mining: exclusions and acquisition accounting |
| [0029](0029-repair-fork-enumeration.md) | Repair fork enumeration | superseded by 0030 | 2026-09-22 | Repository Mining: coverage and evidence recovery |
| [0030](0030-reconcile-missing-fork-identities.md) | Reconcile missing fork identities | superseded by 0031 | 2026-09-22 | Repository Mining: missingness and partial progress |
| [0031](0031-skip-unavailable-forks.md) | Skip unavailable forks | accepted | 2026-09-23 | Repository Mining: missingness and available corpus |
| [0032](0032-reuse-comparisons-with-minimal-evidence.md) | Reuse comparisons with minimal evidence | accepted | 2026-09-23 | Acquisition efficiency and reproducibility |
| [0042](0042-select-cohort-by-confirmed-reviews-only.md) | Select the cohort by confirmed reviews only | accepted | 2026-10-21 | Sampling: explicit membership; Repository Mining: selection |

ADRs 0033 to 0041 recorded the rebuttal of the earlier submitted study. That work is complete and its materials were removed from the repository on 2026-10-21; the numbers are not reused.

## Implementation mapping

Each stage is implemented in the order domain models, data flow, behavioral tests, code. The acquisition and extraction stages are implemented; discovery, labeling, measurement and analysis are still design work.

| Stage | Input and output | Code location |
| --- | --- | --- |
| Retrieve | Intent and manifest queries produce raw responses, candidates and frozen upstream branches; with `--source_run`, the approved cohort is imported from a candidate run | `src/github.py`, `src/repositories.py`, `src/preprocess.py`, `src/review.py` |
| Forks | Frozen upstream SHAs produce enumerated forks, frozen fork branches, comparisons, exclusions and skips | `src/forks.py` |
| Verify | Saved acquisition artifacts produce an acceptance report without network access | `src/verify.py` |
| Extract | PyDriller histories and complete Git objects produce monthly endpoints, origin evidence, net diffs and omission records | `src/git_history.py`, `src/extract.py` |
| Run records and storage | Frozen run settings, JSON and JSONL artifacts | `src/run.py`, `src/storage.py` |
| Entry point | `--step repositories`, `forks`, `verify`, `all`, `review` and `extract` with `--num_samples` and `--pilot` | `eval/skill-pattern-mine/main.py` |
| Discover | A recorded sample produces candidate patterns and a frozen taxonomy | Planned |
| Label | Monthly diffs produce raw API results and validated labels | Planned |
| Measure | Complete package endpoints produce length measurements and security evidence | Planned |
| Audit and analyze | Independent ratings and retained observations produce quality estimates, tables and figures | Planned |

Run artifacts live under `data/skill-pattern-mine/runs/{run_id}/`. Each run freezes its configuration, cutoff, pilot mode and sample bounds in `run.json`, and copies the source files it ran with into `source/`. The domain models for the planned stages are already defined in `src/domain.py` following ADRs 0005 to 0010; they are revised when those stages are implemented.

Implementation notes that qualify accepted ADRs: the GitHub API history reader kept by the original ADR 0023 was removed on 2026-10-21, so `history_backend` no longer exists in configuration. The historical `outputs` compatibility shim from ADR 0024 was removed at the same time because no run snapshots with that field remain. The recovery import from ADRs 0029 and 0030 was removed with them; creation ordered enumeration, inventory checks and numeric identity fallback from ADR 0029 remain in `src/forks.py`.

## Remaining design work

- **Corpus and endpoints, ADRs 0002, 0003, 0013 to 0020, 0027 and 0042:** the main cohort is defined by confirmed reviews; the package file ratio is descriptive and no calibrated selection is claimed. Validate the implemented origin rules on independent human ratings. Package moves remain omitted pending identity review; histories crossing month boundaries backwards fail extraction. Merge attribution is deliberately conservative. Bot and translation handling remain unresolved. An unmatched patch is not proof of independent authorship.
- **Taxonomy and annotation, ADRs 0005 and 0006:** fix discovery batch sizes and stopping rules, preserve candidate evidence, isolate independent validation, verify the API model, and define failure handling.
- **Measurements and audit, ADRs 0007 to 0009:** specify file types and structural units, independent security findings, precise denominators, adjudication, rare category support and undefined statistics.
- **Analysis, ADRs 0001 and 0016:** account for repeated observations and overlapping labels, define effect summaries and uncertainty, and handle sparse or partial months. Ordinary contingency testing is not yet an approved solution.
- **Execution and replication:** acquisition bounds and replay follow ADR 0019; annotation costs, human audit costs and artifact release scope remain to be fixed. Do not publish personal or sensitive source content merely because it appears in a public repository.

## Validation

Run the behavioral checks from the project root with `uv run --locked python -m unittest discover -s tests -v`. They cover acquisition, verification and monthly extraction, including cancellation, unchanged endpoint files, patch overlap, mixed origin, mode changes, binary content, missing or corrupt data and stable observation identities. These fixtures do not replace human validation of origin attribution or statistical procedures. A bounded engineering pilot does not establish a final corpus, annotation quality or the accuracy of the origin heuristic.
