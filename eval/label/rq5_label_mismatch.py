"""RQ5: the reverse direction of the What-coverage comparison.

The What-coverage analysis in ``eval.label.rq5`` reports how many patch labels
the commit message captures (recall). This script reports the complementary
direction: how many labels asserted from the commit message have no matching
label in the patch reference set. We call these unmatched labels, following the
same per-record label sets used for recall.

A high unmatched share does not imply the change is absent from the skill. An
unmatched label can arise when an edit was overwritten by a later commit and no
longer appears in the net diff, when the message-only labeling generalizes
beyond what the patch supports, or when the same change receives a different
label on each side. The figure reported in the paper is the unmatched share of
all message-asserted pattern labels.

Operates on the same ``data/analysis/msg_predictions.jsonl`` as
``eval.label.rq5``: each record carries the message-derived labels
(``pred_labels``) and the reconciled human patch labels (``gt_labels``).

Outputs:
    eval/tables-and-figures/rq5-label-mismatch.csv

Usage:
    uv run python -m eval.label.rq5_label_mismatch
    uv run python -m eval.label.rq5_label_mismatch --predictions PATH --out-dir DIR
"""

import argparse
import csv
import json
import logging
from pathlib import Path

from eval.label import utils

logger = logging.getLogger(__name__)
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

DEFAULT_PREDICTIONS = utils.ROOT / "data" / "analysis" / "msg_predictions.jsonl"
DEFAULT_OUT_DIR = utils.ROOT / "eval" / "tables-and-figures"

MISMATCH_FIELDNAMES = [
    "level", "records", "message_labels", "captured", "unmatched",
    "unmatched_share",
]


def load_predictions(path: Path) -> list[dict]:
    """Read the message-prediction records as a list."""
    with Path(path).open() as f:
        return [json.loads(line) for line in f if line.strip()]


def unmatched_counts(message_sets: list[set[str]],
                     reference_sets: list[set[str]]) -> dict:
    """Aggregate message-asserted, captured, and unmatched label counts.

    A captured label is a message label that also appears in the reference set;
    an unmatched label is a message label with no match in the reference set.
    Counts pool over all records, so the share is a label-level rate.
    """
    message_labels = 0
    captured = 0
    unmatched = 0
    for message, reference in zip(message_sets, reference_sets):
        message_labels += len(message)
        captured += len(message & reference)
        unmatched += len(message - reference)
    share = unmatched / message_labels if message_labels else 0.0
    return {
        "records": len(message_sets),
        "message_labels": message_labels,
        "captured": captured,
        "unmatched": unmatched,
        "unmatched_share": share,
    }


def mismatch_rows(records: list[dict], label_family: dict[str, str]
                  ) -> list[dict]:
    """Unmatched-label counts at the pattern and family levels."""
    msg_patterns = [set(r.get("pred_labels", [])) for r in records]
    gt_patterns = [set(r.get("gt_labels", [])) for r in records]

    def to_families(label_sets):
        return [
            {label_family[label] for label in labels if label in label_family}
            for labels in label_sets
        ]

    msg_families = to_families(msg_patterns)
    gt_families = to_families(gt_patterns)

    rows = []
    for level, message_sets, reference_sets in [
        ("Pattern", msg_patterns, gt_patterns),
        ("Family", msg_families, gt_families),
    ]:
        counts = unmatched_counts(message_sets, reference_sets)
        rows.append({"level": level, **counts})
    return rows


def write_csv(rows: list[dict], fieldnames: list[str], path: Path) -> None:
    """Write rows to CSV, formatting the share column to 4 decimals."""
    floats = {"unmatched_share"}
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({
                k: (f"{v:.4f}" if k in floats else v) for k, v in row.items()
            })


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--predictions", type=Path, default=DEFAULT_PREDICTIONS)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--num_samples", type=int, default=None,
                        help="limit to the first N records for a dry run")
    args = parser.parse_args()

    records = load_predictions(args.predictions)
    if args.num_samples:
        records = records[: args.num_samples]
    label_family = utils.load_label_family_map()

    rows = mismatch_rows(records, label_family)
    write_csv(rows, MISMATCH_FIELDNAMES,
              args.out_dir / "rq5-label-mismatch.csv")

    logger.info("records=%d", len(records))
    for r in rows:
        logger.info(
            "  %-8s message-labels=%d captured=%d unmatched=%d "
            "unmatched-share=%.1f%%",
            r["level"], r["message_labels"], r["captured"], r["unmatched"],
            100 * r["unmatched_share"],
        )
    logger.info("wrote rq5-label-mismatch.csv")


if __name__ == "__main__":
    main()
