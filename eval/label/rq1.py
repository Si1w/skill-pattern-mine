"""RQ1: prevalence of modification families and patterns across fork instances.

Each instance (one fork's skill modification, keyed by ``modification_id``)
carries a flat ``labels`` list. Labels are the 46 patterns; each maps to one of
13 families via the pattern-labeling taxonomy. We report branch-level binary
incidence: an instance counts once toward a family/pattern if it carries at
least one matching label. Alongside raw prevalence we report sqrt-upstream
adjusted prevalence (to curb obra/superpowers dominance), skill breadth and
upstream coverage.

Reported as tables only: each family/pattern carries several metrics
(prevalence, adjusted prevalence, skill breadth, upstream coverage) that a
single bar chart cannot show, so the CSV is the primary artifact.

A focused breakdown isolates the ``modify-skill-metadata`` instances and reports
how many of them land on the SKILL.md frontmatter ``description:`` field (the
field that drives skill activation), versus other metadata fields only.

Outputs (eval/tables-and-figures/):
    rq1-families.csv, rq1-patterns.csv, rq1-metadata-description.csv

Usage:
    uv run python -m eval.label.rq1
    uv run python -m eval.label.rq1 --out-dir DIR
"""

import argparse
import csv
import logging
from pathlib import Path

from eval.label import utils

logger = logging.getLogger(__name__)
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

DEFAULT_OUT_DIR = utils.ROOT / "eval" / "tables-and-figures"

FAMILY_FIELDNAMES = [
    "family", "instances", "analyzed_instances", "prevalence",
    "adjusted_prevalence", "skills_with_family", "observed_skills",
    "skill_breadth", "upstreams_with_family", "observed_upstreams",
    "upstream_coverage",
]
PATTERN_FIELDNAMES = [
    "pattern", "instances", "analyzed_instances", "prevalence",
    "adjusted_prevalence", "skills_with_pattern", "observed_skills",
    "skill_breadth", "upstreams_with_pattern", "observed_upstreams",
    "upstream_coverage",
]
METADATA_LABEL = "modify-skill-metadata"
METADATA_DESC_FIELDNAMES = ["group", "instances", "share"]


def metadata_description_rows(instances: list[dict]) -> list[dict]:
    """Split ``modify-skill-metadata`` instances by whether they edit description.

    Among instances carrying the ``modify-skill-metadata`` label, count how many
    have at least one +/- line on a SKILL.md frontmatter ``description:`` field
    (including localised variants such as ``description_cn``) versus those that
    only touch other metadata fields. ``share`` is each group's fraction of the
    metadata instances.
    """
    meta = [i for i in instances if METADATA_LABEL in i.get("labels", [])]
    on_desc = 0
    for inst in meta:
        files = utils.split_patch(inst.get("patch", ""))
        if any(f["path"].split("/")[-1] == "SKILL.md"
               and utils.touches_frontmatter_field(f["diff"], "description")
               for f in files):
            on_desc += 1
    n = len(meta)
    return [
        {"group": "metadata_instances", "instances": n, "share": 1.0 if n else 0.0},
        {"group": "on_description", "instances": on_desc,
         "share": on_desc / n if n else 0.0},
        {"group": "other_fields_only", "instances": n - on_desc,
         "share": (n - on_desc) / n if n else 0.0},
    ]


def pattern_keys(instance: dict) -> set[str]:
    """Distinct pattern labels exhibited by an instance."""
    return set(instance.get("labels", []))


def family_keys_fn(label_family: dict[str, str]):
    """Build an item_keys function mapping an instance's labels to families."""

    def keys(instance: dict) -> set[str]:
        return {
            label_family[label]
            for label in instance.get("labels", [])
            if label in label_family
        }

    return keys


def summary_to_rows(summary: dict, key_name: str, with_word: str) -> list[dict]:
    """Flatten a prevalence summary into CSV rows sorted by prevalence."""
    rows = []
    for cat, m in summary.items():
        rows.append({
            key_name: cat,
            "instances": m["instances"],
            "analyzed_instances": m["analyzed_instances"],
            "prevalence": m["prevalence"],
            "adjusted_prevalence": m["adjusted_prevalence"],
            f"skills_with_{with_word}": m["skills_with"],
            "observed_skills": m["observed_skills"],
            "skill_breadth": m["skill_breadth"],
            f"upstreams_with_{with_word}": m["upstreams_with"],
            "observed_upstreams": m["observed_upstreams"],
            "upstream_coverage": m["upstream_coverage"],
        })
    rows.sort(key=lambda r: (-r["prevalence"], r[key_name]))
    return rows


def write_csv(rows: list[dict], fieldnames: list[str], path: Path) -> None:
    """Write rows to CSV, formatting fractional columns to 4 decimals."""
    floats = {"prevalence", "adjusted_prevalence", "skill_breadth",
              "upstream_coverage", "share"}
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
    parser.add_argument("--num_samples", type=int, default=None,
                        help="limit to the first N instances for a dry run")
    args = parser.parse_args()

    instances = utils.load_instances(args.instances)
    if args.num_samples:
        instances = instances[: args.num_samples]
    label_family = utils.load_label_family_map()
    sizes = utils.upstream_sizes(instances)

    family_summary = utils.prevalence_summary(
        instances, family_keys_fn(label_family), sizes
    )
    pattern_summary = utils.prevalence_summary(instances, pattern_keys, sizes)

    family_rows = summary_to_rows(family_summary, "family", "family")
    pattern_rows = summary_to_rows(pattern_summary, "pattern", "pattern")

    meta_desc_rows = metadata_description_rows(instances)

    write_csv(family_rows, FAMILY_FIELDNAMES, args.out_dir / "rq1-families.csv")
    write_csv(pattern_rows, PATTERN_FIELDNAMES, args.out_dir / "rq1-patterns.csv")
    write_csv(meta_desc_rows, METADATA_DESC_FIELDNAMES,
              args.out_dir / "rq1-metadata-description.csv")

    logger.info("instances=%d families=%d patterns=%d",
                len(instances), len(family_rows), len(pattern_rows))
    for r in family_rows:
        logger.info("  family %-13s prevalence=%5.1f%% adj=%5.1f%% upstream-cov=%.2f",
                    r["family"], 100 * r["prevalence"],
                    100 * r["adjusted_prevalence"], r["upstream_coverage"])
    meta = {r["group"]: r for r in meta_desc_rows}
    logger.info("metadata instances=%d on-description=%d (%.1f%%) other-only=%d",
                meta["metadata_instances"]["instances"],
                meta["on_description"]["instances"],
                100 * meta["on_description"]["share"],
                meta["other_fields_only"]["instances"])
    logger.info("wrote rq1-families.csv, rq1-patterns.csv, "
                "rq1-metadata-description.csv")


if __name__ == "__main__":
    main()
