"""RQ2: which physical skill surfaces do fork modifications touch?

Each instance's unified-diff ``patch`` lists the changed files. Every file is
attributed to its skill root (the directory holding SKILL.md) and made relative
to it, then classified into a physical surface: the core SKILL.md, root
companion files (README/LICENSE/AGENTS), scripts, references, assets,
configuration, examples, or catch-all additional files/directories. A branch
counts once per surface. Metrics match RQ1: branch prevalence, sqrt-upstream
adjusted prevalence, skill breadth and upstream coverage.

A second table reports prevalence of specific root companion files carried over
from upstream skill bundles (reviewer prompts, best-practice docs, AGENTS.md).

Reported as tables only (multiple metrics per surface).

Outputs (eval/tables-and-figures/):
    rq2-surfaces.csv, rq2-root-companion-files.csv

Usage:
    uv run python -m eval.label.rq2
    uv run python -m eval.label.rq2 --out-dir DIR
"""

import argparse
import csv
import logging
from pathlib import PurePosixPath, Path

from eval.label import utils

logger = logging.getLogger(__name__)
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

DEFAULT_OUT_DIR = utils.ROOT / "eval" / "tables-and-figures"

SURFACE_ORDER = [
    "SKILL.md", "README.md", "LICENSE.txt", "AGENTS.md", "agents/", "scripts",
    "references", "assets", "configuration", "examples", "additional files",
    "additional directories",
]
SURFACE_FIELDNAMES = [
    "surface", "branches_with_surface", "analyzed_branches", "prevalence",
    "adjusted_prevalence", "skills_with_surface", "observed_skills",
    "skill_breadth", "upstreams_with_surface", "observed_upstreams",
    "upstream_coverage",
]
ROOT_COMPANION_FILES = [
    "visual-companion.md", "spec-document-reviewer-prompt.md",
    "plan-document-reviewer-prompt.md", "code-quality-reviewer-prompt.md",
    "implementer-prompt.md", "anthropic-best-practices.md", "AGENTS.md",
]
ROOT_COMPANION_FIELDNAMES = [
    "file", "branches_with_file", "analyzed_branches", "prevalence",
    "upstreams_with_file", "observed_upstreams", "upstream_coverage",
]

# Surface classification name sets, ported verbatim from the legacy RQ2.
SCRIPT_DIRS = {"bin", "script", "scripts", "tool", "tools"}
REFERENCE_DIRS = {"docs", "documentation", "knowledge", "reference",
                  "references", "rules"}
ASSET_DIRS = {"asset", "assets", "canvas-fonts", "fonts", "images", "media",
              "public", "resource", "resources", "static", "template",
              "templates", "theme-factory", "themes"}
CONFIG_DIRS = {".github", "config", "configs", "hooks"}
EXAMPLE_DIRS = {"demo", "demos", "evals", "example", "examples", "sample",
                "samples", "test", "tests"}
SCRIPT_SUFFIXES = {".cjs", ".go", ".js", ".jsx", ".mjs", ".py", ".rb", ".sh",
                   ".ts", ".tsx"}
ASSET_SUFFIXES = {".avif", ".css", ".gif", ".jpeg", ".jpg", ".otf", ".png",
                  ".svg", ".ttf", ".webp", ".woff", ".woff2"}
CONFIG_NAMES = {".gitignore", "config.json", "metadata.json",
                "package-lock.json", "package.json", "pyproject.toml",
                "requirements.txt", "uv.lock"}
CONFIG_SUFFIXES = {".json", ".toml", ".yaml", ".yml"}


def root_file_surface(name: str) -> str | None:
    """Surface for a root-level file inside a skill, if it has a known role."""
    lower = name.lower()
    suffix = PurePosixPath(lower).suffix
    if lower == "skill.md":
        return "SKILL.md"
    if lower == "readme.md":
        return "README.md"
    if lower == "license.txt":
        return "LICENSE.txt"
    if lower == "agents.md":
        return "AGENTS.md"
    if lower in CONFIG_NAMES or suffix in CONFIG_SUFFIXES:
        return "configuration"
    if "example" in lower or lower.startswith(("demo", "sample", "test-")):
        return "examples"
    if "reference" in lower:
        return "references"
    if suffix in ASSET_SUFFIXES:
        return "assets"
    if suffix in SCRIPT_SUFFIXES:
        return "scripts"
    return None


def directory_surface(directory: str) -> str | None:
    """Surface for a top-level directory inside a skill, if recognised."""
    lower = directory.lower()
    if lower == "agents":
        return "agents/"
    if lower in SCRIPT_DIRS:
        return "scripts"
    if lower in REFERENCE_DIRS:
        return "references"
    if lower in ASSET_DIRS:
        return "assets"
    if lower in CONFIG_DIRS:
        return "configuration"
    if lower in EXAMPLE_DIRS:
        return "examples"
    return None


def path_surface(relative: str) -> str:
    """Classify a skill-relative file path into a physical surface."""
    parts = PurePosixPath(relative).parts
    if not parts or relative in ("", "."):
        return "additional files"
    if parts[-1].lower() == "skill.md":
        return "SKILL.md"
    if len(parts) == 1:
        return root_file_surface(parts[0]) or "additional files"
    surface = directory_surface(parts[0])
    if surface:
        return surface
    if len(parts) > 2:
        surface = directory_surface(parts[1])
        if surface:
            return surface
    return "additional directories"


def surface_keys(instance: dict) -> set[str]:
    """Distinct surfaces an instance touches."""
    return {
        path_surface(rel)
        for _, rel in utils.file_skill_relative(instance.get("patch", ""))
    }


def companion_keys(instance: dict) -> set[str]:
    """Tracked root-companion files an instance adds or edits."""
    found = set()
    for _, rel in utils.file_skill_relative(instance.get("patch", "")):
        name = PurePosixPath(rel).name
        if name in ROOT_COMPANION_FILES:
            found.add(name)
    return found


def surface_rows(summary: dict) -> list[dict]:
    """Flatten the surface summary into ordered CSV rows."""
    rank = {s: i for i, s in enumerate(SURFACE_ORDER)}
    rows = []
    for surface, m in summary.items():
        rows.append({
            "surface": surface,
            "branches_with_surface": m["instances"],
            "analyzed_branches": m["analyzed_instances"],
            "prevalence": m["prevalence"],
            "adjusted_prevalence": m["adjusted_prevalence"],
            "skills_with_surface": m["skills_with"],
            "observed_skills": m["observed_skills"],
            "skill_breadth": m["skill_breadth"],
            "upstreams_with_surface": m["upstreams_with"],
            "observed_upstreams": m["observed_upstreams"],
            "upstream_coverage": m["upstream_coverage"],
        })
    rows.sort(key=lambda r: (rank.get(r["surface"], len(rank)), -r["prevalence"]))
    return rows


def companion_rows(summary: dict) -> list[dict]:
    """Flatten the companion-file summary into CSV rows sorted by prevalence."""
    rows = []
    for name, m in summary.items():
        rows.append({
            "file": name,
            "branches_with_file": m["instances"],
            "analyzed_branches": m["analyzed_instances"],
            "prevalence": m["prevalence"],
            "upstreams_with_file": m["upstreams_with"],
            "observed_upstreams": m["observed_upstreams"],
            "upstream_coverage": m["upstream_coverage"],
        })
    rows.sort(key=lambda r: (-r["prevalence"], r["file"]))
    return rows


def write_csv(rows: list[dict], fieldnames: list[str], path: Path) -> None:
    """Write rows to CSV, formatting fractional columns to 4 decimals."""
    floats = {"prevalence", "adjusted_prevalence", "skill_breadth",
              "upstream_coverage"}
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
    sizes = utils.upstream_sizes(instances)

    surface_summary = utils.prevalence_summary(instances, surface_keys, sizes)
    companion_summary = utils.prevalence_summary(instances, companion_keys, sizes)

    s_rows = surface_rows(surface_summary)
    c_rows = companion_rows(companion_summary)
    write_csv(s_rows, SURFACE_FIELDNAMES, args.out_dir / "rq2-surfaces.csv")
    write_csv(c_rows, ROOT_COMPANION_FIELDNAMES,
              args.out_dir / "rq2-root-companion-files.csv")

    logger.info("instances=%d surfaces=%d companion-files=%d",
                len(instances), len(s_rows), len(c_rows))
    for r in s_rows:
        logger.info("  surface %-22s prevalence=%5.1f%% adj=%5.1f%% breadth=%.2f",
                    r["surface"], 100 * r["prevalence"],
                    100 * r["adjusted_prevalence"], r["skill_breadth"])
    logger.info("wrote rq2-surfaces.csv, rq2-root-companion-files.csv")


if __name__ == "__main__":
    main()
