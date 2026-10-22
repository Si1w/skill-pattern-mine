"""Export measured repository candidates for human screening."""

import csv
import json
from pathlib import Path

import yaml

from src.storage import read_jsonl


def export_repository_review(root: Path) -> dict:
    """Project frozen measurements into CSV and YAML without inferring decisions.

    The YAML is a review worksheet. The names of repositories to retain are
    copied into the experiment configuration after review; the worksheet itself
    never implies a decision. Existing worksheets are protected because they
    may contain human notes.
    """
    targets = [root / "repository_candidates.csv", root / "repository_review.yaml"]
    if any(path.exists() for path in targets):
        raise ValueError("Review exports already exist; preserve completed decisions.")
    for name in (
        "run.json",
        "repositories.jsonl",
        "candidate_metadata.jsonl",
        "repository_summary.json",
        "search_coverage.json",
    ):
        if not (root / name).exists():
            raise ValueError(f"Repository collection has not produced {name}.")
    run = json.loads((root / "run.json").read_text())
    settings = run["config"]["screening"]
    confirmed = {name.lower() for name in settings["repositories"]}
    floor = settings["minimum_forks"]
    metadata = {
        row["metadata"]["id"]: row["metadata"]
        for row in read_jsonl(root / "candidate_metadata.jsonl")
    }
    rows, candidates = [], {}
    for snapshot in read_jsonl(root / "repositories.jsonl"):
        repository = snapshot["repository"]
        if repository["forks_count"] < floor:
            continue
        name = repository["full_name"]
        details = metadata[snapshot["github_id"]]
        counts = repository["skill_centricity"]
        row = {
            "repository": name,
            "url": details["html_url"],
            "forks": repository["forks_count"],
            "package_count": len(repository["skill_package_paths"]) if counts else None,
            "skill_files": counts["skill_files"] if counts else None,
            "tracked_files": counts["tracked_files"] if counts else None,
            "ratio": counts["ratio"] if counts else None,
            "tree_complete": snapshot["tree_complete"],
            "aggregator_keyword_hit": repository["aggregator_keyword_hit"],
            "channels": ", ".join(repository["channels"]),
            "excluded_by": repository["excluded_by"],
            "exclusion_note": repository["exclusion_note"],
            "description": details.get("description"),
        }
        rows.append(row)
        if snapshot["tree_complete"] and repository["skill_package_paths"]:
            candidates[name] = {
                **{key: value for key, value in row.items() if key != "repository"},
                "github_id": snapshot["github_id"],
                "retrieved_at": repository["retrieved_at"],
                "default_branch_sha": snapshot["default_branch_sha"],
                "package_path_examples": repository["skill_package_paths"][:5],
                "evidence": snapshot["evidence"],
                "confirmed": name.lower() in confirmed,
            }
    worksheet = {
        "run_id": root.name,
        "cutoff_utc": run["cutoff_utc"],
        "repository_snapshot_file": "repositories.jsonl",
        "instructions": (
            "Review repository purpose and package contents. Add the names of the repositories "
            "to retain under screening.repositories in the experiment YAML and record each "
            "exclusion with its reason in an ADR; an unlisted candidate stays pending. "
            "Exclude aggregators whose primary purpose is collecting skills from other repositories, "
            "whether linked or stored locally. Under ADR 0022, references, adaptations or "
            "accompanying imported skills do not alone disqualify a substantive skill workflow. "
            "Only the confirmed list defines the cohort; the package file ratio is descriptive evidence "
            "(ADR 0042). This worksheet is not an executable experiment configuration."
        ),
        "summary": json.loads((root / "repository_summary.json").read_text()),
        "search_coverage": json.loads((root / "search_coverage.json").read_text()),
        "minimum_forks": settings["minimum_forks"],
        "repositories": candidates,
    }
    with targets[0].open("w", newline="") as stream:
        if rows:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
    targets[1].write_text(
        yaml.safe_dump(worksheet, sort_keys=False, allow_unicode=True)
    )
    return {"measured_or_pending": len(rows), "review_candidates": len(candidates)}
