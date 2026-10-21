"""Discover repositories, measure their trees and mine frozen public forks."""

import json
import logging
import re
from collections import Counter
from pathlib import Path
from urllib.parse import quote, urlencode

from src.config import ExperimentSettings, ScreeningSettings
from src.domain import (
    ExclusionReason,
    Fork,
    ForkComparison,
    ForkExclusion,
    ForkSkip,
    Repository,
    RepositorySnapshot,
    RetrievalChannel,
    RetrievalEvidence,
    SourceCommit,
    TreeEntry,
)
from src.github import ApiError, NoCommonAncestor, collect_pages, read_jsonl, utcnow, write_json, write_jsonl
from src.preprocess import measure_skill_centricity

logger = logging.getLogger(__name__)


def complete_tree(client, repository: str, tree_sha: str) -> list[TreeEntry]:
    """Expand truncated recursive responses using complete direct subtrees."""
    endpoint = f"repos/{repository}/git/trees/{tree_sha}"
    response = client.get(endpoint + "?recursive=1").body
    if not response["truncated"]:
        return [TreeEntry.model_validate(item) for item in response["tree"]]
    entries = []
    pending = [("", tree_sha)]
    subtrees = {}
    while pending:
        prefix, sha = pending.pop()
        if sha not in subtrees:
            subtree = client.get(f"repos/{repository}/git/trees/{sha}").body
            if subtree["truncated"]:
                raise ApiError(f"Direct subtree is truncated: {repository} {sha}")
            subtrees[sha] = subtree["tree"]
        for item in subtrees[sha]:
            path = f"{prefix}/{item['path']}" if prefix else item["path"]
            entries.append(
                TreeEntry(
                    path=path, type=item["type"], mode=item["mode"], sha=item["sha"]
                )
            )
            if item["type"] == "tree":
                pending.append((path, item["sha"]))
    return entries


def screen_repository(
    repository: Repository, entries: list[TreeEntry], settings: ScreeningSettings
) -> Repository:
    """Apply confirmed rules, leaving uncalibrated or unreviewed cases pending."""
    result = repository.model_copy(deep=True)
    result.skill_centricity = measure_skill_centricity(entries, complete=True)
    result.skill_package_paths = result.skill_centricity.package_paths
    ratio = result.skill_centricity.ratio
    review = next(
        (
            review
            for name, review in settings.reviews.items()
            if name.lower() == result.full_name.lower()
        ),
        None,
    )
    if result.forks_count < settings.minimum_forks:
        result.excluded_by = ExclusionReason.FORK_THRESHOLD
        result.exclusion_note = (
            f"Fewer than {settings.minimum_forks} forks at retrieval."
        )
    elif not result.skill_package_paths:
        result.excluded_by = ExclusionReason.NOT_SKILL_CENTRIC
        result.exclusion_note = "No regular SKILL.md manifest in the complete tree."
    elif (
        settings.selection_mode == "calibrated_ratio"
        and settings.skill_centricity_threshold is not None
        and (ratio is None or ratio < settings.skill_centricity_threshold)
    ):
        result.excluded_by = ExclusionReason.NOT_SKILL_CENTRIC
        result.exclusion_note = "Package file ratio is below the calibrated threshold."
    elif review and review.is_aggregator:
        result.excluded_by = ExclusionReason.AGGREGATOR
        result.exclusion_note = review.reason
    elif review and review.exclude:
        result.excluded_by = ExclusionReason.MANUAL
        result.exclusion_note = review.reason
    result.screening_complete = result.excluded_by is not None or (
        review is not None
        and (
            settings.selection_mode == "confirmed_reviews"
            or settings.skill_centricity_threshold is not None
        )
    )
    return result


def record_error(
    errors: list[dict], stage: str, subject: str, error: Exception
) -> None:
    """Preserve failures separately from empty responses and screened exclusions."""
    logger.error("%s failed for %s: %s", stage, subject, error)
    errors.append({"stage": stage, "subject": subject, "error": str(error)})


def discover(
    client,
    config: ExperimentSettings,
    root: Path,
    limit: int | None,
    errors: list[dict],
) -> dict[str, list[RetrievalEvidence]]:
    """Combine intent and manifest queries without losing channel overlap."""
    topics = Counter()
    seed_topics = {}
    for repository in config.retrieval.topic_seeds:
        try:
            metadata = client.get(f"repos/{repository}").body
            seed_topics[repository] = metadata.get("topics", [])
            topics.update(sorted(set(seed_topics[repository])))
        except (ApiError, KeyError, ValueError) as error:
            record_error(errors, "seed_topics", repository, error)
    selected_topics = [
        topic
        for topic, count in sorted(topics.items(), key=lambda item: (-item[1], item[0]))
        if config.retrieval.topic_contains.lower() in topic.lower()
    ][: config.retrieval.maximum_topics]
    write_json(
        root / "topics.json",
        {
            "seeds": seed_topics,
            "frequencies": dict(topics),
            "selected": selected_topics,
        },
    )
    floor = min(
        [config.screening.minimum_forks, *config.screening.sensitivity_fork_thresholds]
    )
    queries = [
        (RetrievalChannel.INTENT, query)
        for query in [
            *[f"topic:{topic}" for topic in selected_topics],
            *config.retrieval.description_queries,
        ]
    ]
    queries += [
        (RetrievalChannel.MANIFEST, query)
        for query in config.retrieval.manifest_queries
    ]
    candidates, coverage = {}, []
    for channel, query in queries:
        route = "repositories" if channel == RetrievalChannel.INTENT else "code"
        if channel == RetrievalChannel.INTENT:
            query += f" forks:>={floor} fork:false"
        endpoint = f"search/{route}?" + urlencode(
            {"q": query, "per_page": config.github.per_page}
        )
        logger.info("Searching %s: %s", channel, query)
        try:
            hits, report = collect_pages(client, endpoint, key="items", limit=limit)
            coverage.append({"channel": channel.value, "query": query, **report})
            for hit in hits:
                name = (
                    hit if channel == RetrievalChannel.INTENT else hit["repository"]
                )["full_name"].lower()
                evidence = RetrievalEvidence(
                    channel=channel, source=query, path=hit.get("path")
                )
                if evidence not in candidates.setdefault(name, []):
                    candidates[name].append(evidence)
        except (ApiError, KeyError, ValueError) as error:
            record_error(errors, "search", query, error)
            coverage.append(
                {
                    "channel": channel.value,
                    "query": query,
                    "complete": False,
                    "stop_reason": "error",
                }
            )
    for pointer in config.retrieval.registry_pointers:
        candidates.setdefault(pointer.repository.lower(), []).append(
            RetrievalEvidence(
                channel=RetrievalChannel.MANIFEST, source=pointer.source_url
            )
        )
    write_json(root / "search_coverage.json", coverage)
    write_jsonl(
        root / "discovered.jsonl",
        [
            {
                "full_name": name,
                "evidence": [item.model_dump(mode="json") for item in evidence],
            }
            for name, evidence in sorted(candidates.items())
        ],
    )
    return candidates


def retrieve_repositories(
    client, config: ExperimentSettings, root: Path, *, limit: int | None
) -> list[RepositorySnapshot]:
    """Retrieve candidates and screen a deterministic, optionally bounded set."""
    if config.screening.selection_mode == "confirmed_reviews":
        raise ValueError("Use the source run to import the confirmed repositories.")
    errors = []
    candidates = discover(client, config, root, limit, errors)
    metadata_by_id = {}
    for index, (name, evidence) in enumerate(candidates.items(), start=1):
        if index == 1 or index % 100 == 0 or index == len(candidates):
            logger.info("Retrieving repository metadata %d/%d", index, len(candidates))
        try:
            response = client.get(f"repos/{name}")
            metadata = response.body
            if metadata.get("private") or metadata.get("fork"):
                continue
            identity = metadata["id"]
            if identity in metadata_by_id:
                existing = metadata_by_id[identity]["evidence"]
                existing.extend(item for item in evidence if item not in existing)
            else:
                metadata_by_id[identity] = {
                    "metadata": metadata,
                    "retrieved_at": response.retrieved_at,
                    "evidence": evidence,
                }
        except (ApiError, KeyError, ValueError) as error:
            record_error(errors, "repository_metadata", name, error)
    ordered = sorted(
        metadata_by_id.values(),
        key=lambda row: (
            -row["metadata"]["forks_count"],
            row["metadata"]["full_name"].lower(),
        ),
    )
    write_jsonl(
        root / "candidate_metadata.jsonl",
        [
            {
                **row,
                "evidence": [item.model_dump(mode="json") for item in row["evidence"]],
            }
            for row in ordered
        ],
    )
    results = []
    floor = min(
        [config.screening.minimum_forks, *config.screening.sensitivity_fork_thresholds]
    )
    for row in ordered[:limit]:
        metadata = row["metadata"]
        name = metadata["full_name"]
        repository = Repository(
            full_name=name,
            channels=sorted({item.channel for item in row["evidence"]}),
            retrieved_at=row["retrieved_at"],
            forks_count=metadata["forks_count"],
            stars_count=metadata["stargazers_count"],
            skill_package_paths=[],
            aggregator_keyword_hit=bool(
                re.search(
                    r"\b(awesome|collection|curated)\b",
                    " ".join(
                        [
                            name,
                            metadata.get("description") or "",
                            *metadata.get("topics", []),
                        ]
                    ).lower(),
                )
            ),
        )
        snapshot = RepositorySnapshot(
            repository=repository,
            github_id=metadata["id"],
            default_branch=metadata["default_branch"],
            evidence=row["evidence"],
        )
        try:
            if repository.forks_count < floor:
                repository.excluded_by = ExclusionReason.FORK_THRESHOLD
                repository.exclusion_note = (
                    f"Fewer than {floor} forks, the lowest configured threshold."
                )
                repository.screening_complete = True
            else:
                logger.info(
                    "Freezing and screening %s (%d forks)", name, repository.forks_count
                )
                branch = client.get(
                    f"repos/{name}/branches/{quote(snapshot.default_branch, safe='')}"
                ).body
                snapshot.default_branch_sha = branch["commit"]["sha"]
                commit = client.get(
                    f"repos/{name}/git/commits/{snapshot.default_branch_sha}"
                ).body
                snapshot.tree_sha = commit["tree"]["sha"]
                entries = complete_tree(client, name, snapshot.tree_sha)
                write_jsonl(root / "trees" / f"{snapshot.github_id}.jsonl", entries)
                snapshot.tree_complete = True
                snapshot.repository = screen_repository(
                    repository, entries, config.screening
                )
        except (ApiError, KeyError, ValueError) as error:
            record_error(errors, "repository_tree", name, error)
        results.append(snapshot)
    write_jsonl(root / "repositories.jsonl", results)
    write_jsonl(root / "repository_errors.jsonl", errors)
    search_coverage = json.loads((root / "search_coverage.json").read_text())
    write_json(
        root / "repository_summary.json",
        {
            "discovered": len(candidates),
            "metadata_available": len(ordered),
            "processed": len(results),
            "trees_complete": sum(item.tree_complete for item in results),
            "retained": sum(
                item.repository.screening_complete
                and item.repository.excluded_by is None
                for item in results
            ),
            "pending": sum(not item.repository.screening_complete for item in results),
            "excluded": dict(
                Counter(
                    item.repository.excluded_by.value
                    for item in results
                    if item.repository.excluded_by
                )
            ),
            "errors": len(errors),
            "complete": not errors
            and len(results) == len(ordered)
            and all(item["complete"] for item in search_coverage),
        },
    )
    return results


def compare_fork(
    client,
    fork: Fork,
    github_id: int,
    upstream_sha: str,
    *,
    per_page: int,
    limit: int | None,
) -> ForkComparison | ForkExclusion:
    """Collect divergence metadata using only the two frozen commit SHAs."""
    endpoint = f"repos/{fork.full_name}/compare/{upstream_sha}...{fork.default_branch_sha}?per_page={per_page}"
    try:
        metadata = client.get(endpoint).body
    except NoCommonAncestor as error:
        return ForkExclusion(
            fork=fork, github_id=github_id, upstream_sha=upstream_sha,
            endpoint=error.endpoint, message=str(error), retrieved_at=error.retrieved_at,
        )
    commits, coverage = collect_pages(client, endpoint, key="commits", limit=limit)
    unique = {item["sha"]: item for item in commits}
    if len(unique) != len(commits):
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
        commits=[
            SourceCommit(
                sha=item["sha"],
                tree_sha=item["commit"]["tree"]["sha"],
                parent_shas=[parent["sha"] for parent in item["parents"]],
                author_date=item["commit"]["author"]["date"],
                committer_date=item["commit"]["committer"]["date"],
                message=item["commit"]["message"],
                author_login=(item.get("author") or {}).get("login"),
            )
            for item in commits
        ],
    )


def retrieve_forks(
    client, config: ExperimentSettings, root: Path, *, limit: int | None, pilot: bool
) -> list[ForkComparison]:
    """Enumerate public forks and preserve frozen branch comparisons."""
    if not (root / "repositories.jsonl").exists():
        raise ValueError("Run the repositories step before collecting forks.")
    repositories = [
        RepositorySnapshot.model_validate(row)
        for row in read_jsonl(root / "repositories.jsonl")
    ]
    selected = [
        item
        for item in repositories
        if item.tree_complete
        and item.repository.excluded_by is None
        and (item.repository.screening_complete or pilot)
        and (
            config.screening.selection_mode != "confirmed_reviews"
            or any(
                name.lower() == item.repository.full_name.lower()
                and not review.exclude
                and not review.is_aggregator
                for name, review in config.screening.reviews.items()
            )
        )
    ]
    if not selected:
        raise ValueError(
            "No eligible repositories. Formal collection requires calibrated screening and human review; use --pilot only for engineering validation."
        )
    results, frozen, errors, coverage, exclusions, skips = [], [], [], [], [], []
    complete_pairs = {}
    inventory_path = root / "recovery_inventory.json"
    previous_inventory = json.loads(inventory_path.read_text()) if inventory_path.exists() else {}

    def checkpoint(upstreams_processed: int) -> None:
        """Publish stage outputs at bounded intervals, including unresolved errors."""
        write_jsonl(root / "forks.jsonl", frozen)
        write_jsonl(root / "comparisons.jsonl", results)
        write_jsonl(root / "fork_exclusions.jsonl", exclusions)
        write_jsonl(root / "fork_skips.jsonl", skips)
        write_jsonl(root / "fork_errors.jsonl", errors)
        write_json(root / "fork_coverage.json", coverage)
        write_json(root / "fork_summary.json", {
            "upstreams": len(selected), "upstreams_processed": upstreams_processed,
            "frozen_forks": len(frozen), "compared_forks": len(results),
            "excluded_forks": len(exclusions),
            "skipped_forks": len(skips),
            "reused_comparisons": sum(item.reused_from is not None for item in results),
            "comparison_statuses": dict(Counter(item.status for item in results)),
            "source_commits": sum(len(item.commits) for item in results),
            "comparisons_complete": sum(item.commits_complete for item in results),
            "errors": len(errors),
            "complete": upstreams_processed == len(selected) and not errors
            and len(coverage) == len(selected)
            and all(item["complete"] for item in coverage)
            and all(item.commits_complete for item in results)
            and len(frozen) == len(results) + len(exclusions)
            + sum(item.default_branch_sha is not None for item in skips),
        })

    def progress(upstreams_processed: int, name: str, state: str = "running") -> None:
        """Expose progress while large upstreams are still being collected."""
        write_json(root / "progress.json", {
            "updated_at": utcnow(), "state": state, "upstream": name,
            "upstreams_total": len(selected), "upstreams_processed": upstreams_processed,
            "frozen_forks": len(frozen), "compared_forks": len(results),
            "excluded_forks": len(exclusions), "errors": len(errors),
            "skipped_forks": len(skips),
            "reused_comparisons": sum(item.reused_from is not None for item in results),
        })

    def skip_unavailable(name, row, stage, error, fork=None):
        skips.append(ForkSkip(
            upstream=name, github_id=row["id"], full_name=row["full_name"],
            stage=stage, message=str(error),
            default_branch_sha=fork.default_branch_sha if fork else None,
        ))
        logger.info("Skipped unavailable fork %s at %s", row["full_name"], stage)

    for upstream_index, upstream in enumerate(selected, start=1):
        name = upstream.repository.full_name
        previous_rows = {row["id"]: row for row in previous_inventory.get(name, [])}
        progress(upstream_index - 1, name)
        endpoint = f"repos/{name}/forks?" + urlencode(
            {"per_page": config.github.per_page, "sort": config.retrieval.fork_sort}
        )
        logger.info("Enumerating forks of %s", name)
        try:
            rows, report = collect_pages(client, endpoint, limit=limit)
            identities = [row["id"] for row in rows]
            unique = set(identities)
            duplicate_rows = len(identities) - len(unique)
            previous_ids = set(previous_rows)
            missing = sorted(previous_ids - unique) if limit is None else []
            inversions = 0
            if config.retrieval.fork_sort == "oldest":
                dates = [row["created_at"] for row in rows]
                inversions = sum(right < left for left, right in zip(dates, dates[1:]))
            reconciled_metadata = {}
            if not duplicate_rows and not inversions:
                for identity in missing:
                    try:
                        response = client.get(f"repositories/{identity}")
                        metadata = response.body
                        network_ids = {
                            (metadata.get(key) or {}).get("id") for key in ("parent", "source")
                        }
                        if (
                            metadata["id"] != identity or metadata.get("private")
                            or not metadata.get("fork") or upstream.github_id not in network_ids
                        ):
                            raise ApiError("Missing fork identity or upstream membership could not be verified.")
                        if config.retrieval.fork_sort == "oldest":
                            metadata["created_at"]  # Required before inserting into creation order.
                        rows.append(metadata)
                        reconciled_metadata[identity] = response
                    except (ApiError, KeyError, ValueError) as error:
                        if isinstance(error, ApiError) and error.status == 404:
                            skip_unavailable(name, previous_rows[identity], "fork_reconciliation", error)
                        else:
                            record_error(errors, "fork_reconciliation", previous_rows[identity]["full_name"], error)
                if reconciled_metadata and config.retrieval.fork_sort == "oldest":
                    rows.sort(key=lambda row: (row["created_at"], row["id"]))
            missing = sorted(set(missing) - set(reconciled_metadata))
            skipped_ids = {item.github_id for item in skips if item.upstream == name}
            report.update({
                "unique_forks": len(unique) + len(reconciled_metadata), "duplicate_rows": duplicate_rows,
                "creation_time_inversions": inversions, "missing_previous_ids": missing,
                "reconciled_ids": sorted(reconciled_metadata),
            })
            if duplicate_rows or inversions or set(missing) - skipped_ids:
                report.update(complete=False, stop_reason="inconsistent_inventory")
            coverage.append({"upstream": name, **report})
            write_json(root / "fork_coverage.json", coverage)
            if duplicate_rows or inversions:
                raise ApiError(
                    f"Inconsistent fork inventory: {duplicate_rows} duplicate rows, "
                    f"{inversions} creation order inversions, {len(missing)} previously observed IDs missing."
                )
            if missing:
                checkpoint(upstream_index - 1)
        except (ApiError, KeyError, ValueError) as error:
            record_error(errors, "fork_enumeration", name, error)
            checkpoint(upstream_index)
            continue
        for fork_index, row in enumerate(rows, start=1):
            fork_name = row["full_name"]
            stage, fork = "fork_metadata", None
            try:
                if row.get("private") or not row.get("fork"):
                    raise ApiError(
                        "Fork listing returned a repository outside the public fork population."
                    )
                try:
                    metadata_endpoint = previous_rows.get(row["id"], {}).get("metadata_endpoint")
                    metadata_response = reconciled_metadata.get(row["id"])
                    if metadata_response is None:
                        metadata_response = client.get(metadata_endpoint or f"repos/{fork_name}")
                except ApiError as error:
                    if error.status != 404:
                        raise
                    metadata_response = client.get(f"repositories/{row['id']}")
                metadata = metadata_response.body
                if (
                    metadata["id"] != row["id"]
                    or metadata.get("private")
                    or not metadata.get("fork")
                ):
                    raise ApiError(
                        "Fork identity or public visibility changed during acquisition."
                    )
                branch = metadata["default_branch"]
                stage = "fork_branch"
                response = client.get(
                    f"repos/{metadata['full_name']}/branches/{quote(branch, safe='')}"
                )
                fork = Fork(
                    upstream=name,
                    full_name=metadata["full_name"],
                    owner=metadata["owner"]["login"],
                    created_at=metadata["created_at"],
                    pushed_at=metadata["pushed_at"],
                    retrieved_at=response.retrieved_at,
                    default_branch=branch,
                    default_branch_sha=response.body["commit"]["sha"],
                )
                frozen.append({"github_id": row["id"], **fork.model_dump(mode="json")})
                stage = "fork_comparison"
                logger.info("Comparing frozen fork %s", fork.full_name)
                pair = (name, upstream.default_branch_sha, fork.default_branch_sha)
                if pair in complete_pairs:
                    source = complete_pairs[pair]
                    comparison = source.model_copy(update={
                        "fork": fork, "github_id": row["id"],
                        "reused_from": source.fork.full_name,
                    })
                else:
                    comparison = compare_fork(
                        client, fork, row["id"], upstream.default_branch_sha,
                        per_page=config.github.per_page, limit=limit,
                    )
                    if isinstance(comparison, ForkComparison) and comparison.commits_complete:
                        complete_pairs[pair] = comparison
                if isinstance(comparison, ForkExclusion):
                    exclusions.append(comparison)
                    logger.info("Excluded unrelated fork history: %s", fork.full_name)
                else:
                    results.append(comparison)
            except (ApiError, KeyError, ValueError) as error:
                if isinstance(error, ApiError) and error.status == 404:
                    skip_unavailable(name, row, stage, error, fork)
                else:
                    record_error(errors, stage, fork_name, error)
            if fork_index % 250 == 0:
                checkpoint(upstream_index - 1)
            if fork_index % 25 == 0:
                progress(upstream_index - 1, name)
        checkpoint(upstream_index)
    progress(len(selected), selected[-1].repository.full_name, "failed" if errors else "finished")
    return results
