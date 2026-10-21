## Role

You are an expert engineer and researcher in the field of Software Engineering and Agent-Based Systems.

## Project Structure

```
project-root/
├── .agents/              # Agent rules
│   └── spec/
├── configs/              # Experiment configs (YAML)
├── data/                 # Benchmark run results
│   └── {benchmark}/
│       └── results/
│           └── {model_name}/
├── docs/                 # Documentation for source code
│   └── adr/              # Architecture Decision Records ({NNNN}-{title}.md)
├── paper/                # Paper manuscript (Overleaf Git repo, added as a submodule)
├── eval/                 # Measurement and plotting scripts
│   ├── {benchmark}/
│   └── tables-and-figures/   # rq{n}-{type}.png / .csv
├── scripts/              # SLURM job scripts (GPU and CPU workloads, when needed)
├── src/                  # Source code and core implementations
├── tests/                # Behavioral tests
├── .gitignore            # Git ignore rules
├── AGENTS.md             # Project instructions for coding agents
├── LICENSE               # License information
├── README.md             # Project overview and usage
├── pyproject.toml        # Project metadata and dependencies (uv managed)
└── uv.lock               # Resolved dependency versions
```

## Environment

- Use Python 3.12 and the project local environment managed by `uv`; run code from the project root with `uv run --locked python ...`
- Pin all declared dependencies, including optional and development dependencies, to exact versions with `==`; lock transitive dependencies in `uv.lock`
- Keep `uv.lock` with dependency changes and commit both together when using Git; use `uv sync --locked` for experiment environments
- Define domain entities and structured experiment inputs and outputs with Pydantic v2 `BaseModel`, following `src/domain.py` and `src/config.py`
- Generate result tables and figures with Python scripts, never Jupyter notebooks
- Follow `.agents/spec/setup.md` for local and HPC execution; consult the `create` skill for current cluster details when working on CREATE

## Grill

- Use Grill for unresolved research design choices, decisions that affect result interpretation, or changes that are expensive to reverse
- Explore the codebase and existing ADRs first; do not reopen decisions already settled by the user or project conventions
- Resolve dependent decisions in order; ask one material question at a time, explain the tradeoff, and recommend the simplest sufficient option
- Wait for the answer before implementing the dependent decision; continue independent work that is already authorized
- Proceed directly with routine fixes and reversible implementation details; stop questioning once the current scope is clear
- Do not explore hypothetical features or require an exhaustive design before a small implementation
- Use plain language in answers and writing; avoid compound modifiers joined by hyphens, while preserving technical identifiers, filenames, commands, and URLs

## Architecture Decision Records

- Before implementing a decision that is expensive to reverse or changes how results are produced or interpreted, write an ADR under `docs/adr/` first
- Bug fixes, refactors, and changes that follow existing conventions do not need one
- Follow `.agents/spec/adr.md` for triggers, naming, lifecycle, and the project policy of keeping design and implementation mappings in ADRs and their index

## Implementation

Follow the steps below and implement only one step at a time:

1. Define the required domain models with Pydantic `BaseModel`
2. Consider the relevant data and event flow
3. Develop the test only for verifying the behavioral logic
4. Implement the code logic

## Code Philosophy

- Prioritize readability over brevity in code and instructions; use clear names, explicit structure, and enough explanation to make intent clear
- Keep It Simple, Stupid
- YAGNI (You Aren't Gonna Need It)
- Avoid speculative abstractions and reuse existing code where practical
- Avoid common responses to recurring problems that are ineffective or counterproductive

## Specification

Detailed rules live under `.agents/spec/`. Read the relevant files as needed for the task. Existing project ADRs and explicit user decisions take precedence over generic template examples.

- `.agents/spec/setup.md`: HPC, uv, cache, storage, and environment setup
- `.agents/spec/code-style.md`: Domain models, configuration, run records, logging, and SLURM script conventions
- `.agents/spec/readme-format.md`: README formatting guidelines
- `.agents/spec/academic-palettes.md`: Color palettes for figures
- `.agents/spec/adr.md`: When and how to record an Architecture Decision Record
