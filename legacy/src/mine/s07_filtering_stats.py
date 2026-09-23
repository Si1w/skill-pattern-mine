"""Compute the corpus-construction filtering counts and write them to CSV.

Reads the artifacts produced by s02-s06 and emits one row per construction
step to ``data/mine/filtering_stats.csv`` with columns ``step,unit,count``.

The five steps mirror the corpus-construction table in the paper:
  1. Enumerate public forks                  (forks)              -> forks.jsonl
  2. Remove trivial forks                     (forks)              -> push>create+5m
  3. Compare branches, drop shared history    (branch comparisons) -> diffs.jsonl
  4. Retain in-skill changes                  (branch comparisons) -> diff_in_skill.jsonl
  5. Deduplicate redundant branches           (branch comparisons) -> diff_cleaned.jsonl

The table stops at corpus construction. ``diff_cleaned.jsonl`` (step 5) is the
corpus handed to modification categorization; dropping zero-label instances
happens after labeling and belongs to that later stage, not here.

Counts reflect whatever is on disk at run time. ``diffs.jsonl`` is rewritten
in place by s03's ``drop_shared_pass`` (shared-history and tombstone removal),
so step 3 already reflects that drop rather than the raw compare total.

Usage:
    uv run python -m mine.s07_filtering_stats
"""

import csv
import json
import logging
from datetime import datetime, timedelta

from mine.utils import DATA_DIR

logger = logging.getLogger(__name__)
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

FORKS_PATH = DATA_DIR / "forks.jsonl"
DIFFS_PATH = DATA_DIR / "diffs.jsonl"
IN_SKILL_PATH = DATA_DIR / "diff_in_skill.jsonl"
CLEANED_PATH = DATA_DIR / "diff_cleaned.jsonl"
OUT_PATH = DATA_DIR / "filtering_stats.csv"

PUSH_GRACE = timedelta(minutes=5)


def _count_lines(path) -> int:
    """Count non-blank JSONL rows; 0 if the file is missing."""
    if not path.exists():
        logger.warning("missing %s — counting as 0", path)
        return 0
    with open(path) as f:
        return sum(1 for line in f if line.strip())


def _likely_modified(fork: dict) -> bool:
    """True iff the fork has a post-creation push beyond the 5-minute grace."""
    try:
        pushed = datetime.fromisoformat(fork["pushed_at"].replace("Z", "+00:00"))
        created = datetime.fromisoformat(fork["created_at"].replace("Z", "+00:00"))
    except (KeyError, ValueError):
        return True
    return pushed > created + PUSH_GRACE


def count_active_forks(path=FORKS_PATH) -> int:
    """Count forks that survive the trivial-fork filter."""
    if not path.exists():
        logger.warning("missing %s — counting as 0", path)
        return 0
    n = 0
    with open(path) as f:
        for line in f:
            if line.strip() and _likely_modified(json.loads(line)):
                n += 1
    return n


def collect_stats() -> list[tuple[str, str, int]]:
    """Return the five (step, unit, count) rows of the corpus-construction pipeline."""
    return [
        ("Enumerate public forks", "forks", _count_lines(FORKS_PATH)),
        ("Remove trivial forks", "forks", count_active_forks()),
        ("Compare branches, drop shared history", "branch comparisons",
         _count_lines(DIFFS_PATH)),
        ("Retain in-skill changes", "branch comparisons",
         _count_lines(IN_SKILL_PATH)),
        ("Deduplicate redundant branches", "branch comparisons",
         _count_lines(CLEANED_PATH)),
    ]


def write_csv(rows: list[tuple[str, str, int]], path=OUT_PATH) -> None:
    """Write the filtering counts to CSV with a step/unit/count header."""
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["step", "unit", "count"])
        w.writerows(rows)
    logger.info("wrote %d filtering steps to %s", len(rows), path)


def main():
    rows = collect_stats()
    for step, unit, count in rows:
        logger.info("%-34s %-18s %d", step, unit, count)
    write_csv(rows)


if __name__ == "__main__":
    main()
