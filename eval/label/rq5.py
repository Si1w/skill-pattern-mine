"""RQ5: how well do commit messages describe and motivate the modification?

Operates on the 305 representative audited records in
``data/analysis/msg_predictions.jsonl``, each carrying labels the model derived
from the commit message alone (``pred_labels``), the reconciled human patch
labels (``gt_labels``), and the message's What/Why expression categories.

Two tables, aligned with the paper:

1. What-coverage (tab:rq5-what-coverage). Treating the human patch labels as the
   reference, we report two complementary measures at the pattern and family
   levels:
     - Recall: average fraction of reference labels captured by the
       message-derived label set, i.e. how completely commit messages describe
       the implemented modification.
     - Any-hit rate: fraction of records whose message-derived set captures at
       least one reference label, i.e. whether the message mentions any
       implemented modification.

2. Message expression (tab:rq5-message-expression). Percentage of records
   assigned to each What and Why expression category (multi-label), including
   the missing-what / missing-why rates that bound how often a message carries
   no What/Why information at all.

3. Why-vs-family lift (fig:rq5-why-family-heatmap). For each Why category, the
   lift P(family | Why) / P(family) over the patch-family baseline, showing
   which modification families each rationale category is associated with.
   Families with fewer than MIN_FAMILY_SUPPORT records are dropped as their
   baseline is too small for a stable ratio.

The 7-category stated-intent distribution described in the paper depends on a
separate commit-intent coding that is not present in the current
``msg_predictions.jsonl``; it is intentionally omitted here.

Outputs:
    eval/tables-and-figures/: rq5-what-coverage.csv, rq5-message-expression.csv,
        rq5-why-family-lift.csv
    paper/figures/rq5/: rq5-why-family-heatmap.pdf, .png

Usage:
    uv run python -m eval.label.rq5
    uv run python -m eval.label.rq5 --predictions PATH --out-dir DIR
"""

import argparse
import collections
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

WHAT_COVERAGE_FIELDNAMES = ["level", "items", "hit_rate", "recall"]
EXPRESSION_FIELDNAMES = ["axis", "category", "records", "share"]
LIFT_FIELDNAMES = ["why", "why_records", "family", "lift"]

# Why categories that index the heatmap rows, with their display labels.
WHY_FAMILY_ROWS = [
    ("describe-skill-objective", "Objective"),
    ("describe-skill-issue", "Issue"),
    ("illustrate-skill-requirement", "Requirement"),
    ("imply-skill-necessity", "Necessity"),
]
# Families with fewer base records than this are dropped from the lift heatmap:
# their lift is divided by a near-zero baseline and is statistically unstable.
MIN_FAMILY_SUPPORT = 5
DEFAULT_FIG_DIR = utils.ROOT / "paper" / "figures" / "rq5"

# Display order for the What/Why expression categories (missing-* last).
WHAT_ORDER = [
    "summarize-skill-object-change", "illustrate-skill-function",
    "describe-skill-implementation-principle", "missing-what",
]
WHY_ORDER = [
    "describe-skill-objective", "describe-skill-issue",
    "illustrate-skill-requirement", "imply-skill-necessity", "missing-why",
]


def load_predictions(path: Path) -> list[dict]:
    """Read the message-prediction records as a list."""
    with Path(path).open() as f:
        return [json.loads(line) for line in f if line.strip()]


def recall_and_hit_rate(
    message_sets: list[set[str]], reference_sets: list[set[str]]
) -> tuple[float, float, int]:
    """Mean recall and any-hit rate of message sets against reference sets.

    Records with an empty reference set have no recall denominator and are
    excluded from both measures, matching the paper's per-record averaging.
    """
    recalls = []
    hits = []
    for message, reference in zip(message_sets, reference_sets):
        if not reference:
            continue
        intersection = message & reference
        recalls.append(len(intersection) / len(reference))
        hits.append(1 if intersection else 0)
    n = len(recalls)
    mean_recall = sum(recalls) / n if n else 0.0
    hit_rate = sum(hits) / n if n else 0.0
    return mean_recall, hit_rate, n


def what_coverage_rows(records: list[dict], label_family: dict[str, str]
                       ) -> list[dict]:
    """What-coverage at the pattern and family levels."""
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
        recall, hit_rate, n = recall_and_hit_rate(message_sets, reference_sets)
        rows.append({
            "level": level,
            "items": n,
            "hit_rate": hit_rate,
            "recall": recall,
        })
    return rows


def expression_rows(records: list[dict]) -> list[dict]:
    """Per-category share of What and Why expression categories."""
    n = len(records)
    rows = []
    for axis, field, order in [
        ("What", "what_expression_categories", WHAT_ORDER),
        ("Why", "why_expression_categories", WHY_ORDER),
    ]:
        counts = collections.Counter()
        for r in records:
            for cat in r.get(field, []):
                counts[cat] += 1
        rank = {c: i for i, c in enumerate(order)}
        for cat in sorted(counts, key=lambda c: (rank.get(c, len(rank)), c)):
            rows.append({
                "axis": axis,
                "category": cat,
                "records": counts[cat],
                "share": counts[cat] / n if n else 0.0,
            })
    return rows


def why_family_lift(records: list[dict], label_family: dict[str, str]
                    ) -> tuple[list[str], dict[str, int], dict[tuple[str, str], float]]:
    """Lift of each (Why category, patch family) pair over the family baseline.

    Lift is ``P(family | Why) / P(family)``: 1.0 means no enrichment, >1
    over-representation, <1 under-representation. Families with fewer than
    ``MIN_FAMILY_SUPPORT`` records are dropped because their baseline is too
    small for a stable ratio. Returns the kept families (in canonical order),
    the per-Why record counts, and the lift per (Why label, family) pair.
    """
    n = len(records)
    rec_families = [
        {label_family[l] for l in r.get("gt_labels", []) if l in label_family}
        for r in records
    ]
    base = collections.Counter()
    for fams in rec_families:
        base.update(fams)
    families = [f for f in utils.family_order(list(base))
                if base[f] >= MIN_FAMILY_SUPPORT]

    why_counts: dict[str, int] = {}
    lift: dict[tuple[str, str], float] = {}
    for why, display in WHY_FAMILY_ROWS:
        idx = [i for i, r in enumerate(records)
               if why in r.get("why_expression_categories", [])]
        why_counts[display] = len(idx)
        for f in families:
            p_cond = (sum(1 for i in idx if f in rec_families[i]) / len(idx)
                      if idx else 0.0)
            p_base = base[f] / n if n else 0.0
            lift[(display, f)] = p_cond / p_base if p_base else 0.0
    return families, why_counts, lift


def lift_rows(families: list[str], why_counts: dict[str, int],
              lift: dict[tuple[str, str], float]) -> list[dict]:
    """Flatten the lift map into CSV rows."""
    rows = []
    for _, display in WHY_FAMILY_ROWS:
        for f in families:
            rows.append({
                "why": display,
                "why_records": why_counts[display],
                "family": f,
                "lift": lift[(display, f)],
            })
    return rows


def plot_why_family_heatmap(families: list[str], why_counts: dict[str, int],
                            lift: dict[tuple[str, str], float], path: Path) -> None:
    """Render the Why-vs-family lift heatmap, mirroring the paper figure."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np

    rows = [d for _, d in WHY_FAMILY_ROWS]
    matrix = np.array([[lift[(d, f)] for f in families] for d in rows])

    fig, ax = plt.subplots(figsize=(0.62 * len(families) + 2.2, 3.4))
    # Diverging warm-cool map centred at lift 1.0 (warm below, cool above),
    # built from the legacy academic palette ends so the figure matches the
    # warm-cool scheme used elsewhere in the paper.
    cmap = matplotlib.colors.LinearSegmentedColormap.from_list(
        "rq5_why_family", ["#FFE6B7", "#FFFFFF", "#1E466E"]
    )
    vmax = max(2.0, float(np.nanmax(matrix)))
    norm = matplotlib.colors.TwoSlopeNorm(vmin=0.0, vcenter=1.0, vmax=vmax)
    im = ax.imshow(matrix, cmap=cmap, norm=norm, aspect="auto")

    ax.set_xticks(range(len(families)))
    ax.set_xticklabels(families, rotation=45, ha="right")
    ax.set_yticks(range(len(rows)))
    ax.set_yticklabels([f"{d} ({why_counts[d]})" for d in rows])
    for i in range(len(rows)):
        for j in range(len(families)):
            # White text on dark (high-lift) cells, deep blue on light ones.
            color = "white" if norm(matrix[i, j]) >= 0.75 else "#1E466E"
            ax.text(j, i, f"{matrix[i, j]:.1f}", ha="center", va="center",
                    color=color, fontsize=9)
    cbar = fig.colorbar(im, ax=ax)
    cbar.set_label("Lift over family baseline")
    ax.set_xticks(np.arange(-0.5, len(families), 1), minor=True)
    ax.set_yticks(np.arange(-0.5, len(rows), 1), minor=True)
    ax.grid(which="minor", color="white", linewidth=2)
    ax.tick_params(which="minor", length=0)

    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path.with_suffix(".pdf"))
    fig.savefig(path.with_suffix(".png"), dpi=150)
    plt.close(fig)


def write_csv(rows: list[dict], fieldnames: list[str], path: Path) -> None:
    """Write rows to CSV, formatting fractional columns to 4 decimals."""
    floats = {"hit_rate", "recall", "share", "lift"}
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
    parser.add_argument("--fig-dir", type=Path, default=DEFAULT_FIG_DIR)
    parser.add_argument("--num_samples", type=int, default=None,
                        help="limit to the first N records for a dry run")
    args = parser.parse_args()

    records = load_predictions(args.predictions)
    if args.num_samples:
        records = records[: args.num_samples]
    label_family = utils.load_label_family_map()

    coverage = what_coverage_rows(records, label_family)
    expression = expression_rows(records)
    families, why_counts, lift = why_family_lift(records, label_family)
    write_csv(coverage, WHAT_COVERAGE_FIELDNAMES,
              args.out_dir / "rq5-what-coverage.csv")
    write_csv(expression, EXPRESSION_FIELDNAMES,
              args.out_dir / "rq5-message-expression.csv")
    write_csv(lift_rows(families, why_counts, lift), LIFT_FIELDNAMES,
              args.out_dir / "rq5-why-family-lift.csv")
    plot_why_family_heatmap(families, why_counts, lift,
                            args.fig_dir / "rq5-why-family-heatmap")

    logger.info("records=%d", len(records))
    for r in coverage:
        logger.info("  %-8s hit-rate=%5.1f%% recall=%5.1f%% (n=%d)",
                    r["level"], 100 * r["hit_rate"], 100 * r["recall"],
                    r["items"])
    for r in expression:
        logger.info("  %-4s %-42s %5.1f%%", r["axis"], r["category"],
                    100 * r["share"])
    logger.info("dropped low-support families (<%d): %s", MIN_FAMILY_SUPPORT,
                sorted(set(utils.FAMILY_ORDER) - set(families)))
    logger.info("wrote rq5-what-coverage.csv, rq5-message-expression.csv, "
                "rq5-why-family-lift.csv, rq5-why-family-heatmap.pdf/png")


if __name__ == "__main__":
    main()
