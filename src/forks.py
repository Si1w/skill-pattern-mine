"""Enumerate public forks, freeze their branches and compare them with upstream."""

import logging
from collections import Counter
from pathlib import Path
from urllib.parse import quote, urlencode

from src.config import ExperimentSettings
from src.domain import (
    Fork,
    ForkComparison,
    ForkExclusion,
    ForkSkip,
    RepositorySnapshot,
    SourceCommit,
)
from src.github import ApiError, NoCommonAncestor, Page, collect_pages
from src.repositories import eligible_upstreams
from src.storage import read_jsonl, record_error, utcnow, write_json, write_jsonl

logger = logging.getLogger(__name__)

CHECKPOINT_EVERY = 250
PROGRESS_EVERY = 25


def source_commit(item: dict) -> SourceCommit:
    """Parse one GitHub commit object, preserving ordered parents and both dates."""
    return SourceCommit(
        sha=item["sha"],
        tree_sha=item["commit"]["tree"]["sha"],
        parent_shas=[parent["sha"] for parent in item["parents"]],
        author_date=item["commit"]["author"]["date"],
        committer_date=item["commit"]["committer"]["date"],
        message=item["commit"]["message"],
        author_login=(item.get("author") or {}).get("login"),
    )


class ForkStage:
    """Outputs of the fork stage, written at checkpoints so interruptions lose little."""

    def __init__(self, root: Path, upstream_count: int):
        self.root = root
        self.upstream_count = upstream_count
        self.frozen: list[dict] = []
        self.comparisons: list[ForkComparison] = []
        self.exclusions: list[ForkExclusion] = []
        self.skips: list[ForkSkip] = []
        self.errors: list[dict] = []
        self.coverage: list[dict] = []
        self.complete_pairs: dict[tuple[str, str, str], ForkComparison] = {}

    @property
    def reused(self) -> int:
        return sum(item.reused_from is not None for item in self.comparisons)

    def skip(self, upstream: str, row: dict, stage: str, error: Exception, fork: Fork | None = None) -> None:
        """Record an HTTP 404 as a missing observation rather than an error (ADR 0031)."""
        self.skips.append(
            ForkSkip(
                upstream=upstream,
                github_id=row["id"],
                full_name=row["full_name"],
                stage=stage,
                message=str(error),
                default_branch_sha=fork.default_branch_sha if fork else None,
            )
        )
        logger.info("Skipped unavailable fork %s at %s", row["full_name"], stage)

    def checkpoint(self, upstreams_processed: int) -> None:
        """Write every stage artifact, including unresolved errors."""
        write_jsonl(self.root / "forks.jsonl", self.frozen)
        write_jsonl(self.root / "comparisons.jsonl", self.comparisons)
        write_jsonl(self.root / "fork_exclusions.jsonl", self.exclusions)
        write_jsonl(self.root / "fork_skips.jsonl", self.skips)
        write_jsonl(self.root / "fork_errors.jsonl", self.errors)
        write_json(self.root / "fork_coverage.json", self.coverage)
        frozen_skips = sum(item.default_branch_sha is not None for item in self.skips)
        write_json(
            self.root / "fork_summary.json",
            {
                "upstreams": self.upstream_count,
                "upstreams_processed": upstreams_processed,
                "frozen_forks": len(self.frozen),
                "compared_forks": len(self.comparisons),
                "excluded_forks": len(self.exclusions),
                "skipped_forks": len(self.skips),
                "reused_comparisons": self.reused,
                "comparison_statuses": dict(Counter(item.status for item in self.comparisons)),
                "source_commits": sum(len(item.commits) for item in self.comparisons),
                "comparisons_complete": sum(item.commits_complete for item in self.comparisons),
                "errors": len(self.errors),
                "complete": upstreams_processed == self.upstream_count
                and not self.errors
                and len(self.coverage) == self.upstream_count
                and all(item["complete"] for item in self.coverage)
                and all(item.commits_complete for item in self.comparisons)
                and len(self.frozen) == len(self.comparisons) + len(self.exclusions) + frozen_skips,
            },
        )

    def progress(self, upstreams_processed: int, upstream: str, state: str = "running") -> None:
        """Expose progress while large upstreams are still being collected."""
        write_json(
            self.root / "progress.json",
            {
                "updated_at": utcnow(),
                "state": state,
                "upstream": upstream,
                "upstreams_total": self.upstream_count,
                "upstreams_processed": upstreams_processed,
                "frozen_forks": len(self.frozen),
                "compared_forks": len(self.comparisons),
                "excluded_forks": len(self.exclusions),
                "skipped_forks": len(self.skips),
                "reused_comparisons": self.reused,
                "errors": len(self.errors),
            },
        )


def enumerate_forks(client, config: ExperimentSettings, upstream: str, limit: int | None) -> tuple[list[dict], dict]:
    """List forks and check the listing for duplicate rows and creation order inversions.

    An inconsistent listing is reported with stop reason inconsistent_inventory;
    the caller must not request comparisons for it.
    """
    endpoint = f"repos/{upstream}/forks?" + urlencode(
        {"per_page": config.github.per_page, "sort": config.retrieval.fork_sort}
    )
    logger.info("Enumerating forks of %s", upstream)
    rows, report = collect_pages(client, endpoint, limit=limit)
    identities = [row["id"] for row in rows]
    duplicate_rows = len(identities) - len(set(identities))
    inversions = 0
    if config.retrieval.fork_sort == "oldest":
        dates = [row["created_at"] for row in rows]
        inversions = sum(right < left for left, right in zip(dates, dates[1:]))
    report.update(
        {
            "upstream": upstream,
            "unique_forks": len(set(identities)),
            "duplicate_rows": duplicate_rows,
            "creation_time_inversions": inversions,
        }
    )
    if duplicate_rows or inversions:
        report.update(complete=False, stop_reason="inconsistent_inventory")
    return rows, report


def fork_metadata(client, row: dict) -> Page:
    """Read fork metadata by name, falling back to the numeric identity after a 404.

    Renamed forks keep their numeric identity; the response must still describe
    a public fork with the listed identity.
    """
    try:
        response = client.get(f"repos/{row['full_name']}")
    except ApiError as error:
        if error.status != 404:
            raise
        response = client.get(f"repositories/{row['id']}")
    metadata = response.body
    if metadata["id"] != row["id"] or metadata.get("private") or not metadata.get("fork"):
        raise ApiError("Fork identity or public visibility changed during acquisition.")
    return response


def freeze_fork(client, upstream: str, metadata: dict) -> Fork:
    """Resolve the default branch head once; later mining never follows the moving ref."""
    branch = metadata["default_branch"]
    response = client.get(f"repos/{metadata['full_name']}/branches/{quote(branch, safe='')}")
    return Fork(
        upstream=upstream,
        full_name=metadata["full_name"],
        owner=metadata["owner"]["login"],
        created_at=metadata["created_at"],
        pushed_at=metadata["pushed_at"],
        retrieved_at=response.retrieved_at,
        default_branch=branch,
        default_branch_sha=response.body["commit"]["sha"],
    )


def compare_fork(
    client, fork: Fork, github_id: int, upstream_sha: str, *, per_page: int, limit: int | None
) -> ForkComparison | ForkExclusion:
    """Collect divergence metadata using only the two frozen commit SHAs."""
    endpoint = f"repos/{fork.full_name}/compare/{upstream_sha}...{fork.default_branch_sha}?per_page={per_page}"
    try:
        metadata = client.get(endpoint).body
    except NoCommonAncestor as error:
        return ForkExclusion(
            fork=fork,
            github_id=github_id,
            upstream_sha=upstream_sha,
            endpoint=error.endpoint,
            message=str(error),
            retrieved_at=error.retrieved_at,
        )
    commits, coverage = collect_pages(client, endpoint, key="commits", limit=limit)
    if len({item["sha"] for item in commits}) != len(commits):
        raise ApiError(f"Comparison repeated a commit: {fork.full_name}")
    if coverage["complete"] and len(commits) != metadata["ahead_by"]:
        raise ApiError(f"Comparison count differs from ahead_by: {fork.full_name}")
    return ForkComparison(
        fork=fork,
        github_id=github_id,
        upstream_sha=upstream_sha,
        merge_base_sha=metadata["merge_base_commit"]["sha"],
        status=metadata["status"],
        ahead_by=metadata["ahead_by"],
        behind_by=metadata["behind_by"],
        commits_complete=coverage["complete"],
        commits=[source_commit(item) for item in commits],
    )


def compare_or_reuse(
    client,
    config: ExperimentSettings,
    stage: ForkStage,
    fork: Fork,
    github_id: int,
    upstream_sha: str,
    limit: int | None,
) -> ForkComparison | ForkExclusion:
    """Reuse a complete comparison of the same SHA pair within the upstream (ADR 0032)."""
    pair = (fork.upstream, upstream_sha, fork.default_branch_sha)
    source = stage.complete_pairs.get(pair)
    if source is not None:
        return source.model_copy(
            update={"fork": fork, "github_id": github_id, "reused_from": source.fork.full_name}
        )
    comparison = compare_fork(
        client, fork, github_id, upstream_sha, per_page=config.github.per_page, limit=limit
    )
    if isinstance(comparison, ForkComparison) and comparison.commits_complete:
        stage.complete_pairs[pair] = comparison
    return comparison


def process_fork(
    client, config: ExperimentSettings, stage: ForkStage, upstream: RepositorySnapshot, row: dict, limit: int | None
) -> None:
    """Freeze and compare one listed fork, recording a skip, exclusion or error."""
    name = upstream.repository.full_name
    step, fork = "fork_metadata", None
    try:
        if row.get("private") or not row.get("fork"):
            raise ApiError("Fork listing returned a repository outside the public fork population.")
        metadata = fork_metadata(client, row).body
        step = "fork_branch"
        fork = freeze_fork(client, name, metadata)
        stage.frozen.append({"github_id": row["id"], **fork.model_dump(mode="json")})
        step = "fork_comparison"
        logger.info("Comparing frozen fork %s", fork.full_name)
        comparison = compare_or_reuse(
            client, config, stage, fork, row["id"], upstream.default_branch_sha, limit
        )
        if isinstance(comparison, ForkExclusion):
            stage.exclusions.append(comparison)
            logger.info("Excluded unrelated fork history: %s", fork.full_name)
        else:
            stage.comparisons.append(comparison)
    except (ApiError, KeyError, ValueError) as error:
        if isinstance(error, ApiError) and error.status == 404:
            stage.skip(name, row, step, error, fork)
        else:
            record_error(stage.errors, step, row["full_name"], error)


def retrieve_forks(
    client, config: ExperimentSettings, root: Path, *, limit: int | None, pilot: bool
) -> list[ForkComparison]:
    """Enumerate public forks of every eligible upstream and preserve frozen comparisons."""
    if not (root / "repositories.jsonl").exists():
        raise ValueError("Run the repositories step before collecting forks.")
    repositories = [RepositorySnapshot.model_validate(row) for row in read_jsonl(root / "repositories.jsonl")]
    selected = eligible_upstreams(repositories, pilot=pilot)
    if not selected:
        raise ValueError(
            "No eligible repositories. Formal collection requires reviewed repositories; "
            "use --pilot only for engineering validation."
        )
    stage = ForkStage(root, len(selected))
    for index, upstream in enumerate(selected, start=1):
        name = upstream.repository.full_name
        stage.progress(index - 1, name)
        try:
            rows, report = enumerate_forks(client, config, name, limit)
        except (ApiError, KeyError, ValueError) as error:
            record_error(stage.errors, "fork_enumeration", name, error)
            stage.checkpoint(index)
            continue
        stage.coverage.append(report)
        if report["stop_reason"] == "inconsistent_inventory":
            problem = ApiError(
                f"Inconsistent fork inventory: {report['duplicate_rows']} duplicate rows, "
                f"{report['creation_time_inversions']} creation order inversions."
            )
            record_error(stage.errors, "fork_enumeration", name, problem)
            stage.checkpoint(index)
            continue
        for fork_index, row in enumerate(rows, start=1):
            process_fork(client, config, stage, upstream, row, limit)
            if fork_index % CHECKPOINT_EVERY == 0:
                stage.checkpoint(index - 1)
            if fork_index % PROGRESS_EVERY == 0:
                stage.progress(index - 1, name)
        stage.checkpoint(index)
    final_state = "failed" if stage.errors else "finished"
    stage.progress(len(selected), selected[-1].repository.full_name, final_state)
    return stage.comparisons
