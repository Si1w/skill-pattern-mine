"""Building blocks for label-input instance construction.

Loads the cleaned diffs from the mining stage
(``data/mine/diff_cleaned.jsonl``), derives per-row features, and writes
self-contained label-input JSON files under ``data/label/inputs/`` that the
labelling skill consumes directly.

Both the pilot sampler (``label.sample_pilot``) and the full-sweep builder
(``label.build_full``) reuse this module — they only differ in how they choose
which ``(candidate, diff_row)`` pairs to write.

The input is already scoped and cleaned by the mining stage:
``mine.s05_filter_in_skill`` drops add/remove-skill files, non-skill files,
binaries, and upstream-sync rows; ``mine.s06_clean`` then reduces commits to
skill-relevant intent and deduplicates redundant branches. So commits here are
already clean — this module only derives features.
"""

import json
import logging
import re
from pathlib import Path

from common import classify
from mine.utils import DATA_DIR as MINE_DATA_DIR

logger = logging.getLogger(__name__)

DIFF_CLEANED_PATH = MINE_DATA_DIR / "diff_cleaned.jsonl"
INPUTS_DIR = Path("data/label/inputs")

SLUG_RE = re.compile(r"[^a-zA-Z0-9._-]+")


def repo_slug(repo_name: str) -> str:
    return repo_name.replace("/", "-")


def slugify(value: str) -> str:
    return SLUG_RE.sub("-", value).strip("-") or "x"


def instance_stem(upstream: str, fork_owner: str, fork_branch: str) -> str:
    """Filename stem used for both label input and label output."""
    return f"{repo_slug(upstream)}--{slugify(fork_owner)}--{slugify(fork_branch)}"


def modification_id(row: dict) -> str:
    return f"{row['upstream']}::{row['fork_owner']}::{row.get('fork_branch', '')}"


def has_merge_commit(commits: list[dict]) -> bool:
    return any((classify(c.get("message", "")) or "").startswith("merge") for c in commits)


def candidate_from_row(row: dict) -> dict:
    """Compute sampling features for one cleaned diff row.

    Files are already skill-scoped and commits already cleaned by the mining
    stage (``mine.s05_filter_in_skill`` + ``mine.s06_clean``), so every file and
    commit here is skill-relevant.
    """
    commits = row.get("commits", [])
    files = row.get("files", [])
    statuses = [f.get("status") for f in files]
    skill_md_files = [
        f for f in files
        if Path(f.get("filename", "")).name.upper() == "SKILL.MD"
    ]

    return {
        "modification_id": modification_id(row),
        "upstream": row["upstream"],
        "fork_owner": row["fork_owner"],
        "fork_branch": row.get("fork_branch", ""),
        "head_sha": row.get("head_sha"),
        "commit_count": len(commits),
        "has_merge_commit": has_merge_commit(commits),
        "file_count": len(files),
        "skill_md_file_count": len(skill_md_files),
        "added_files": sum(s == "added" for s in statuses),
        "removed_files": sum(s == "removed" for s in statuses),
        "renamed_files": sum(s == "renamed" for s in statuses),
        "total_additions": sum(f.get("additions", 0) for f in files),
        "total_deletions": sum(f.get("deletions", 0) for f in files),
        "skill_patch_chars": sum(len(f.get("patch") or "") for f in files),
    }


def load_candidates() -> list[tuple[dict, dict]]:
    """Return ``(candidate_metadata, diff_row)`` for every in-skill row.

    Deduplicates by ``modification_id`` (``upstream::owner::branch``); keep the
    first occurrence.
    """
    pairs: list[tuple[dict, dict]] = []
    seen_ids: set[str] = set()
    duplicates = 0
    if not DIFF_CLEANED_PATH.exists():
        logger.warning("missing %s — run mine.s06_clean first",
                       DIFF_CLEANED_PATH)
        return pairs
    with DIFF_CLEANED_PATH.open() as f:
        for line in f:
            if not line.strip():
                continue
            row = json.loads(line)
            candidate = candidate_from_row(row)
            if candidate["modification_id"] in seen_ids:
                duplicates += 1
                continue
            seen_ids.add(candidate["modification_id"])
            pairs.append((candidate, row))
    if duplicates:
        logger.info("skipped %d duplicate diff rows", duplicates)
    return pairs


def build_instance(candidate: dict, row: dict) -> dict:
    """Assemble a label-input instance from a selected (candidate, diff_row).

    ``candidate`` must carry a ``sample_stratum`` key indicating how it was
    selected (e.g. ``"repo:owner/name"``, ``"edge-case"``, or ``"full"``).
    """
    return {
        "modification_id": candidate["modification_id"],
        "upstream": candidate["upstream"],
        "fork_owner": candidate["fork_owner"],
        "fork_branch": candidate["fork_branch"],
        "head_sha": candidate["head_sha"],
        "commits": [
            {"sha": c.get("sha"), "message": c.get("message", "")}
            for c in row.get("commits", [])
        ],
        "files": [
            {
                "filename": f.get("filename"),
                "previous_filename": f.get("previous_filename"),
                "status": f.get("status"),
                "additions": f.get("additions", 0),
                "deletions": f.get("deletions", 0),
                "patch": f.get("patch", ""),
            }
            for f in row.get("files", [])
        ],
        "input_context": {
            "sample_stratum": candidate["sample_stratum"],
            "raw_commit_count": candidate["commit_count"],
            "raw_file_count": candidate["file_count"],
            "skill_md_file_count": candidate["skill_md_file_count"],
        },
    }


def write_instances(
    pairs: list[tuple[dict, dict]],
    out_dir: str | Path | None = None,
) -> Path:
    """Write one label-input JSON per ``(candidate, row)`` pair.

    Each candidate must already carry a ``sample_stratum`` tag.
    """
    target = Path(out_dir) if out_dir else INPUTS_DIR
    target.mkdir(parents=True, exist_ok=True)
    for candidate, row in pairs:
        instance = build_instance(candidate, row)
        stem = instance_stem(instance["upstream"], instance["fork_owner"],
                             instance["fork_branch"])
        with (target / f"{stem}.json").open("w") as f:
            json.dump(instance, f, indent=2, ensure_ascii=False)
    logger.info("wrote %d label inputs to %s", len(pairs), target)
    return target
