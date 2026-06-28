# Skill Pattern Mine

> An empirical study of how developers fork and modify Claude Code skills across public GitHub repositories.

## Overview

Agent skills (reusable instruction sets for LLM-based agents) are rapidly evolving on GitHub, yet little is known about how developers adapt them to new contexts. This study mines 1,126 fork-level skill modifications across 6 upstream repositories, classifies adaptation patterns using a grounded-theory taxonomy, and analyzes security-relevant changes and commit-message intent.

**Key findings:**

- We identify 10 modification families (e.g., *lifecycle*, *procedure*, *decision*, *policy*) covering 40%+ of observed modifications each for the top families.
- `modify-skill-metadata` is the single most common pattern (18.2% prevalence), followed by `add-procedure-step` (17.8%) and `add-decision-rule` (15.1%).
- Security-relevant modifications appear in a non-trivial share of instances, spanning both hardening and relaxation changes.
- Commit messages systematically under-describe the *why* behind skill adaptations.

## Selected Upstream Repositories

- [anthropics/skills](https://github.com/anthropics/skills)
- [obra/superpowers](https://github.com/obra/superpowers)
- [affaan-m/everything-claude-code](https://github.com/affaan-m/everything-claude-code)
- [mattpocock/skills](https://github.com/mattpocock/skills)
- [vercel-labs/agent-skills](https://github.com/vercel-labs/agent-skills)
- [ComposioHQ/awesome-claude-skills](https://github.com/ComposioHQ/awesome-claude-skills)
## Dataset

| Split | File | Rows |
|-------|------|------|
| Labeled instances | `data/artifact/instances.public.jsonl` | 1,126 |
| Commit-message instances (subset) | `data/artifact/msg_instances.public.jsonl` | 277 |

Fork-owner identifiers are pseudonymized (UUID v5); secrets and local paths are redacted. Upstream repository names are preserved.

**Fields — `instances.public.jsonl`**

| Field | Description |
|-------|-------------|
| `modification_id` | UUID v5 (pseudonymized fork identifier) |
| `upstream` | Upstream repository (`org/repo`) |
| `commit_messages` | List of commit messages in the fork branch |
| `patch` | Unified diff of skill file changes |
| `labels` | Modification pattern labels (taxonomy) |

## Repository Structure

```
project-root/
├── configs/          # Experiment configs (YAML)
├── data/artifact/    # Public release datasets
├── eval/             # Measurement and plotting scripts
│   └── tables-and-figures/
├── scripts/          # SLURM job scripts
├── src/              # Source code
│   ├── mine/         # Fork mining pipeline
│   ├── label/        # Taxonomy labeling
│   ├── analysis/     # Aggregate analysis and sanitization
│   └── audit/        # Human audit utilities
└── tests/            # Test suite
```

## Quick Start

**Prerequisites:** Python 3.12, [uv](https://github.com/astral-sh/uv)

```bash
cd skill-pattern-mine
uv sync
```

**Run the analysis pipeline:**

```bash
uv run python -m analysis.sanitize_release --input data/analysis/instances.jsonl --out data/artifact/instances.public.jsonl
```

## Agents & Skills

The labeling pipeline is implemented as Claude Code agents and skills. Agents are invoked via the Claude Code CLI; skills define the step-by-step workflow each agent follows.

**Agents** (`agents/`)

| Agent | Description |
|-------|-------------|
| `taxonomy-builder` | Builds the two-level family→pattern taxonomy from a corpus via grounded-theory open coding. Iterates 50 instances at a time until saturation, pausing for human feedback after each batch. |
| `pattern-labeler` | Classifies each instance against the fixed taxonomy, producing one validated label record grounded in patch evidence. |
| `msg-labeler` | Codes each instance from commit messages alone (blind to the diff), measuring how much signal messages carry on the What and Why axes. |

All agents use `claude-opus-4-8` with medium effort.

**Skills** (`skills/`)

| Skill | Description |
|-------|-------------|
| `iter-taxonomy-build` | Workflow for iterative taxonomy construction: bootstrap on 300 representative instances, then iterate until two consecutive batches add nothing new. |
| `pattern-labeling` | Workflow for patch-grounded pattern classification: scope determination, evidence-based label assignment, and validation. |
| `msg-labeling` | Workflow for commit-message-only coding on the What (patterns + expression) and Why (motivation + intention) axes. |

Each skill directory contains `SKILL.md` (the workflow), `taxonomy.json` (the shared label vocabulary), and `scripts/` (validation helpers).

### Usage

Run the command in Claude Code CLI:

```
@taxonomy-builder run the task
@pattern-labeler  run the task
@msg-labeler      run the task
```

## Results

Full tables and figures are under `eval/tables-and-figures/`.

## License

MIT
