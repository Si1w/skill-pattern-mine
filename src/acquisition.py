"""Freeze run settings and validate repository and fork acquisition artifacts."""

import hashlib
import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path

from src.config import ExperimentSettings, load_saved_config
from src.domain import Fork, ForkComparison, ForkExclusion, ForkSkip, RepositorySnapshot, TreeEntry
from src.github import no_common_ancestor, read_jsonl, utcnow, write_json, write_jsonl
from src.preprocess import measure_skill_centricity
from src.retrieve import screen_repository


def prepare_run(
    root: Path,
    config: ExperimentSettings,
    *,
    pilot: bool | None,
    limit: int | None,
    offline: bool,
    source_run_id: str | None = None,
    recovery_run_id: str | None = None,
) -> dict:
    """Freeze the cutoff and sample bounds once, rejecting incompatible resumes."""
    path = root / "run.json"
    settings = config.model_dump(mode="json")
    if path.exists():
        run = json.loads(path.read_text())
        if (
            load_saved_config(run["config"]).model_dump(mode="json")
            != settings
        ):
            raise ValueError(
                "Configuration changed. Use the original config or a new run ID."
            )
        if pilot is not None and run["pilot"] != pilot:
            raise ValueError("Pilot mode cannot change within a run.")
        if limit is not None and run["num_samples"] != limit:
            raise ValueError("Sample bounds cannot change within a run.")
        if source_run_id is not None and source_run_id != run.get("source_run_id"):
            raise ValueError("Source run cannot change within a run.")
        if recovery_run_id is not None and recovery_run_id != run.get("recovery_run_id"):
            raise ValueError("Recovery source cannot change within a run.")
        return run
    if offline:
        raise ValueError("Offline replay requires an existing run.")
    if limit is not None and limit < 1:
        raise ValueError("--num_samples must be positive.")
    now = datetime.now(timezone.utc)
    cutoff = min(
        now, config.observation.end_exclusive_cap, config.observation.cutoff_utc or now
    ).astimezone(timezone.utc)
    if recovery_run_id:
        if recovery_run_id == root.name:
            raise ValueError("Recovery needs a new run ID.")
        previous = json.loads((root.parent / recovery_run_id / "run.json").read_text())
        original = load_saved_config(previous["config"]).model_dump(mode="json")
        original["retrieval"]["fork_sort"] = settings["retrieval"]["fork_sort"]
        if original != settings:
            raise ValueError("Recovery may change only fork ordering, not research settings.")
        if (pilot is not None and bool(pilot) != previous["pilot"]) or (
            limit is not None and limit != previous["num_samples"]
        ):
            raise ValueError("Recovery must preserve pilot mode and sample bounds.")
        if source_run_id is not None and source_run_id != previous.get("source_run_id"):
            raise ValueError("Recovery must preserve the upstream source run.")
        pilot, limit = previous["pilot"], previous["num_samples"]
        source_run_id = previous.get("source_run_id")
        cutoff = datetime.fromisoformat(previous["cutoff_utc"])
    if pilot and limit is None:
        raise ValueError("An engineering pilot requires --num_samples.")
    run = {
        "schema_version": 1,
        "created_at": now.isoformat(),
        "cutoff_utc": cutoff.isoformat(),
        "partial_final_month": cutoff.day != 1
        or any([cutoff.hour, cutoff.minute, cutoff.second, cutoff.microsecond]),
        "pilot": bool(pilot),
        "num_samples": limit,
        "config": settings,
        "source_run_id": source_run_id,
        "recovery_run_id": recovery_run_id,
        "scope": "Repository screening and frozen fork divergence; no monthly observations or labels.",
    }
    project = Path(__file__).resolve().parents[1]
    files = [project / "pyproject.toml", project / "uv.lock"]
    for folder, pattern in (("src", "*.py"), ("eval", "*.py"), ("configs", "*.yaml")):
        files.extend(sorted((project / folder).rglob(pattern)))
    for source in files:
        relative = source.relative_to(project)
        destination = root / "source" / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
    run["provenance"] = {
        "run_id": root.name,
        "source_directory": "source",
    }
    write_json(path, run)
    return run


def import_recovery_cache(source: Path, root: Path) -> dict:
    """Preserve cached responses; retain listings only under the same creation order."""
    run = json.loads((root / "run.json").read_text())
    previous = json.loads((source / "run.json").read_text())
    if root.resolve() == source.resolve() or run.get("recovery_run_id") != source.name:
        raise ValueError("Recovery source does not match the frozen run.")
    if run["cutoff_utc"] != previous["cutoff_utc"]:
        raise ValueError("Recovery must preserve the observation cutoff.")
    manifest = root / "cache_import.json"
    if manifest.exists():
        return json.loads(manifest.read_text())
    version = run["config"]["github"]["api_version"]
    upstreams = {
        str(item["github_id"]): item["repository"]["full_name"]
        for item in read_jsonl(source / "repositories.jsonl")
    }
    known = {name: {} for name in upstreams.values()}
    inventory = source / "recovery_inventory.json"
    if inventory.exists():
        for name, rows in json.loads(inventory.read_text()).items():
            if name in known:
                known[name].update({row["id"]: row for row in rows})
    reuse_listings = (
        previous["config"]["retrieval"]["fork_sort"]
        == run["config"]["retrieval"]["fork_sort"] == "oldest"
    )
    imported, listing_pages, metadata_endpoints = 0, 0, {}
    (root / "raw").mkdir(parents=True, exist_ok=True)
    for path in sorted((source / "raw").glob("*.json")):
        data = path.read_bytes()
        saved = json.loads(data)
        endpoint = saved["endpoint"]
        digest = hashlib.sha256(f"{version}:{endpoint}".encode()).hexdigest()
        if saved["api_version"] != version or path.name != f"{digest}.json":
            raise ValueError(f"Invalid recovery request identity: {path.name}")
        listing = re.fullmatch(r"(?:repos/([^/]+/[^/]+)|repositories/(\d+))/forks\?.*", endpoint)
        if listing and saved["status"] == 200:
            name = listing[1] or upstreams.get(listing[2])
            if name in known:
                for row in saved["body"]:
                    known[name][row["id"]] = {"id": row["id"], "full_name": row["full_name"]}
            if not reuse_listings:
                continue
        reusable = re.fullmatch(
            r"(?:repos/[^/]+/[^/]+|repositories/\d+)(?:/branches/[^?]+|/compare/[0-9a-f]{40}\.\.\.[0-9a-f]{40}\?.*)?",
            endpoint,
        )
        if not (reusable or (listing and reuse_listings)) or saved["status"] not in {200, 404}:
            continue
        destination = root / "raw" / path.name
        if destination.exists() and destination.read_bytes() != data:
            raise ValueError(f"Recovery would overwrite frozen evidence: {path.name}")
        if not destination.exists():
            shutil.copyfile(path, destination)
        imported += 1
        listing_pages += bool(listing)
        if re.fullmatch(r"repos/[^/]+/[^/]+|repositories/\d+", endpoint) and saved["status"] == 200:
            metadata_endpoints[saved["body"]["id"]] = endpoint
    write_json(root / "recovery_inventory.json", {
        name: [
            {**row, "metadata_endpoint": metadata_endpoints.get(row["id"], row.get("metadata_endpoint"))}
            for row in sorted(rows.values(), key=lambda row: row["id"])
        ] for name, rows in known.items()
    })
    report = {
        "source_run_id": source.name, "imported_at": utcnow(),
        "responses": imported, "listing_pages": listing_pages,
        "known_forks": {name: len(rows) for name, rows in known.items()},
    }
    write_json(manifest, report)
    return report


def import_confirmed_repositories(
    source: Path, root: Path, config: ExperimentSettings
) -> None:
    """Reuse approved frozen upstream evidence without mutating the candidate run."""
    if source.resolve() == root.resolve():
        raise ValueError("Source and destination runs must differ.")
    if config.screening.selection_mode != "confirmed_reviews":
        raise ValueError("Import requires confirmed_reviews selection.")
    approved = {
        name.lower() for name, review in config.screening.reviews.items()
        if not review.exclude and not review.is_aggregator
    }
    if not approved:
        raise ValueError("No approved repositories in the configuration.")
    snapshots = [
        RepositorySnapshot.model_validate(row)
        for row in read_jsonl(source / "repositories.jsonl")
    ]
    names = [item.repository.full_name.lower() for item in snapshots]
    ids = [item.github_id for item in snapshots]
    if len(set(names)) != len(names) or len(set(ids)) != len(ids):
        raise ValueError("Duplicate repository identity in source evidence.")
    if approved - set(names):
        raise ValueError(f"Missing approved repositories: {sorted(approved - set(names))}")
    selected = [item for item in snapshots if item.repository.full_name.lower() in approved]
    for item in selected:
        tree_file = f"trees/{item.github_id}.jsonl"
        entries = [TreeEntry.model_validate(row) for row in read_jsonl(source / tree_file)]
        if (
            not item.tree_complete or not item.tree_sha
            or not re.fullmatch(r"[0-9a-f]{40}", item.default_branch_sha or "")
            or not (source / tree_file).exists()
            or measure_skill_centricity(entries, complete=True) != item.repository.skill_centricity
        ):
            raise ValueError(f"Incomplete or inconsistent frozen evidence: {item.repository.full_name}")
        item.repository = screen_repository(item.repository, entries, config.screening)
        if item.repository.excluded_by is not None or not item.repository.screening_complete:
            raise ValueError(f"Approved repository failed structural checks: {item.repository.full_name}")
    provenance = {
        "source_run_id": source.name,
        "selection_mode": "confirmed_reviews",
        "approved_repositories": sorted(approved),
    }
    manifest = root / "repository_selection.json"
    if manifest.exists():
        saved = json.loads(manifest.read_text())
        if (
            any(saved.get(key) != value for key, value in provenance.items())
            or read_jsonl(root / "repositories.jsonl") != [item.model_dump(mode="json") for item in selected]
            or any(
                read_jsonl(root / f"trees/{item.github_id}.jsonl")
                != read_jsonl(source / f"trees/{item.github_id}.jsonl")
                for item in selected
            )
        ):
            raise ValueError("Source evidence changed; use a new run ID.")
    write_json(manifest, provenance)
    (root / "trees").mkdir(parents=True, exist_ok=True)
    for item in selected:
        name = f"trees/{item.github_id}.jsonl"
        shutil.copyfile(source / name, root / name)
    coverage = json.loads((source / "search_coverage.json").read_text())
    write_json(root / "search_coverage.json", coverage)
    selected_ids = {item.github_id for item in selected}
    write_jsonl(root / "candidate_metadata.jsonl", [
        row for row in read_jsonl(source / "candidate_metadata.jsonl")
        if row["metadata"]["id"] in selected_ids
    ])
    write_jsonl(root / "repositories.jsonl", selected)
    write_jsonl(root / "repository_errors.jsonl", [])
    write_json(root / "repository_summary.json", {
        "selection_mode": "confirmed_reviews", "source_run_id": source.name,
        "processed": len(selected), "trees_complete": len(selected),
        "retained": len(selected), "pending": 0, "excluded": {}, "errors": 0,
        "complete": True,
        "source_search_complete": all(item["complete"] for item in coverage),
    })


def verify_run(root: Path) -> dict:
    """Validate saved acquisition outputs without making network requests."""
    run = json.loads((root / "run.json").read_text())
    config = load_saved_config(run["config"])
    confirmed = config.screening.selection_mode == "confirmed_reviews"
    repositories = [
        RepositorySnapshot.model_validate(row)
        for row in read_jsonl(root / "repositories.jsonl")
    ]
    comparisons = [
        ForkComparison.model_validate(row)
        for row in read_jsonl(root / "comparisons.jsonl")
    ]
    exclusions = [ForkExclusion.model_validate(row) for row in read_jsonl(root / "fork_exclusions.jsonl")]
    skips = [ForkSkip.model_validate(row) for row in read_jsonl(root / "fork_skips.jsonl")]
    outcomes = [*comparisons, *exclusions]
    frozen_skips = [item for item in skips if item.default_branch_sha is not None]
    frozen = read_jsonl(root / "forks.jsonl")
    frozen_pairs = {(row["upstream"], row["github_id"]) for row in frozen}
    evidence_checks = []
    for item in exclusions:
        digest = hashlib.sha256(f"{config.github.api_version}:{item.endpoint}".encode()).hexdigest()
        path = root / "raw" / f"{digest}.json"
        saved = json.loads(path.read_text()) if path.exists() else {}
        evidence_checks.append(
            saved.get("status") == item.status
            and saved.get("endpoint") == item.endpoint
            and saved.get("api_version") == config.github.api_version
            and saved.get("retrieved_at") == item.retrieved_at.isoformat()
            and saved.get("body", {}).get("message") == item.message
            and f"/compare/{item.upstream_sha}...{item.fork.default_branch_sha}?" in item.endpoint
            and no_common_ancestor(item.endpoint, saved.get("body"))
        )
    errors = read_jsonl(root / "repository_errors.jsonl") + read_jsonl(
        root / "fork_errors.jsonl"
    )
    coverage = (
        json.loads((root / "search_coverage.json").read_text())
        if (root / "search_coverage.json").exists()
        else []
    )
    upstreams = {item.repository.full_name: item for item in repositories}
    expected = {
        name
        for name, item in upstreams.items()
        if item.tree_complete
        and item.repository.excluded_by is None
        and (item.repository.screening_complete or run["pilot"])
    }
    observed = {item.fork.upstream for item in outcomes} | {item.upstream for item in skips}
    measured = [item for item in repositories if item.tree_complete]
    summaries = [
        json.loads((root / name).read_text()) if (root / name).exists() else {}
        for name in ["repository_summary.json", "fork_summary.json"]
    ]
    comparison_sources = {(item.fork.upstream, item.fork.full_name): item for item in comparisons}
    reuse_checks = []
    for item in comparisons:
        if item.reused_from is None:
            continue
        source = comparison_sources.get((item.fork.upstream, item.reused_from))
        reuse_checks.append(
            source is not None and source.reused_from is None and source.commits_complete
            and source.fork.default_branch_sha == item.fork.default_branch_sha
            and source.model_dump(exclude={"fork", "github_id", "reused_from"})
            == item.model_dump(exclude={"fork", "github_id", "reused_from"})
        )
    outcome_pairs = {(item.fork.upstream, item.github_id) for item in outcomes}
    skip_pairs = {(item.upstream, item.github_id) for item in skips}
    frozen_skip_pairs = {(item.upstream, item.github_id) for item in frozen_skips}
    tree_checks = []
    for item in measured:
        path = root / "trees" / f"{item.github_id}.jsonl"
        entries = [TreeEntry.model_validate(row) for row in read_jsonl(path)]
        tree_checks.append(
            path.exists()
            and measure_skill_centricity(entries, complete=True)
            == item.repository.skill_centricity
        )
    checks = {
        "both_discovery_channels_recorded": {
            row["channel"] for row in coverage if row["stop_reason"] != "error"
        }
        == {"intent", "manifest"},
        "repositories_measured": bool(measured),
        "both_stages_finished": all(bool(item) for item in summaries)
        and summaries[1].get("upstreams_processed") == summaries[1].get("upstreams"),
        "tree_measurements_reproduce": bool(tree_checks) and all(tree_checks),
        "eligible_upstreams_compared": bool(expected) and observed == expected,
        "forks_processed": bool(outcomes or skips),
        "exclusion_evidence_matches": all(evidence_checks),
        "reused_comparisons_match": all(reuse_checks),
        "skips_accounted_for": len(skip_pairs) == len(skips)
        and not (skip_pairs & outcome_pairs)
        and summaries[1].get("skipped_forks", 0) == len(skips)
        and all(item.upstream in expected for item in skips)
        and all(
            item.default_branch_sha is None or any(
                row["upstream"] == item.upstream and row["github_id"] == item.github_id
                and row["default_branch_sha"] == item.default_branch_sha
                for row in frozen
            ) for item in skips
        ),
        "all_frozen_forks_accounted_for": len(frozen) == len(frozen_pairs) == len(outcomes) + len(frozen_skips)
        and frozen_pairs == outcome_pairs | frozen_skip_pairs,
        "no_acquisition_errors": not errors,
        "unique_repository_ids": len(upstreams)
        == len(repositories)
        == len({item.github_id for item in repositories}),
        "unique_forks_per_upstream": len(outcomes)
        == len({(item.fork.upstream, item.github_id) for item in outcomes}),
        "frozen_references_match": all(
            item.fork.upstream in upstreams
            and upstreams[item.fork.upstream].default_branch_sha == item.upstream_sha
            and re.fullmatch(r"[0-9a-f]{40}", item.fork.default_branch_sha)
            for item in outcomes
        ),
        "commit_counts_consistent": all(
            len(item.commits) == item.ahead_by
            if item.commits_complete
            else len(item.commits) <= item.ahead_by
            for item in comparisons
        ),
        "sample_bounds_respected": run["num_samples"] is None
        or (
            (confirmed or len(repositories) <= run["num_samples"])
            and all(
                sum(item.fork.upstream == name for item in outcomes)
                + sum(item.upstream == name and item.stage != "fork_reconciliation" for item in skips)
                <= run["num_samples"]
                for name in observed
            )
            and all(len(item.commits) <= run["num_samples"] for item in comparisons)
        ),
    }
    if confirmed:
        approved = {
            name.lower() for name, review in config.screening.reviews.items()
            if not review.exclude and not review.is_aggregator
        }
        checks["confirmed_membership_matches"] = bool(approved) and approved == {
            item.repository.full_name.lower() for item in measured
            if item.repository.screening_complete and item.repository.excluded_by is None
        } == {item.repository.full_name.lower() for item in repositories}
    coverage_complete = all(item.get("complete", False) for item in summaries)
    fork_coverage = json.loads((root / "fork_coverage.json").read_text()) if (root / "fork_coverage.json").exists() else []
    checks["fork_inventory_consistent"] = bool(fork_coverage) and all(
        not item.get("duplicate_rows", 0)
        and not item.get("creation_time_inversions", 0)
        and set(item.get("missing_previous_ids", [])) <= {
            skip.github_id for skip in skips
            if skip.upstream == item["upstream"] and skip.stage == "fork_reconciliation"
        }
        for item in fork_coverage
    )
    if not run["pilot"]:
        checks["enumeration_complete"] = coverage_complete and bool(fork_coverage) and all(
            item.get("complete", False) for item in fork_coverage
        )
        checks["screening_complete"] = all(
            item.repository.screening_complete for item in repositories
        )
    report = {
        "status": "passed" if all(checks.values()) else "failed",
        "checked_at": utcnow(),
        "purpose": "engineering_pilot" if run["pilot"] else "acquisition_validation",
        "checks": checks,
        "repositories": len(repositories),
        "forks": len(comparisons),
        "frozen_forks": len(frozen),
        "excluded_forks": len(exclusions),
        "skipped_forks": len(skips),
        "reused_comparisons": sum(item.reused_from is not None for item in comparisons),
        "source_commits": sum(len(item.commits) for item in comparisons),
        "coverage_complete": coverage_complete,
        "discovery_coverage_complete": bool(coverage) and all(item["complete"] for item in coverage),
        "complete_comparisons": sum(item.commits_complete for item in comparisons),
        "formally_retained_repositories": sum(
            item.repository.screening_complete and item.repository.excluded_by is None
            for item in repositories
        ),
        "limitations": [
            "This validates acquisition, not monthly origin attribution or annotation.",
            "Pilot bounds do not define a representative sample.",
            "Divergence commits may predate or follow the observation cutoff; temporal selection belongs to monthly extraction.",
            "HTTP 404 skips are omitted from the available corpus; acceptance does not imply every listed fork was accessible.",
        ],
    }
    write_json(root / "acceptance.json", report)
    return report


def load_extraction_inputs(root: Path, run: dict, *, allow_partial: bool = False) -> list[tuple[Fork, str]]:
    """Require completed acquisition unless an explicit pilot permits partial inputs."""
    if allow_partial and not run["pilot"]:
        raise ValueError("Partial extraction requires a bounded pilot run; use a separate pilot ID.")
    if not allow_partial:
        path = root / "progress.json"
        progress = json.loads(path.read_text()) if path.exists() else {}
        if progress.get("state") != "finished":
            raise ValueError("Extraction requires finished acquisition; use --allow_partial only in a pilot run.")
        if verify_run(root)["status"] != "passed":
            raise ValueError("Extraction requires passing acquisition acceptance.")
    omitted = {
        (row["fork"]["upstream"], row["github_id"])
        for row in read_jsonl(root / "fork_exclusions.jsonl")
    } | {
        (row["upstream"], row["github_id"])
        for row in read_jsonl(root / "fork_skips.jsonl")
    }
    successful = {
        (row["fork"]["upstream"], row["github_id"])
        for row in read_jsonl(root / "comparisons.jsonl")
    }
    repositories = {
        row["repository"]["full_name"]: RepositorySnapshot.model_validate(row)
        for row in read_jsonl(root / "repositories.jsonl")
    }
    inputs = []
    for row in read_jsonl(root / "forks.jsonl"):
        identity = (row["upstream"], row["github_id"])
        if identity in omitted or identity not in successful:
            continue
        fork = Fork.model_validate(row)
        repository = repositories[fork.upstream]
        if (
            repository.tree_complete and repository.repository.excluded_by is None
            and (run["pilot"] or repository.repository.screening_complete)
        ):
            inputs.append((fork, repository.default_branch_sha))
    if not inputs:
        raise ValueError("Extraction needs eligible forks with successful comparisons.")
    return inputs
