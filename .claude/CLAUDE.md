# Role

You are an expert engineer and researcher in the field of Software Engineering and Agent-Based Systems.

# Project Structure

```
project-root/
├── .claude/              # Agent rules
│   └── rules/
├── configs/              # Experiment configs (YAML)
├── data/                 # Benchmark run results
│   └── {benchmark}/
│       └── results/
│           └── {model_name}/
├── docs/                 # Documentation for source code
├── paper/                # Paper manuscript (Overleaf Git repo, added as a submodule)
├── eval/                 # Measurement and plotting scripts
│   ├── {benchmark}/
│   └── tables-and-figures/   # rq{n}-{type}.png / .csv
├── scripts/              # SLURM job scripts (GPU-intensive workloads)
├── src/                  # Source code and core implementations
├── .gitignore            # Git ignore rules
├── LICENSE               # License information
├── README.md             # Project overview and usage
└── pyproject.toml        # Project metadata and dependencies (uv managed)
```

# Git Conventions

- Develop directly on `main`, no feature branches or pull requests
- Commit message format:

```
<type>(<scope>): <subject>

- <body>
```

Types: `feat`, `fix`, `refactor`, `docs`, `test`, `chore`

- Review the code before committing to ensure the logic and correctness

# Environment

- Always run code through `uv` from the project root (e.g., `uv run python ...`), using the project-local environment

# Rules Index

Detailed rules live under [.claude/rules/](.claude/rules/):

- [setup.md](.claude/rules/setup.md) — HPC, uv, cache, storage, and environment setup
- [code-style.md](.claude/rules/code-style.md) — Code style and SLURM script conventions
- [readme-format.md](.claude/rules/readme-format.md) — README formatting guidelines
- [academic-palettes.md](.claude/rules/academic-palettes.md) — Color palettes for figures
