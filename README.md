# Skill Pattern Mine

> An empirical study of how developers fork and modify agent skills on GitHub.

## Rebuttal TODO: September 25

The current priority is the rebuttal for paper #1322, due **September 25, 2026**. The exact cutoff time, timezone and response length still need confirmation. Work is on the `rebuttal` branch and builds on `legacy/`. See [Rebuttal.md](Rebuttal.md) for results and the response draft, and [coauthor annotation instructions](legacy/annotation/README.md) for the ready-to-use forms.

Both forms now use version `human-unseen-v2-20260923`. Update your checkout before starting. The old forms are superseded; preserve existing exports separately and never merge old and new task IDs. Of the 1,126 analyzed instances, 488 have known prior exposure and 638 remain eligible. The same exclusion rule reduces security validation from 209 to 109 positives. Original descriptive statistics retain their original denominators.

### Coauthors: start here

Clone the `rebuttal` branch and open [blind.html](legacy/annotation/blind.html) and [security.html](legacy/annotation/security.html) locally in a browser. Use rater IDs `A` and `B`; each person completes the same tasks independently. Do not read model predictions or old audit results before finishing. Export ratings regularly and return them privately to the corresponding author; repository write access is not required.

- [ ] **Both raters:** independently complete the same **293 blind tasks**, drawn from 638 eligible final instances after excluding known prior audit and taxonomy exposure. The 94 zero-label exclusions are outside this frame.
- [ ] **Both raters:** independently audit **109 eligible security-positive instances / 642 matched lines**, recording textual meaning and change direction.
- [ ] **Both raters:** return `blind-A.json`, `blind-B.json`, `security-A.json`, and `security-B.json`, with expertise, prior exposure and incomplete-task notes.
- [ ] **Authors:** preserve independent exports, adjudicate disagreements before viewing model predictions, then compute agreement, per-label precision/recall and security outcomes.
- [ ] **Corresponding author:** confirm the deadline time/timezone, word limit and rules on new results or external links.
- [ ] **Authors:** provide an authenticated model runtime and fix the rerun configuration/budget, or explicitly report that rerun stability is unavailable.
- [ ] **Authors:** confirm the recovered bibliography source, check page limits, and finalize the response with observed human results or candid limitations.
- [ ] **Corresponding author:** submit before the confirmed September 25 cutoff and retain submission confirmation.

### Completed

- [x] Per-repository and all six repository-exclusion analyses for RQ1-RQ3.
- [x] Aggregation subsets, conditional fork-cluster intervals and label-provenance sensitivity.
- [x] Historical script availability, conditional script modification and PR evidence.
- [x] Agreement recalculation and upstream security-file context checks.
- [x] Blank, credential-redacted annotation forms with independent JSON export.
- [x] Unsupported manuscript claims revised locally; numerical evidence recorded in [Rebuttal.md](Rebuttal.md).

Aim to complete independent annotation and adjudication on September 24, leaving September 25 for result checks, response compression and submission. Annotation is substantial work: time early tasks and report constraints without dropping difficult records selectively. Human validity, strict held-out status, full atomic relabeling, detector recall and exact historical model reproduction are **not** established by the completed automatic checks.

This branch includes the main project, the legacy implementation, previously released artifacts, selected aggregate results and the standalone annotation forms. Raw mining caches, coordinator mappings, private ratings and the separate Overleaf checkout remain local. Some detailed evidence links in `Rebuttal.md` therefore require the full local workspace; the coauthor forms need no additional data.

## Overview

The current priority is responding to reviews #1322A-C using the submitted study and implementation under `legacy/`. See [Rebuttal.md](Rebuttal.md) for verified evidence, pending validation and the response draft, and [ADR 0033](docs/adr/0033-prioritize-legacy-rebuttal.md) for scope.

This project studies modification patterns, package length and security changes in public forks of agent skills. Current design decisions and remaining questions are in [docs/adr/](docs/adr/README.md). The earlier implementation and datasets are in [legacy/](legacy/README.md), and the manuscript is in [paper/](paper/main.tex).

The project root uses [Si1w/research-template](https://github.com/Si1w/research-template) at revision `40c6ef53887307693f81c714c00f7011f1e87512`.

## Architecture

```text
skill-pattern-mine/
├── .agents/          # Agent instructions and project specifications
├── AGENTS.md         # Project instructions for coding agents
├── configs/          # Experiment settings
├── docs/adr/         # Design decisions and implementation mapping
├── legacy/           # Existing implementation, configs, datasets, and analysis
├── paper/            # Existing manuscript with its own Git repository
├── eval/             # Acquisition entry point and future analysis scripts
├── src/              # Domain models, GitHub acquisition and screening
├── tests/            # Behavioral checks
└── pyproject.toml    # Root project metadata and dependency configuration
```

The root implements repository discovery, complete tree screening, fork enumeration and monthly package extraction from frozen default branches. Monthly outputs contain complete endpoint contents, net diffs and conservative origin evidence. Annotation remains separate work. Collection and extraction rules are recorded in [ADR 0019](docs/adr/0019-repository-and-fork-acquisition.md) and [ADR 0020](docs/adr/0020-monthly-extraction-and-origin-evidence.md). The earlier pipeline retains its own environment and dependencies under `legacy/`.

## Quick Start

### Prerequisites

- Python 3.12.
- [uv](https://docs.astral.sh/uv/) for dependency and environment management.
- An authenticated [GitHub CLI](https://cli.github.com/) for live API reads; offline replay does not require authentication.

### Installation

Set up the root environment:

```bash
uv sync --locked
```

### Usage

Run a bounded acquisition pilot across all 30 confirmed repositories using their frozen candidate snapshots:

```bash
uv run --locked python eval/skill-pattern-mine/main.py --step all --source_run repository-candidates-20260916 --pilot --num_samples 2 --run_id my-pilot
```

Run individual stages with `--step repositories`, `--step forks` or `--step verify`. Reuse the run ID to resume with saved responses and frozen settings. Replay an existing run without network access:

```bash
uv run --locked python eval/skill-pattern-mine/main.py --step all --offline --run_id my-pilot
```

Artifacts are written to `data/skill-pattern-mine/runs/{run_id}/`. The entry point derives this fixed location and its default config path from the project root; YAML contains experiment parameters rather than output directories. Historical snapshots with the retired `outputs` field remain readable without modifying their files. Inspect `acceptance.json`, `repository_summary.json`, `fork_summary.json`, and the error records before using outputs. Pilot success verifies the bounded acquisition; coverage flags still identify sampled or incomplete histories. The current `confirmed_reviews` mode selects only explicitly approved repositories and keeps package ratios descriptive. `--num_samples 2` bounds forks per upstream and comparison commits, while all 30 approved upstreams are included. The original `calibrated_ratio` mode remains available for historical configurations. Source selection identities and an exact implementation snapshot are saved with each new run. Redundant checksum inventories are omitted; cache identity, Git content and observation identity checks remain. The source search coverage remains incomplete; selecting the confirmed cohort does not resolve that limitation.

Start a full acquisition with a new run ID and no sample limit:

```bash
uv run --locked python eval/skill-pattern-mine/main.py --step all --source_run repository-candidates-20260916 --run_id my-full-run
```

Full runs wait for GitHub quota renewal. `progress.json` reports the active upstream and counts. Outputs are checkpointed every 250 forks and after each upstream. Responses already cached for the current upstream are reused on resume. Repeat the command with the same run ID and unchanged configuration after an interruption; do not launch two collectors for the same run. Background launches record their process ID in `launcher.json` and write logs to `collector.log`.

New runs enumerate forks by creation time ascending. Before comparisons, the collector rejects duplicate IDs and creation time inversions. During full recovery, missing known IDs are checked by numeric identity and upstream membership. IDs that remain unavailable with HTTP 404 are recorded in `fork_skips.jsonl` and do not block acceptance of the available corpus. Other unresolved failures remain errors. Reaching the final page alone does not establish a consistent inventory. See [ADR 0031](docs/adr/0031-skip-unavailable-forks.md). Recover the interrupted star ordering run into a separate run:

```bash
uv run --locked python eval/skill-pattern-mine/main.py --step all --recover_run confirmed-forks-full-20260922 --run_id confirmed-forks-full-recovery-20260922
```

Recovery preserves the original observation cutoff, candidate source, pilot mode and sample bounds. It imports attributable metadata, branch and comparison responses, including their timestamps and cached 404 failures. Listings are reused when both runs use creation ordering; changing the order requires new listings. Inventory validation remains mandatory. `cache_import.json` records import counts and `recovery_inventory.json` records known fork identities, including previously missing IDs. The old run remains evidence of the failure. A historical run with a different configuration must use its saved YAML via `--config data/skill-pattern-mine/runs/RUN/source/configs/skill-pattern-mine.yaml`.

Successful complete comparisons are reused for identical base and head SHAs within the same upstream. Every fork retains its own metadata and a `reused_from` reference; incomplete comparisons, errors and exclusions are never shared. `fork_summary.json` reports `reused_comparisons`. See [ADR 0032](docs/adr/0032-reuse-comparisons-with-minimal-evidence.md).

Explicit API evidence of no common ancestor between the requested frozen SHAs is saved in `fork_exclusions.jsonl` and its raw response cache. Such pairs are excluded from monthly extraction and counted separately from errors. Other fork 404 responses are recorded separately in `fork_skips.jsonl` and omitted from extraction. Metadata lookup still tries the numeric identity after a name lookup returns 404. Upstream listing failures and all non-404 errors still block acceptance. See [ADR 0031](docs/adr/0031-skip-unavailable-forks.md).

Prepare the confirmed repository snapshots without collecting forks, then export a review worksheet:

```bash
uv run --locked python eval/skill-pattern-mine/main.py --step repositories --source_run repository-candidates-20260916 --run_id candidates
uv run --locked python eval/skill-pattern-mine/main.py --step review --run_id candidates
```

The run directory contains `repository_candidates.csv` for candidates at or above the lowest fork threshold, including structural exclusions, and `repository_review.yaml` for repositories with measured skill packages. Review fields remain null until assessed. Copy completed `review` objects into `screening.reviews` in the experiment config; the worksheet itself is not an executable experiment config. Search coverage accompanies the worksheet, and existing review exports are never overwritten.

Extract monthly package changes after acquisition finishes and passes validation. `--step all` runs acquisition and verification only; extraction is a separate command:

```bash
uv run --locked python eval/skill-pattern-mine/main.py --step extract --run_id my-pilot --month 2026-03
```

Formal extraction refuses running or failed acquisition before freezing its inputs. A bounded pilot may explicitly use `--allow_partial`; its report records `input_scope: partial_pilot`. Keep partial experiments in separate pilot runs or use the review input example below with a new run ID. Partial inputs remain frozen and cannot later be expanded in that run. Skipped, excluded and unsuccessful forks never enter direct extraction.

Omit `--month` to process all observed months. Extraction collects complete reachable histories even in a pilot; `--num_samples` bounds forks and monthly candidates per fork. The resulting `monthly_records.jsonl` includes retained candidates and records marked `unresolved_upstream`, which must be excluded from main analysis. `monthly_omissions.jsonl` records unsupported identities and pure synchronization; failures appear in `monthly_errors.jsonl`. Inspect `monthly_acceptance.json` for engineering checks and coverage. Actual attribution accuracy still requires human validation.

To use a saved acquisition review example as pilot input:

```bash
uv run --locked python eval/skill-pattern-mine/main.py --step extract --input data/skill-pattern-mine/review-example.json --pilot --num_samples 2 --month 2026-03 --run_id monthly-review
```

The review input supplies frozen references and its original cutoff. It must contain the repository, comparison and run objects from acquisition. New runs use PyDriller for complete commit histories and GitPython for complete file states, preserving the existing monthly and origin rules. GitHub API acquisition still supplies repository, fork and account metadata. Local histories leave unavailable GitHub author logins null. The reader is selected by `extraction.history_backend`; `github_api` remains available for comparison and historical configurations. Migration requires a new run ID with the new configuration.

Local Git evidence is saved under the run's `git_evidence/`, separately from API responses. Temporary bare Git repositories are removed on success and failure. Once evidence has been saved, repeat the same command with `--offline` for replay without Git downloads. Missing offline evidence is an error. Keep this evidence directory to reproduce extraction after cleanup. Reader versions and Git fetch counts are recorded in `monthly_acceptance.json`. No LLM calls are made during extraction. See [ADR 0023](docs/adr/0023-use-pydriller-for-monthly-history.md).

Run the current behavioral checks from the project root:

```bash
uv run --locked python -m unittest discover -s tests -v
```

Run the PyDriller compatibility experiment on the saved monthly review input:

```bash
uv run --locked python eval/pydriller-pilot/main.py --step all --num_samples 2
```

Settings are in `configs/pydriller-pilot.yaml`. The experiment compares frozen histories and monthly records, probes direct modifications on merge commits, and checks deterministic edge cases. Use `--step fixtures` for local cases or `--step real` for the saved observations. The entry point defaults to `data/skill-pattern-mine/monthly-review-example.json` as input and `data/skill-pattern-mine/pydriller-pilot.json` as output. Select different files with `--input` and `--output`; explicit relative paths are resolved from the working directory. An existing result is never overwritten, so use a new `--output` path for another run. Temporary Git repositories and API caches are automatically removed. This is an engineering comparison under [ADR 0021](docs/adr/0021-pydriller-compatibility-pilot.md); it uses the same object reader as production extraction. Path conventions are recorded in [ADR 0024](docs/adr/0024-fixed-project-paths.md).

Follow [legacy/README.md](legacy/README.md) for earlier pipeline commands, datasets and agent workflows. Run those commands from `legacy/`.

Project conventions are in [AGENTS.md](AGENTS.md); use [docs/adr/template.md](docs/adr/template.md) when recording an architecture decision.

## Results

The active collector is `confirmed-forks-full-optimized-20260923`, replacing the previous recovery process on 2026-09-23. It imports the previous run's cached evidence and creation ordered listings while preserving the original cutoff of `2026-09-22T14:48:04.707823+00:00`. Its `progress.json` includes skipped forks and reused comparisons. The old run remains preserved with a `superseded.json` marker. This full run is ongoing; launch and cache replay do not imply final acceptance.

The optimization pilot `confirmed-forks-optimized-pilot-20260923` passed acquisition validation across all 30 approved upstreams: 59 successful comparisons, one recorded HTTP 404 skip, 16 reused comparisons and no acquisition errors. Recovery needed two network requests. Its successful records are unchanged from the source pilot, and isolated offline replay reproduced all seven checked acquisition artifacts with zero network requests. All 119 behavioral tests passed. See `pilot_validation.json` in that run. These are bounded engineering checks, not evidence of complete full collection.

The separate validation run `confirmed-forks-validation-20260922` passed under ADR 0028: 59 comparisons, one evidenced exclusion, and zero acquisition errors. Its 90 behavioral tests passed, and exact offline replay included the exclusion record. The first full run, `confirmed-forks-full-20260922`, was paused after its first upstream listing returned 26,093 rows containing only 14,781 distinct IDs. It is not a complete dataset. Recovery under ADR 0029 uses a new run and keeps this evidence intact.

The full ordering diagnostic returned 26,100 unique fork IDs with zero duplicates or creation order inversions. It found 11,321 IDs absent from the original listing; two previously observed IDs were missing and returned 404 by numeric identity. The new bounded pilot and its recovery each produced 59 identical successful comparisons and the same one unresolved metadata 404, so their acquisition acceptance remains failed. Recovery reduced network requests from 209 to 32 and preserved the original cutoff. All 105 behavioral tests passed, including incomplete inventory handling under ADR 0030. These checks validate the repairs; they do not establish a complete research dataset.

On 2026-09-22, the original collector was stopped and replaced by `confirmed-forks-full-recovery-20260922`, which has since been superseded by the optimized run above. That historical run imported 24,617 attributable responses and 261 validated listing pages, retains the original cutoff of `2026-09-22T14:48:04.707823+00:00`, and continues with all 30 approved upstreams. Its recorded coverage treated the two missing IDs as unresolved errors under the previous policy. Inspect that run's `progress.json`, `fork_errors.jsonl` and eventual `acceptance.json`; launch and partial progress do not imply acceptance.

The 2026-09-22 acquisition pilot covered the 30 confirmed upstreams and froze 60 forks. It completed 59 comparisons; one OpenMontage fork had no common ancestor with the frozen upstream revision, so acceptance remains failed. All 86 behavioral tests passed, and isolated offline replay reproduced the collected artifacts without network requests. The run is `data/skill-pattern-mine/runs/confirmed-forks-pilot-20260922/`; inspect `pilot_validation.json` and `comparison_diagnostics.json` before formal acquisition. These are engineering results, not findings about monthly skill modifications.

Existing result tables and figures are in [legacy/eval/tables-and-figures/](legacy/eval/tables-and-figures/).

## License

MIT. See [LICENSE](LICENSE).

## Acknowledgments

Project scaffold adapted from [Si1w/research-template](https://github.com/Si1w/research-template).
