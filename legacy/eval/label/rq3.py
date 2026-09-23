"""RQ3: which modification families co-occur within the same fork instance?

Reuses RQ1's family assignment (flat ``labels`` mapped to 13 families via the
pattern taxonomy). For every instance we form its family set with branch-level
binary incidence, enumerate all size-2 and size-3 family combinations, and count
how many instances exhibit each bundle. Each bundle reports branch prevalence,
skill breadth, upstream coverage, the expected prevalence under family
independence, and lift (observed / expected) as the association strength. A
second table gives the pairwise co-occurrence prevalence across all families
(use ``--top-family-count`` to restrict to the N most frequent families). The
same pairwise prevalence is rendered as a lower-triangle heatmap.

Outputs (eval/tables-and-figures/):
    rq3-family-bundles.csv, rq3-family-pair-bundles.csv,
    rq3-family-pair-heatmap.png, rq3-family-pair-heatmap.pdf

Usage:
    uv run python -m eval.label.rq3
    uv run python -m eval.label.rq3 --top-family-count 10 --out-dir DIR
    (default reports all families; --top-family-count restricts the pair table)
"""

import argparse
import collections
import csv
import itertools
import logging
from pathlib import Path

from eval.label import utils

logger = logging.getLogger(__name__)
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

DEFAULT_OUT_DIR = utils.ROOT / "eval" / "tables-and-figures"

BUNDLE_FIELDNAMES = [
    "rank", "size", "bundle", "instances", "analyzed_instances",
    "branch_prevalence", "skills_with_bundle", "observed_skills",
    "skill_breadth", "upstreams_with_bundle", "observed_upstreams",
    "upstream_coverage", "expected_prevalence", "lift",
]
PAIR_FIELDNAMES = [
    "family_a", "family_b", "instances", "analyzed_instances",
    "branch_prevalence", "lift",
]


def instance_families(instance: dict, label_family: dict[str, str]) -> set[str]:
    """Family set an instance exhibits (branch-level binary incidence)."""
    return {
        label_family[label]
        for label in instance.get("labels", [])
        if label in label_family
    }


def bundle_rows(instances: list[dict], label_family: dict[str, str],
                min_size: int = 2, max_size: int = 3) -> list[dict]:
    """Frequent family bundles with support, breadth, coverage and lift."""
    n = len(instances)
    observed_skills = set()
    observed_upstreams = set()
    family_counts = collections.Counter()
    bundle_counts = collections.Counter()
    skills_by_bundle = collections.defaultdict(set)
    upstreams_by_bundle = collections.defaultdict(set)

    for inst in instances:
        families = utils.family_order(list(instance_families(inst, label_family)))
        skills = utils.skill_keys(inst)
        upstream = utils.upstream_key(inst)
        observed_skills |= skills
        if upstream:
            observed_upstreams.add(upstream)
        for family in families:
            family_counts[family] += 1
        for size in range(min_size, max_size + 1):
            for bundle in itertools.combinations(families, size):
                bundle_counts[bundle] += 1
                skills_by_bundle[bundle] |= skills
                if upstream:
                    upstreams_by_bundle[bundle].add(upstream)

    n_skills = len(observed_skills)
    n_upstreams = len(observed_upstreams)
    rows = []
    for bundle, count in bundle_counts.items():
        prevalence = count / n if n else 0.0
        expected = 1.0
        for family in bundle:
            expected *= family_counts[family] / n if n else 0.0
        rows.append({
            "size": len(bundle),
            "bundle": " + ".join(bundle),
            "instances": count,
            "analyzed_instances": n,
            "branch_prevalence": prevalence,
            "skills_with_bundle": len(skills_by_bundle[bundle]),
            "observed_skills": n_skills,
            "skill_breadth": (
                len(skills_by_bundle[bundle]) / n_skills if n_skills else 0.0
            ),
            "upstreams_with_bundle": len(upstreams_by_bundle[bundle]),
            "observed_upstreams": n_upstreams,
            "upstream_coverage": (
                len(upstreams_by_bundle[bundle]) / n_upstreams
                if n_upstreams else 0.0
            ),
            "expected_prevalence": expected,
            "lift": prevalence / expected if expected else 0.0,
        })
    rows.sort(key=lambda r: (-r["branch_prevalence"], r["size"], r["bundle"]))
    for rank, row in enumerate(rows, start=1):
        row["rank"] = rank
    return rows


def pair_rows(instances: list[dict], label_family: dict[str, str],
              top_n: int | None = None) -> list[dict]:
    """Pairwise co-occurrence prevalence and lift among families.

    ``lift`` is the observed pair prevalence over its expected value under
    family independence (product of the two marginal prevalences); >1 means the
    pair co-occurs more than chance, <1 less than chance.

    With ``top_n`` set, restrict to the most frequent ``top_n`` families;
    with ``top_n=None`` (default) include every observed family so the full
    pairwise ranking is reported.
    """
    n = len(instances)
    family_counts = collections.Counter()
    family_sets = []
    for inst in instances:
        fams = instance_families(inst, label_family)
        family_sets.append(fams)
        for f in fams:
            family_counts[f] += 1
    top = [f for f, _ in family_counts.most_common(top_n)]
    top = utils.family_order(top)

    rows = []
    for a, b in itertools.combinations(top, 2):
        count = sum(1 for fams in family_sets if a in fams and b in fams)
        prevalence = count / n if n else 0.0
        expected = (family_counts[a] / n) * (family_counts[b] / n) if n else 0.0
        rows.append({
            "family_a": a,
            "family_b": b,
            "instances": count,
            "analyzed_instances": n,
            "branch_prevalence": prevalence,
            "lift": prevalence / expected if expected else 0.0,
        })
    rows.sort(key=lambda r: -r["branch_prevalence"])
    return rows


def plot_pair_heatmap(rows: list[dict], path: Path) -> None:
    """Render pairwise family lift as a lower-triangle heatmap.

    ``rows`` is the output of ``pair_rows``; each row's ``lift`` fills cell
    ``(family_b, family_a)``. The diagonal and upper triangle stay blank so each
    unordered pair appears once. Colour runs from the 1.0 independence baseline
    (warm) up to the strongest positive association (deep cool); pairs with
    lift < 1 (co-occurring less than chance) are shown in pale grey so the 1.0
    threshold reads clearly despite the sequential ramp.
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np
    from matplotlib.colors import LinearSegmentedColormap

    families = utils.family_order(
        list({r["family_a"] for r in rows} | {r["family_b"] for r in rows})
    )
    index = {family: i for i, family in enumerate(families)}
    matrix = np.full((len(families), len(families)), np.nan)
    for r in rows:
        matrix[index[r["family_b"]], index[r["family_a"]]] = r["lift"]

    # Sequential warm-cool ramp anchored at the lift=1.0 independence baseline:
    # vmin=1.0 so the ramp encodes positive association strength. NaN cells
    # (diagonal, upper triangle) stay white; lift < 1 falls below vmin and is
    # painted in the under-range colour (pale grey) to flag below-chance pairs.
    cmap = LinearSegmentedColormap.from_list(
        "rq3_family_pair", ["#FFE6B7", "#72BCD5", "#1E466E"]
    )
    cmap = cmap.with_extremes(bad="white", under="#E8E8E8")
    valid = matrix[~np.isnan(matrix)]
    vmax = max(float(valid.max()) if valid.size else 2.0, 2.0)

    fig, ax = plt.subplots(figsize=(3.45, 3.25), constrained_layout=True)
    im = ax.imshow(matrix, cmap=cmap, vmin=1.0, vmax=vmax, aspect="equal")

    ax.set_xticks(range(len(families)), families, rotation=45, ha="right",
                  fontsize=7)
    ax.set_yticks(range(len(families)), families, fontsize=7)
    ax.set_xticks([i - 0.5 for i in range(len(families) + 1)], minor=True)
    ax.set_yticks([i - 0.5 for i in range(len(families) + 1)], minor=True)
    ax.grid(which="minor", color="white", linewidth=1.0)
    ax.tick_params(which="minor", bottom=False, left=False)

    for i in range(len(families)):
        for j in range(len(families)):
            value = matrix[i, j]
            if np.isnan(value):
                continue
            scaled = (value - 1.0) / (vmax - 1.0) if vmax > 1.0 else 0.0
            color = "white" if scaled >= 0.65 else "#1E466E"
            ax.text(j, i, f"{value:.1f}", ha="center", va="center",
                    fontsize=5.5, color=color)

    cbar = fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04, extend="min")
    cbar.ax.tick_params(labelsize=7)
    cbar.ax.set_ylabel("Lift (obs / exp, 1.0 = independence)", rotation=90,
                       labelpad=8, fontsize=8)

    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path.with_suffix(".pdf"))
    fig.savefig(path.with_suffix(".png"), dpi=150)
    plt.close(fig)


def write_csv(rows: list[dict], fieldnames: list[str], path: Path) -> None:
    """Write rows to CSV, formatting fractional columns to 4 decimals."""
    floats = {"branch_prevalence", "skill_breadth", "upstream_coverage",
              "expected_prevalence", "lift"}
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
    parser.add_argument("--instances", type=Path, default=utils.DEFAULT_INSTANCES)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--top-family-count", type=int, default=None,
                        help="restrict pair table to the N most frequent "
                             "families; default reports all families")
    parser.add_argument("--num_samples", type=int, default=None,
                        help="limit to the first N instances for a dry run")
    args = parser.parse_args()

    instances = utils.load_instances(args.instances)
    if args.num_samples:
        instances = instances[: args.num_samples]
    label_family = utils.load_label_family_map()

    bundles = bundle_rows(instances, label_family)
    pairs = pair_rows(instances, label_family, args.top_family_count)
    write_csv(bundles, BUNDLE_FIELDNAMES, args.out_dir / "rq3-family-bundles.csv")
    write_csv(pairs, PAIR_FIELDNAMES,
              args.out_dir / "rq3-family-pair-bundles.csv")
    plot_pair_heatmap(pairs, args.out_dir / "rq3-family-pair-heatmap")

    logger.info("instances=%d bundles=%d pairs=%d",
                len(instances), len(bundles), len(pairs))
    logger.info("top bundles by prevalence:")
    for r in bundles[:8]:
        logger.info("  %-32s prevalence=%5.1f%% lift=%.2f",
                    r["bundle"], 100 * r["branch_prevalence"], r["lift"])
    logger.info("wrote rq3-family-bundles.csv, rq3-family-pair-bundles.csv, "
                "rq3-family-pair-heatmap.{png,pdf}")


if __name__ == "__main__":
    main()
