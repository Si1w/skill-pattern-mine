"""Per-upstream instance coverage from the analysis corpus.

Counts how many analysis instances each upstream repository contributes and
writes the share table. The corpus is ``data/analysis/instances.jsonl`` where
every record carries a flat ``upstream`` string (e.g. ``obra/superpowers``).

Usage:
    uv run python -m eval.mine.instance_coverage
    uv run python -m eval.mine.instance_coverage --instances PATH --out-dir DIR
"""

import argparse
import collections
import csv
import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INSTANCES = ROOT / "data" / "analysis" / "instances.jsonl"
DEFAULT_OUT_DIR = ROOT / "eval" / "tables-and-figures"

INSTANCE_SHARE_FIELDNAMES = [
    "upstream",
    "instances",
    "total_instances",
    "instance_share",
]


def load_instances(path: Path) -> list[dict]:
    """Read the analysis corpus as a list of instance records."""
    with Path(path).open() as f:
        return [json.loads(line) for line in f if line.strip()]


def upstream_share_table(instances: list[dict]) -> list[dict]:
    """Aggregate instances by ``upstream`` and compute each repo's share."""
    counts = collections.Counter(inst.get("upstream", "") for inst in instances)
    total = sum(counts.values())
    rows = [
        {
            "upstream": upstream,
            "instances": count,
            "total_instances": total,
            "instance_share": count / total if total else 0.0,
        }
        for upstream, count in counts.items()
    ]
    rows.sort(key=lambda r: (-r["instance_share"], r["upstream"]))
    return rows


def write_csv(rows: list[dict], path: Path) -> None:
    """Write coverage rows to ``path`` as CSV."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=INSTANCE_SHARE_FIELDNAMES)
        writer.writeheader()
        for row in rows:
            writer.writerow({**row, "instance_share": f"{row['instance_share']:.4f}"})


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--instances", type=Path, default=DEFAULT_INSTANCES)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    args = parser.parse_args()

    instances = load_instances(args.instances)
    rows = upstream_share_table(instances)
    out_path = args.out_dir / "instance-coverage.csv"
    write_csv(rows, out_path)

    logger.info("instances=%d, upstreams=%d", len(instances), len(rows))
    for row in rows:
        logger.info(
            "  %-40s %5d  %6.1f%%",
            row["upstream"],
            row["instances"],
            100 * row["instance_share"],
        )
    logger.info("wrote %s", out_path)


if __name__ == "__main__":
    main()
