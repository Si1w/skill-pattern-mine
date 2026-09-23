"""How often forks add new skills alongside modifying existing ones.

The study scopes its corpus to modifications of skills already present upstream
(Section III), excluding whole-skill additions. This script quantifies the
excluded behavior: across the fork branch comparisons before in-skill scoping
(``data/mine/diffs.jsonl``), how many forks add a new skill (a `SKILL.md` whose
directory is not an existing upstream skill), and how many do so while also
modifying an existing skill.

A new skill is a file named `SKILL.md` with status ``added`` whose parent
directory is not among the upstream skill directories in
``data/mine/skills_index.jsonl``. A fork modifies an existing skill when it
touches any file inside an upstream skill directory.

Outputs:
    eval/tables-and-figures/new-skill-addition.csv

Usage:
    uv run python -m eval.mine.new_skill_addition
"""

import argparse
import csv
import json
import logging
from collections import defaultdict
from pathlib import Path, PurePosixPath

logger = logging.getLogger(__name__)
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DIFFS = ROOT / "data" / "mine" / "diffs.jsonl"
DEFAULT_INDEX = ROOT / "data" / "mine" / "skills_index.jsonl"
DEFAULT_OUT = ROOT / "eval" / "tables-and-figures" / "new-skill-addition.csv"

FIELDNAMES = ["category", "count", "share_of_total", "denominator"]


def load_existing_skill_dirs(index_path: Path) -> dict[str, set[str]]:
    """Map each upstream repo to its set of skill directories (SKILL.md parents)."""
    existing: dict[str, set[str]] = defaultdict(set)
    with Path(index_path).open() as f:
        for line in f:
            d = json.loads(line)
            existing[d["repo"]].add(str(PurePosixPath(d["path"]).parent))
    return existing


def classify_row(row: dict, existing: dict[str, set[str]]) -> tuple[bool, bool]:
    """Return (modifies_existing_skill, adds_new_skill) for one fork comparison."""
    ex = existing.get(row["upstream"], set())
    touches_existing = False
    adds_new = False
    for fl in row.get("files") or []:
        fn = fl.get("filename", "")
        sd = str(PurePosixPath(fn).parent)
        if PurePosixPath(fn).name == "SKILL.md" and fl.get("status") == "added":
            if sd not in ex:
                adds_new = True
        if any(sd == d or sd.startswith(d + "/") or fn.startswith(d + "/")
               for d in ex):
            touches_existing = True
    return touches_existing, adds_new


def tally(diffs_path: Path, existing: dict[str, set[str]]) -> dict:
    """Count modify/add/both categories over all fork branch comparisons."""
    counts = {"total": 0, "modifies_existing": 0, "adds_new": 0, "both": 0,
              "adds_new_only": 0}
    with Path(diffs_path).open() as f:
        for line in f:
            modifies, adds = classify_row(json.loads(line), existing)
            counts["total"] += 1
            counts["modifies_existing"] += modifies
            counts["adds_new"] += adds
            counts["both"] += modifies and adds
            counts["adds_new_only"] += adds and not modifies
    return counts


def write_csv(counts: dict, path: Path) -> None:
    """Write the category counts and shares to CSV."""
    total = counts["total"]
    rows = [
        ("modifies_existing_skill", counts["modifies_existing"]),
        ("adds_new_skill", counts["adds_new"]),
        ("modifies_existing_and_adds_new", counts["both"]),
        ("adds_new_skill_only", counts["adds_new_only"]),
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        for cat, n in rows:
            writer.writerow({"category": cat, "count": n,
                             "share_of_total": f"{n / total:.4f}" if total else "0",
                             "denominator": total})


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--diffs", type=Path, default=DEFAULT_DIFFS)
    parser.add_argument("--index", type=Path, default=DEFAULT_INDEX)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()

    existing = load_existing_skill_dirs(args.index)
    counts = tally(args.diffs, existing)
    write_csv(counts, args.out)

    total = counts["total"]
    me = counts["modifies_existing"]
    logger.info("fork branch comparisons: %d", total)
    logger.info("  modifies existing skill: %d (%.1f%%)", me, 100 * me / total)
    logger.info("  adds new skill: %d (%.1f%%)", counts["adds_new"],
                100 * counts["adds_new"] / total)
    logger.info("  both: %d (%.1f%% of all, %.1f%% of modifiers)",
                counts["both"], 100 * counts["both"] / total,
                100 * counts["both"] / me if me else 0)
    logger.info("  adds new skill only: %d (%.1f%%)", counts["adds_new_only"],
                100 * counts["adds_new_only"] / total)
    logger.info("wrote new-skill-addition.csv")


if __name__ == "__main__":
    main()
