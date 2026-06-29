"""Label-level uncertainty: agent accuracy on the unbiased audit sample.

The corpus mixes 277 audited instances (using reconciled consensus labels) with
849 unaudited instances (using the original agent labels). This script estimates
how reliable the agent labels are, using only the random-sample audit set, which
is an unbiased draw from the full corpus. The low-confidence set is excluded
because it was oversampled and would bias the estimate.

On that random sample we treat the reconciled consensus as the reference and
report, at the label level:
    - precision: agent labels that survived reconciliation / all agent labels
    - recall: surviving agent labels / (surviving + auditor-added labels)
Both carry a Wilson score interval. Precision is an upper bound: the consensus
was reconciled from the agent output, so auditor anchoring can only inflate
agreement. The independent inter-auditor agreement bounds reliability.

We also report Wilson intervals for the headline family and security
prevalences, so the point estimates carry uncertainty when read against the
849 unaudited instances.

Outputs:
    eval/tables-and-figures/label-uncertainty.csv

Usage:
    uv run python -m eval.label.label_uncertainty
"""

import argparse
import csv
import json
import logging
import math
from pathlib import Path

from eval.label import utils

logger = logging.getLogger(__name__)
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

DEFAULT_CONSENSUS = utils.ROOT / "data" / "audit" / "consensus_verdicts.json"
DEFAULT_OUT_DIR = utils.ROOT / "eval" / "tables-and-figures"
FIELDNAMES = ["measure", "numerator", "denominator", "estimate", "ci_low",
              "ci_high"]

# Headline prevalences to bound, as (label, count, total). Counts are the
# reported instance counts; see RQ1 and RQ4 in the paper.
N_INSTANCES = 1126
HEADLINE_PREVALENCES = [
    ("prevalence:lifecycle", 461, N_INSTANCES),
    ("prevalence:procedure", 459, N_INSTANCES),
    ("prevalence:security-added-line", 209, N_INSTANCES),
]


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson score interval for a binomial proportion."""
    if n == 0:
        return 0.0, 0.0
    p = k / n
    denom = 1 + z * z / n
    center = p + z * z / (2 * n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return (center - half) / denom, (center + half) / denom


def parse_labels(value) -> set[str]:
    """Parse a label field that may be a list or comma-separated string."""
    if not value:
        return set()
    if isinstance(value, list):
        return {x.strip() for x in value if x.strip()}
    return {x.strip() for x in value.split(",") if x.strip()}


def agent_label_accuracy(consensus_path: Path) -> dict:
    """Label-level precision and recall of agent labels on the random sample."""
    verdicts = json.loads(Path(consensus_path).read_text())["verdicts"]
    sample = [v for v in verdicts if v.get("set") == "sample"]

    agent_total = survived = missed = 0
    for v in sample:
        pred = parse_labels(v.get("predicted_labels"))
        added = parse_labels(v.get("add_labels"))
        removed = parse_labels(v.get("remove_labels"))
        final = (pred | added) - removed
        agent_total += len(pred)
        survived += len(pred & final)
        missed += len(final - pred)
    return {
        "records": len(sample),
        "agent_labels": agent_total,
        "survived": survived,
        "removed": agent_total - survived,
        "missed": missed,
    }


def rows_for_csv(acc: dict) -> list[dict]:
    """Build CSV rows for precision, recall, and headline prevalences."""
    rows = []

    prec_k, prec_n = acc["survived"], acc["agent_labels"]
    lo, hi = wilson(prec_k, prec_n)
    rows.append({"measure": "agent_label_precision", "numerator": prec_k,
                 "denominator": prec_n, "estimate": prec_k / prec_n,
                 "ci_low": lo, "ci_high": hi})

    rec_k, rec_n = acc["survived"], acc["survived"] + acc["missed"]
    lo, hi = wilson(rec_k, rec_n)
    rows.append({"measure": "agent_label_recall", "numerator": rec_k,
                 "denominator": rec_n, "estimate": rec_k / rec_n,
                 "ci_low": lo, "ci_high": hi})

    for label, k, n in HEADLINE_PREVALENCES:
        lo, hi = wilson(k, n)
        rows.append({"measure": label, "numerator": k, "denominator": n,
                     "estimate": k / n, "ci_low": lo, "ci_high": hi})
    return rows


def write_csv(rows: list[dict], path: Path) -> None:
    """Write rows to CSV, formatting fractional columns to 4 decimals."""
    floats = {"estimate", "ci_low", "ci_high"}
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        for row in rows:
            writer.writerow({
                k: (f"{v:.4f}" if k in floats else v) for k, v in row.items()
            })


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--consensus", type=Path, default=DEFAULT_CONSENSUS)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    args = parser.parse_args()

    acc = agent_label_accuracy(args.consensus)
    rows = rows_for_csv(acc)
    write_csv(rows, args.out_dir / "label-uncertainty.csv")

    logger.info("random-sample records=%d agent-labels=%d", acc["records"],
                acc["agent_labels"])
    for r in rows:
        logger.info("  %-32s %.1f%% [%.1f, %.1f]", r["measure"],
                    100 * r["estimate"], 100 * r["ci_low"], 100 * r["ci_high"])
    logger.info("wrote label-uncertainty.csv")


if __name__ == "__main__":
    main()
