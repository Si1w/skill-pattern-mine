"""Batch instances for the second phase of taxonomy coding.

Taxonomy building has two phases:
  1. bootstrap — code the full 300-instance representative sample
     (``data/label/sample/``) by hand to build an initial taxonomy.
  2. iterate — keep coding *new* instances 50 at a time until the taxonomy
     saturates. This script drives phase 2: it draws from the full label set
     (``data/label/inputs/``), excluding both the bootstrap sample and anything
     already coded, and records each pulled batch as coded — pulling claims it.

Usage:
    python skills/iter-taxonomy-build/scripts/iter.py --status
    python skills/iter-taxonomy-build/scripts/iter.py --next
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

INPUTS_DIR = Path("data/label/inputs")
SAMPLE_DIR = Path("data/label/sample")
CODED_PATH = Path("skills/iter-taxonomy-build/coded.jsonl")
BATCH_SIZE = 50


def _stems(directory: Path) -> set[str]:
    return {p.stem for p in directory.glob("*.json")}


def coded_stems() -> set[str]:
    """Stems already coded in phase 2, read from coded.jsonl."""
    if not CODED_PATH.exists():
        return set()
    out: set[str] = set()
    with open(CODED_PATH) as f:
        for line in f:
            if line.strip():
                out.add(json.loads(line)["stem"])
    return out


def available_stems() -> list[str]:
    """Phase-2 candidates: full inputs minus the bootstrap sample, sorted."""
    return sorted(_stems(INPUTS_DIR) - _stems(SAMPLE_DIR))


def next_batch(size: int = BATCH_SIZE) -> list[dict]:
    """Return up to ``size`` uncoded phase-2 instances and record them as coded.

    Pulling a batch claims it: the returned stems are appended to coded.jsonl
    so the next call returns the following batch.
    """
    done = coded_stems()
    todo = [s for s in available_stems() if s not in done][:size]
    instances = [json.loads((INPUTS_DIR / f"{s}.json").read_text()) for s in todo]
    if todo:
        CODED_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(CODED_PATH, "a") as f:
            for s in todo:
                f.write(json.dumps({"stem": s}) + "\n")
    return instances


def status() -> dict:
    total = len(available_stems())
    done = len(coded_stems())
    return {
        "phase2_pool": total,
        "coded": done,
        "remaining": total - done,
        "batches_left": (total - done + BATCH_SIZE - 1) // BATCH_SIZE,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--next", action="store_true",
                        help="print and claim the next batch of uncoded instances")
    parser.add_argument("--status", action="store_true",
                        help="print phase-2 coding progress")
    parser.add_argument("--size", type=int, default=BATCH_SIZE)
    args = parser.parse_args()

    if args.status:
        print(json.dumps(status(), indent=2))
    else:
        print(json.dumps(next_batch(args.size), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
