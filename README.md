# Skill Pattern Mine

> An empirical study of how developers fork and modify agent skills on GitHub.

## Overview

The study observes public forks of skill repositories and describes the monthly net changes that fork owners make to skill packages: which modification patterns occur, how their prevalence changes over time, how package length changes, and which changes are relevant to security. Design decisions and the remaining research questions are recorded as architecture decision records in [docs/adr/](docs/adr/README.md). The manuscript lives in a separate Overleaf repository checked out under `paper/`, which is ignored by Git.

The implemented part is data acquisition: repository discovery and screening, fork enumeration with frozen branches, comparison against the frozen upstream, acceptance checks, and monthly extraction of complete package endpoints with origin evidence from local Git history. Taxonomy discovery, labeling, measurement and analysis are still design work.

## Architecture

```text
skill-pattern-mine/
├── .agents/          # Agent instructions and project specifications
├── AGENTS.md         # Project instructions for coding agents
├── configs/          # Experiment settings (YAML)
├── docs/adr/         # Design decisions and implementation mapping
├── eval/             # Entry point and future analysis scripts
├── src/              # Domain models, GitHub acquisition, Git history and extraction
├── tests/            # Behavioral checks
└── pyproject.toml    # Project metadata and pinned dependencies (uv)
```

Pipeline stages and their modules:

| Step | What it does | Module |
| --- | --- | --- |
| `repositories` | Discover candidates, freeze default branches, measure complete trees, screen | `src/repositories.py` |
| `review` | Export a screening worksheet for human review | `src/review.py` |
| `forks` | Enumerate forks, freeze their branches, compare with the frozen upstream | `src/forks.py` |
| `verify` | Check saved artifacts offline and write `acceptance.json` | `src/verify.py` |
| `extract` | Build monthly package net changes from local Git history | `src/git_history.py`, `src/extract.py` |

## Quick Start

### Prerequisites

- Python 3.12 and [uv](https://docs.astral.sh/uv/).
- An authenticated [GitHub CLI](https://cli.github.com/) for live API reads. Offline replay does not need it.
- Git, for monthly extraction.

### Installation

```bash
uv sync --locked
```

### Configuration

`configs/skill-pattern-mine.yaml` holds only the settings a run freezes; the reasoning behind each value lives in the ADRs.

| Section | Setting | Governing decision |
| --- | --- | --- |
| `retrieval` | Topic seeds, the `skill` intent query split into complete fork bands, and the two plugin manifest queries | ADRs 0002, 0019, 0044 |
| `screening` | `minimum_forks` of 2,000, `maximum_forks_per_star`, `maximum_packages`, and `repositories`, the 34 repositories retained by the purpose review in `docs/repository-review-2026-10-21.csv` | ADRs 0022, 0026, 0042, 0043, 0048 |
| `observation` | `cutoff_utc`, the exclusive upper bound of the window; months follow UTC committer time and the final month is partial | ADRs 0015, 0045 |
| `extraction` | Git timeout and the largest blob read during monthly extraction | ADRs 0020, 0023 |

### Usage

All commands run from the project root. Artifacts are written to `data/skill-pattern-mine/runs/{run_id}/`. Reusing a run ID resumes that run with its frozen settings; a changed configuration or sample bound is rejected.

Collect candidate repositories and export the review worksheet:

```bash
uv run --locked python eval/skill-pattern-mine/main.py --step repositories --run_id candidates
uv run --locked python eval/skill-pattern-mine/main.py --step review --run_id candidates
```

Review the candidates in `repository_review.yaml`, list the repositories to retain under `screening.repositories` in `configs/skill-pattern-mine.yaml`, and record each exclusion and its reason in an ADR. The confirmed cohort is then imported from the candidate run and its forks are collected:

```bash
uv run --locked python eval/skill-pattern-mine/main.py --step all --source_run candidates --run_id full
```

A bounded engineering pilot limits forks per upstream and commits per comparison:

```bash
uv run --locked python eval/skill-pattern-mine/main.py --step all --source_run candidates --pilot --num_samples 2 --run_id pilot
```

Replay a run from saved responses without network access, and extract monthly records once acquisition has finished and passed acceptance:

```bash
uv run --locked python eval/skill-pattern-mine/main.py --step all --offline --run_id pilot
uv run --locked python eval/skill-pattern-mine/main.py --step extract --run_id full --month 2026-03
```

Omit `--month` to process every observed month. Inside a pilot run, `--allow_partial` permits extraction before acquisition is complete. Inspect `acceptance.json`, `monthly_acceptance.json` and the error files before using outputs.

Run the behavioral checks:

```bash
uv run --locked python -m unittest discover -s tests -v
```

## Results

Not yet available. Tables and figures will be written to `eval/tables-and-figures/`.

## License

MIT. See [LICENSE](LICENSE).

## Acknowledgments

The project layout follows [Si1w/research-template](https://github.com/Si1w/research-template).
