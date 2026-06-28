"""Audit agreement and consensus-vs-LLM classification metrics.

Reads the human-audit verdict files under ``data/audit/`` and reports two
tables, mirroring the legacy ``human-audit-metrics.csv`` and
``consensus-vs-llm-metrics.csv``:

1. Inter-auditor agreement (auditor A vs auditor B). Each auditor applies
   per-record ``remove_labels`` / ``add_labels`` edits to the LLM
   ``predicted_labels``. We report the derived label-set agreement: mean
   Jaccard, positive agreement, macro per-label Cohen's kappa, and
   Krippendorff's alpha. (The coarse ``verdict`` string is not scored: the two
   auditors record it with opposite conventions, making it uninformative.)

2. Consensus-vs-LLM quality, taking the consensus final label set as reference
   and the LLM ``predicted_labels`` as the prediction: macro-averaged precision
   and recall plus the chance-corrected per-label Cohen's kappa and Krippendorff
   alpha, reported per audit set and in total.

Note on the two auditors: auditor A records non-correct judgements via the
``verdict`` string and prefers ``remove_labels``; auditor B leaves ``verdict``
empty on non-correct records and prefers ``add_labels``. Both are complete
passes with different editing conventions, so exact-set agreement understates
true agreement; report it alongside Jaccard and per-label kappa.

Usage:
    uv run python -m eval.audit.metrics
    uv run python -m eval.audit.metrics --audit-dir data/audit --out-dir DIR
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
DEFAULT_AUDIT_DIR = ROOT / "data" / "audit"
DEFAULT_OUT_DIR = ROOT / "eval" / "tables-and-figures"
CONSENSUS_FILE = "consensus_verdicts.json"

HUMAN_FIELDNAMES = [
    "comparison",
    "items",
    "mean_jaccard",
    "positive_agreement",
    "macro_label_kappa",
    "krippendorff_alpha",
]
CONSENSUS_FIELDNAMES = [
    "comparison",
    "items",
    "macro_precision",
    "macro_recall",
    "macro_label_kappa",
    "krippendorff_alpha",
]


def load_verdicts(path: Path) -> dict[str, dict]:
    """Load a verdict file, keyed by record name."""
    data = json.loads(Path(path).read_text())
    return {v["record"]: v for v in data["verdicts"]}


def find_auditor_files(audit_dir: Path) -> list[Path]:
    """Return the per-auditor verdict files (excludes the consensus file)."""
    return sorted(p for p in audit_dir.glob("audit_verdicts_*.json"))


def predicted_set(verdict: dict) -> set[str]:
    """LLM predicted labels for a record (the audit input)."""
    raw = verdict.get("predicted_labels", "(none)")
    if raw in ("(none)", "", None):
        return set()
    return {x.strip() for x in raw.split(",") if x.strip()}


def final_set(verdict: dict) -> set[str]:
    """Auditor's corrected label set: predicted minus removed plus added."""
    labels = predicted_set(verdict)
    labels -= set(verdict.get("remove_labels") or [])
    labels |= set(verdict.get("add_labels") or [])
    return labels


def cohen_kappa(pairs: list[tuple[str, str]]) -> tuple[float, float]:
    """Nominal Cohen's kappa over category pairs; returns (kappa, observed)."""
    n = len(pairs)
    if n == 0:
        return 0.0, 0.0
    observed = sum(a == b for a, b in pairs) / n
    left = collections.Counter(a for a, _ in pairs)
    right = collections.Counter(b for _, b in pairs)
    expected = sum((left[k] / n) * (right.get(k, 0) / n) for k in left)
    kappa = (observed - expected) / (1 - expected) if expected != 1 else 1.0
    return kappa, observed


def jaccard(left: set[str], right: set[str]) -> float:
    """Jaccard similarity; two empty sets count as full agreement."""
    union = left | right
    return 1.0 if not union else len(left & right) / len(union)


def krippendorff_alpha_binary(left: list[set[str]], right: list[set[str]]) -> float:
    """Nominal Krippendorff's alpha over (record, label) presence decisions.

    Each (record, label) pair in the observed label universe is one unit coded
    by two raters as present/absent (a binary nominal variable). This matches
    the per-label binary framing used for macro Cohen's kappa, so the two are
    directly comparable. Alpha = 1 - Do/De with Do the observed and De the
    expected disagreement; alpha = 1.0 when every unit is coded identically.
    """
    universe = sorted({lab for s in left + right for lab in s})
    # values[c] = list of "1"/"0" codes by coder c, one per (record, label) unit
    codes_a: list[str] = []
    codes_b: list[str] = []
    for lab in universe:
        for a_set, b_set in zip(left, right):
            codes_a.append("1" if lab in a_set else "0")
            codes_b.append("1" if lab in b_set else "0")

    n = len(codes_a)
    if n == 0:
        return 1.0
    # Observed disagreement: fraction of units the two coders disagree on.
    do = sum(x != y for x, y in zip(codes_a, codes_b)) / n
    # Expected disagreement from the overall value distribution (2 ratings/unit).
    counts = collections.Counter(codes_a + codes_b)
    total = sum(counts.values())
    p1 = counts.get("1", 0) / total
    p0 = counts.get("0", 0) / total
    de = 2 * p1 * p0  # prob two random ratings differ (nominal, 2 categories)
    return 1.0 - do / de if de else 1.0


def label_set_metrics(left: list[set[str]], right: list[set[str]]) -> dict:
    """Mean Jaccard, positive agreement, macro per-label kappa, and alpha.

    Exact-set agreement is intentionally omitted: the two auditors record
    corrections with opposite conventions (A removes, B adds), so an exact
    match understates true agreement. Jaccard, positive agreement, per-label
    kappa, and Krippendorff's alpha capture partial agreement faithfully.
    """
    n = len(left)
    mean_jaccard = sum(jaccard(a, b) for a, b in zip(left, right)) / n

    universe = sorted({lab for s in left + right for lab in s})
    n11 = n01 = n10 = 0
    kappas = []
    for lab in universe:
        in_left = [lab in s for s in left]
        in_right = [lab in s for s in right]
        kappa, _ = cohen_kappa(list(zip(
            ["y" if x else "n" for x in in_left],
            ["y" if x else "n" for x in in_right],
        )))
        kappas.append(kappa)
        for a, b in zip(in_left, in_right):
            if a and b:
                n11 += 1
            elif a and not b:
                n10 += 1
            elif b and not a:
                n01 += 1
    denom = 2 * n11 + n01 + n10
    positive = 2 * n11 / denom if denom else 1.0
    macro_kappa = sum(kappas) / len(kappas) if kappas else 0.0
    return {
        "mean_jaccard": mean_jaccard,
        "positive_agreement": positive,
        "macro_label_kappa": macro_kappa,
        "krippendorff_alpha": krippendorff_alpha_binary(left, right),
    }


def precision_recall(gold: list[set[str]], pred: list[set[str]]) -> dict:
    """Macro-averaged precision and recall of ``pred`` against ``gold``.

    Treats the consensus labels as the reference and the LLM labels as the
    prediction, so precision reflects how often an LLM label was kept and recall
    how often a consensus label was found. This is the only place a reference
    direction is assumed; the chance-corrected agreement measures are symmetric.

    Per-label precision/recall are averaged over every label in gold or pred; a
    label with a zero denominator contributes 0 to the average, matching the
    scikit-learn macro convention.
    """
    per: dict[str, dict[str, int]] = collections.defaultdict(
        lambda: {"tp": 0, "fp": 0, "fn": 0})
    for g, p in zip(gold, pred):
        for lab in g | p:
            in_g, in_p = lab in g, lab in p
            if in_g and in_p:
                per[lab]["tp"] += 1
            elif in_p:
                per[lab]["fp"] += 1
            elif in_g:
                per[lab]["fn"] += 1
    precisions, recalls = [], []
    for d in per.values():
        pd, rd = d["tp"] + d["fp"], d["tp"] + d["fn"]
        precisions.append(d["tp"] / pd if pd else 0.0)
        recalls.append(d["tp"] / rd if rd else 0.0)
    macro_p = sum(precisions) / len(precisions) if precisions else 0.0
    macro_r = sum(recalls) / len(recalls) if recalls else 0.0
    return {"macro_precision": macro_p, "macro_recall": macro_r}


def human_audit_row(a: dict[str, dict], b: dict[str, dict]) -> dict:
    """Auditor A vs auditor B agreement row over their shared records."""
    recs = sorted(set(a) & set(b))
    label_metrics = label_set_metrics(
        [final_set(a[r]) for r in recs], [final_set(b[r]) for r in recs]
    )
    return {
        "comparison": "auditor A vs auditor B",
        "items": len(recs),
        **label_metrics,
    }


def consensus_llm_row(consensus: dict[str, dict], audit_set: str | None = None,
                      label: str = "consensus vs LLM") -> dict:
    """Human-consensus vs LLM row: precision, recall, Cohen's kappa, alpha.

    Precision and recall (consensus as reference) capture the direction of the
    disagreement, i.e. whether the LLM over- or under-labels; Cohen's kappa and
    Krippendorff's alpha give chance-corrected per-label agreement.

    If ``audit_set`` is given, restrict to records tagged with that ``set``
    (e.g. ``"sample"`` or ``"low-confidence"``) so quality can be reported per
    audit set, which the validation design requires.
    """
    recs = sorted(r for r in consensus
                  if audit_set is None or consensus[r].get("set") == audit_set)
    gold = [final_set(consensus[r]) for r in recs]
    pred = [predicted_set(consensus[r]) for r in recs]
    pr = precision_recall(gold, pred)
    agr = label_set_metrics(gold, pred)
    return {
        "comparison": label,
        "items": len(recs),
        "macro_precision": pr["macro_precision"],
        "macro_recall": pr["macro_recall"],
        "macro_label_kappa": agr["macro_label_kappa"],
        "krippendorff_alpha": agr["krippendorff_alpha"],
    }


def write_csv(rows: list[dict], fieldnames: list[str], path: Path) -> None:
    """Write metric rows to CSV, formatting floats to 4 decimals."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({
                k: (f"{v:.4f}" if isinstance(v, float) else v)
                for k, v in row.items()
            })


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audit-dir", type=Path, default=DEFAULT_AUDIT_DIR)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    args = parser.parse_args()

    auditor_files = find_auditor_files(args.audit_dir)
    if len(auditor_files) < 2:
        raise FileNotFoundError(
            f"need >=2 audit_verdicts_*.json under {args.audit_dir}, "
            f"found {len(auditor_files)}"
        )
    a = load_verdicts(auditor_files[0])
    b = load_verdicts(auditor_files[1])
    consensus = load_verdicts(args.audit_dir / CONSENSUS_FILE)

    human_row = human_audit_row(a, b)
    sample_row = consensus_llm_row(consensus, "sample", "sample")
    lowconf_row = consensus_llm_row(consensus, "low-confidence", "low-confidence")
    total_row = consensus_llm_row(consensus, None, "total")
    class_rows = [sample_row, lowconf_row, total_row]

    human_path = args.out_dir / "human-audit-metrics.csv"
    class_path = args.out_dir / "consensus-vs-llm-metrics.csv"
    write_csv([human_row], HUMAN_FIELDNAMES, human_path)
    write_csv(class_rows, CONSENSUS_FIELDNAMES, class_path)

    logger.info("auditor files: %s", [p.name for p in auditor_files[:2]])
    logger.info(
        "A vs B (n=%d): mean-jaccard=%.3f, positive-agr=%.3f, "
        "macro-label-kappa=%.3f, krippendorff-alpha=%.3f",
        human_row["items"], human_row["mean_jaccard"],
        human_row["positive_agreement"], human_row["macro_label_kappa"],
        human_row["krippendorff_alpha"],
    )
    for row in class_rows:
        logger.info(
            "consensus vs LLM [%s] (n=%d): macro-P=%.3f, macro-R=%.3f, "
            "kappa=%.3f, krippendorff-alpha=%.3f",
            row["comparison"], row["items"], row["macro_precision"],
            row["macro_recall"], row["macro_label_kappa"], row["krippendorff_alpha"],
        )
    logger.info("wrote %s", human_path)
    logger.info("wrote %s", class_path)


if __name__ == "__main__":
    main()
