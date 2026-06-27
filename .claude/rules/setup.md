---
description: This file describes the global setup instructions for the project.
---

# Global Setup Instructions

All code runs on a HPC cluster (SLURM). Follow the instructions below to set up your environment.

## HPC

### Hardware

| Type | Model |
|------|-------|
| GPU  | h200, h100 |
| GPU  | a100 (40g/80g), l40s, rtx6000 |
| GPU  | a40, a30, rtx3070, rtx2080 |
| CPU  | sapphire_rapids, icelake |
| CPU  | zen4, zen3, zen2 |
| CPU  | cascadelake, skylake_avx512 |

### Execution

Run project code directly through `uv` from the project root, both locally and in SLURM jobs.

```bash
uv run python eval/<benchmark>/main.py --step <step>
```

### Cache

All caches are redirected to `/scratch/` via `~/.bashrc` to avoid filling `/users/` quota.

```bash
export XDG_CACHE_HOME=/scratch/users/$USER/cache
export HF_HOME=/scratch/users/$USER/cache/huggingface
export VLLM_CACHE_ROOT=/scratch/users/$USER/cache/vllm
export TORCH_HOME=/scratch/users/$USER/cache/torch
export TRITON_CACHE_DIR=/scratch/users/$USER/cache/triton
export CUDA_CACHE_PATH=/scratch/users/$USER/cache/nv
export UV_CACHE_DIR=/scratch/users/$USER/cache/uv
```

### Storage

| Path | Quota | Usage |
|------|-------|-------|
| /users/ | 50GB | Code, configs, small files |
| /scratch/ | 200GB | Job I/O, large datasets |

## Environment

- Python version: **3.12** (pinned)
- Use `uv` to manage Python environments on local, login, and compute nodes
- Run Python entry points with `uv run python ...`

### Common Libraries

| Category | Libraries |
|----------|-----------|
| Data & Computation | numpy, polars, scipy, statsmodels |
| Visualization | matplotlib, seaborn |
| ML/DL | torch, transformers, datasets, scikit-learn |
| LLM Inference | vllm |
| LLM API | mistralai, anthropic, openai, google-genai |
| Sandboxing | e2b, docker |
| Utilities | tqdm, jsonlines |

Use Python scripts (`*.py`) for plotting and result table generation. Do not use Jupyter notebooks as the project workflow.
