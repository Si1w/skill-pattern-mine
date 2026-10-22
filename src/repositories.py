"""Discover candidate repositories, freeze their trees and screen them."""

import logging
import re
import shutil
from collections import Counter
from pathlib import Path
from urllib.parse import quote, urlencode

from src.config import ExperimentSettings, ScreeningSettings
from src.domain import (
    ExclusionReason,
    Repository,
    RepositorySnapshot,
    RetrievalChannel,
    RetrievalEvidence,
    TreeEntry,
)
from src.github import ApiError, collect_pages
from src.preprocess import measure_skill_centricity
from src.storage import read_json, read_jsonl, record_error, write_json, write_jsonl

logger = logging.getLogger(__name__)

AGGREGATOR_KEYWORDS = re.compile(r"\b(awesome|collection|curated)\b")
SEARCH_CAP = 1000  # GitHub returns at most 1,000 results per search query.


def complete_tree(client, repository: str, tree_sha: str, *, expand_truncated: bool = True) -> list[TreeEntry] | None:
    """Read the complete tree; expand a truncated response only when asked (ADR 0046).

    Expansion walks every subtree with one request each, which costs tens of
    thousands of requests on a very large repository. Returns None when the
    recursive response is truncated and expansion is not allowed.
    """
    endpoint = f"repos/{repository}/git/trees/{tree_sha}"
    response = client.get(endpoint + "?recursive=1").body
    if not response["truncated"]:
        return [TreeEntry.model_validate(item) for item in response["tree"]]
    if not expand_truncated:
        return None
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
            entries.append(TreeEntry(path=path, type=item["type"], mode=item["mode"], sha=item["sha"]))
            if item["type"] == "tree":
                pending.append((path, item["sha"]))
    return entries


def screen_repository(
    repository: Repository, entries: list[TreeEntry], settings: ScreeningSettings
) -> Repository:
    """Apply the structural rules; only a confirmed repository is retained.

    The rules run in order: fork threshold, manifest presence, forks against
    stars and package count (ADR 0048). Candidates that pass them but are not
    confirmed stay pending. The package file ratio is measured and recorded
    but never used as a threshold (ADR 0042).
    """
    result = repository.model_copy(deep=True)
    result.skill_centricity = measure_skill_centricity(entries, complete=True)
    result.skill_package_paths = result.skill_centricity.package_paths
    confirmed = result.full_name.lower() in settings.confirmed_repositories()
    if result.forks_count < settings.minimum_forks:
        result.excluded_by = ExclusionReason.FORK_THRESHOLD
        result.exclusion_note = f"Fewer than {settings.minimum_forks} forks at retrieval."
    elif not result.skill_package_paths:
        result.excluded_by = ExclusionReason.NOT_SKILL_CENTRIC
        result.exclusion_note = "No regular SKILL.md manifest in the complete tree."
    elif result.forks_count > settings.maximum_forks_per_star * result.stars_count:
        result.excluded_by = ExclusionReason.FORKS_EXCEED_STARS
        result.exclusion_note = (
            f"{result.forks_count} forks against {result.stars_count} stars exceeds "
            f"{settings.maximum_forks_per_star} forks per star."
        )
    elif len(result.skill_package_paths) > settings.maximum_packages:
        result.excluded_by = ExclusionReason.CATALOG_SCALE
        result.exclusion_note = (
            f"{len(result.skill_package_paths)} packages exceed the catalog scale limit of {settings.maximum_packages}."
        )
    result.screening_complete = result.excluded_by is not None or confirmed
    return result


def eligible_upstreams(repositories: list[RepositorySnapshot], *, pilot: bool) -> list[RepositorySnapshot]:
    """Select retained upstreams; a pilot may also use pending candidates."""
    return [
        item
        for item in repositories
        if item.tree_complete
        and item.repository.excluded_by is None
        and (item.repository.screening_complete or pilot)
    ]


def select_topics(client, config: ExperimentSettings, root: Path, errors: list[dict]) -> list[str]:
    """Derive search topics from the configured seed repositories."""
    topics = Counter()
    seed_topics = {}
    for repository in config.retrieval.topic_seeds:
        try:
            metadata = client.get(f"repos/{repository}").body
            seed_topics[repository] = metadata.get("topics", [])
            topics.update(sorted(set(seed_topics[repository])))
        except (ApiError, KeyError, ValueError) as error:
            record_error(errors, "seed_topics", repository, error)
    selected = [
        topic
        for topic, count in sorted(topics.items(), key=lambda item: (-item[1], item[0]))
        if config.retrieval.topic_contains.lower() in topic.lower()
    ][: config.retrieval.maximum_topics]
    write_json(
        root / "topics.json",
        {"seeds": seed_topics, "frequencies": dict(topics), "selected": selected},
    )
    return selected


def fork_bands(client, query: str, low: int, high: int | None) -> list[str]:
    """Split the fork range of an intent query until every band fits under the search cap.

    One probe request per band reads the total count; a band is split in the
    middle, or at twice its lower bound when it is open ended (ADR 0044).
    """
    qualifier = f"forks:>={low}" if high is None else f"forks:{low}..{high - 1}"
    probe = "search/repositories?" + urlencode({"q": f"{query} {qualifier} fork:false", "per_page": 1})
    total = client.get(probe).body["total_count"]
    if total <= SEARCH_CAP or (high is not None and high - low <= 1):
        return [qualifier]
    middle = low * 2 if high is None else (low + high) // 2
    return fork_bands(client, query, low, middle) + fork_bands(client, query, middle, high)


def discover(
    client, config: ExperimentSettings, root: Path, limit: int | None, errors: list[dict]
) -> dict[str, list[RetrievalEvidence]]:
    """Combine intent and manifest queries without losing channel overlap."""
    topics = select_topics(client, config, root, errors)
    candidates, coverage, queries = {}, [], []
    for query in [*[f"topic:{topic}" for topic in topics], *config.retrieval.description_queries]:
        try:
            bands = fork_bands(client, query, config.screening.minimum_forks, None)
        except (ApiError, KeyError, ValueError) as error:
            record_error(errors, "search", query, error)
            coverage.append({"channel": "intent", "query": query, "complete": False, "stop_reason": "error"})
            continue
        queries += [(RetrievalChannel.INTENT, f"{query} {band} fork:false") for band in bands]
    queries += [(RetrievalChannel.MANIFEST, query) for query in config.retrieval.manifest_queries]
    for channel, query in queries:
        route = "repositories" if channel == RetrievalChannel.INTENT else "code"
        endpoint = f"search/{route}?" + urlencode({"q": query, "per_page": config.github.per_page})
        logger.info("Searching %s: %s", channel, query)
        try:
            hits, report = collect_pages(client, endpoint, key="items", limit=limit)
        except (ApiError, KeyError, ValueError) as error:
            record_error(errors, "search", query, error)
            coverage.append({"channel": channel.value, "query": query, "complete": False, "stop_reason": "error"})
            continue
        coverage.append({"channel": channel.value, "query": query, **report})
        for hit in hits:
            repository = hit if channel == RetrievalChannel.INTENT else hit["repository"]
            name = repository["full_name"].lower()
            evidence = RetrievalEvidence(channel=channel, source=query, path=hit.get("path"))
            if evidence not in candidates.setdefault(name, []):
                candidates[name].append(evidence)
    for pointer in config.retrieval.registry_pointers:
        candidates.setdefault(pointer.repository.lower(), []).append(
            RetrievalEvidence(channel=RetrievalChannel.MANIFEST, source=pointer.source_url)
        )
    write_json(root / "search_coverage.json", coverage)
    write_jsonl(
        root / "discovered.jsonl",
        [
            {"full_name": name, "evidence": [item.model_dump(mode="json") for item in evidence]}
            for name, evidence in sorted(candidates.items())
        ],
    )
    return candidates


def fetch_candidate_metadata(
    client, candidates: dict[str, list[RetrievalEvidence]], errors: list[dict], skips: list[dict]
) -> list[dict]:
    """Read repository metadata, merging evidence of renamed duplicates by GitHub ID.

    A candidate that has disappeared since the search (HTTP 404) is recorded as
    a skip rather than an error (ADR 0044). Rows are ordered by fork count, then
    name, so that bounded runs process a deterministic prefix.
    """
    by_id = {}
    for index, (name, evidence) in enumerate(candidates.items(), start=1):
        if index == 1 or index % 100 == 0 or index == len(candidates):
            logger.info("Retrieving repository metadata %d/%d", index, len(candidates))
        try:
            response = client.get(f"repos/{name}")
            metadata = response.body
            if metadata.get("private") or metadata.get("fork"):
                continue
            identity = metadata["id"]
            if identity in by_id:
                existing = by_id[identity]["evidence"]
                existing.extend(item for item in evidence if item not in existing)
            else:
                by_id[identity] = {
                    "metadata": metadata,
                    "retrieved_at": response.retrieved_at,
                    "evidence": evidence,
                }
        except ApiError as error:
            if error.status == 404:
                skips.append({"full_name": name, "stage": "repository_metadata", "message": str(error)})
                logger.info("Skipped unavailable candidate %s", name)
            else:
                record_error(errors, "repository_metadata", name, error)
        except (KeyError, ValueError) as error:
            record_error(errors, "repository_metadata", name, error)
    return sorted(
        by_id.values(),
        key=lambda row: (-row["metadata"]["forks_count"], row["metadata"]["full_name"].lower()),
    )


def candidate_snapshot(row: dict) -> RepositorySnapshot:
    """Build the unscreened snapshot of one candidate from its metadata."""
    metadata = row["metadata"]
    name = metadata["full_name"]
    text = " ".join([name, metadata.get("description") or "", *metadata.get("topics", [])])
    repository = Repository(
        full_name=name,
        channels=sorted({item.channel for item in row["evidence"]}),
        retrieved_at=row["retrieved_at"],
        forks_count=metadata["forks_count"],
        stars_count=metadata["stargazers_count"],
        skill_package_paths=[],
        aggregator_keyword_hit=bool(AGGREGATOR_KEYWORDS.search(text.lower())),
    )
    return RepositorySnapshot(
        repository=repository,
        github_id=metadata["id"],
        default_branch=metadata["default_branch"],
        evidence=row["evidence"],
    )


def freeze_and_screen(client, snapshot: RepositorySnapshot, config: ExperimentSettings, root: Path) -> None:
    """Freeze the default branch, save the complete tree and screen the repository.

    A truncated tree is expanded only for a confirmed repository; any other
    candidate stays unmeasured and pending (ADR 0046).
    """
    name = snapshot.repository.full_name
    logger.info("Freezing and screening %s (%d forks)", name, snapshot.repository.forks_count)
    branch = client.get(f"repos/{name}/branches/{quote(snapshot.default_branch, safe='')}").body
    snapshot.default_branch_sha = branch["commit"]["sha"]
    commit = client.get(f"repos/{name}/git/commits/{snapshot.default_branch_sha}").body
    snapshot.tree_sha = commit["tree"]["sha"]
    confirmed = name.lower() in config.screening.confirmed_repositories()
    entries = complete_tree(client, name, snapshot.tree_sha, expand_truncated=confirmed)
    if entries is None:
        logger.info("Tree truncated and not expanded outside the cohort: %s", name)
        return
    write_jsonl(root / "trees" / f"{snapshot.github_id}.jsonl", entries)
    snapshot.tree_complete = True
    snapshot.repository = screen_repository(snapshot.repository, entries, config.screening)


def retrieve_repositories(
    client, config: ExperimentSettings, root: Path, *, limit: int | None
) -> list[RepositorySnapshot]:
    """Retrieve candidates and screen a deterministic, optionally bounded set."""
    errors, skips = [], []
    candidates = discover(client, config, root, limit, errors)
    ordered = fetch_candidate_metadata(client, candidates, errors, skips)
    write_jsonl(root / "candidate_skips.jsonl", skips)
    write_jsonl(
        root / "candidate_metadata.jsonl",
        [{**row, "evidence": [item.model_dump(mode="json") for item in row["evidence"]]} for row in ordered],
    )
    floor = config.screening.minimum_forks
    results = []
    for row in ordered[:limit]:
        snapshot = candidate_snapshot(row)
        repository = snapshot.repository
        try:
            if repository.forks_count < floor:
                repository.excluded_by = ExclusionReason.FORK_THRESHOLD
                repository.exclusion_note = f"Fewer than {floor} forks at retrieval."
                repository.screening_complete = True
            else:
                freeze_and_screen(client, snapshot, config, root)
        except (ApiError, KeyError, ValueError) as error:
            record_error(errors, "repository_tree", repository.full_name, error)
        results.append(snapshot)
    write_jsonl(root / "repositories.jsonl", results)
    write_jsonl(root / "repository_errors.jsonl", errors)
    search_coverage = read_json(root / "search_coverage.json")
    write_json(
        root / "repository_summary.json",
        {
            "discovered": len(candidates),
            "metadata_available": len(ordered),
            "unavailable": len(skips),
            "processed": len(results),
            "trees_complete": sum(item.tree_complete for item in results),
            "trees_truncated": sum(
                item.tree_sha is not None and not item.tree_complete for item in results
            ),
            "retained": sum(
                item.repository.screening_complete and item.repository.excluded_by is None
                for item in results
            ),
            "pending": sum(not item.repository.screening_complete for item in results),
            "excluded": dict(
                Counter(item.repository.excluded_by.value for item in results if item.repository.excluded_by)
            ),
            "errors": len(errors),
            "complete": not errors
            and len(results) == len(ordered)
            and all(item["complete"] for item in search_coverage),
        },
    )
    return results


def import_confirmed_repositories(source: Path, root: Path, config: ExperimentSettings) -> None:
    """Copy the confirmed upstreams from a candidate run without mutating it."""
    if source.resolve() == root.resolve():
        raise ValueError("Source and destination runs must differ.")
    confirmed = config.screening.confirmed_repositories()
    if not confirmed:
        raise ValueError("No confirmed repositories in the configuration.")
    snapshots = [RepositorySnapshot.model_validate(row) for row in read_jsonl(source / "repositories.jsonl")]
    names = [item.repository.full_name.lower() for item in snapshots]
    ids = [item.github_id for item in snapshots]
    if len(set(names)) != len(names) or len(set(ids)) != len(ids):
        raise ValueError("Duplicate repository identity in source evidence.")
    if confirmed - set(names):
        raise ValueError(f"Missing confirmed repositories: {sorted(confirmed - set(names))}")
    selected = [item for item in snapshots if item.repository.full_name.lower() in confirmed]
    for item in selected:
        check_frozen_evidence(source, item, config)
    provenance = {"source_run_id": source.name, "confirmed_repositories": sorted(confirmed)}
    manifest = root / "repository_selection.json"
    if manifest.exists():
        check_saved_selection(source, root, manifest, provenance, selected)
    write_json(manifest, provenance)
    for item in selected:
        name = f"trees/{item.github_id}.jsonl"
        (root / "trees").mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source / name, root / name)
    coverage = read_json(source / "search_coverage.json")
    write_json(root / "search_coverage.json", coverage)
    selected_ids = {item.github_id for item in selected}
    write_jsonl(
        root / "candidate_metadata.jsonl",
        [row for row in read_jsonl(source / "candidate_metadata.jsonl") if row["metadata"]["id"] in selected_ids],
    )
    write_jsonl(root / "repositories.jsonl", selected)
    write_jsonl(root / "repository_errors.jsonl", [])
    write_json(
        root / "repository_summary.json",
        {
            "source_run_id": source.name,
            "processed": len(selected),
            "trees_complete": len(selected),
            "retained": len(selected),
            "pending": 0,
            "excluded": {},
            "errors": 0,
            "complete": True,
            "source_search_complete": all(item["complete"] for item in coverage),
        },
    )


def check_frozen_evidence(source: Path, item: RepositorySnapshot, config: ExperimentSettings) -> None:
    """Require a complete tree that reproduces the saved measurement, then rescreen."""
    tree_file = source / f"trees/{item.github_id}.jsonl"
    entries = [TreeEntry.model_validate(row) for row in read_jsonl(tree_file)]
    if (
        not item.tree_complete
        or not item.tree_sha
        or not re.fullmatch(r"[0-9a-f]{40}", item.default_branch_sha or "")
        or not tree_file.exists()
        or measure_skill_centricity(entries, complete=True) != item.repository.skill_centricity
    ):
        raise ValueError(f"Incomplete or inconsistent frozen evidence: {item.repository.full_name}")
    item.repository = screen_repository(item.repository, entries, config.screening)
    if item.repository.excluded_by is not None or not item.repository.screening_complete:
        raise ValueError(f"Confirmed repository failed structural checks: {item.repository.full_name}")


def check_saved_selection(
    source: Path, root: Path, manifest: Path, provenance: dict, selected: list[RepositorySnapshot]
) -> None:
    """A repeated import must reproduce the selection already saved in the run."""
    saved = read_json(manifest)
    unchanged = (
        all(saved.get(key) == value for key, value in provenance.items())
        and read_jsonl(root / "repositories.jsonl") == [item.model_dump(mode="json") for item in selected]
        and all(
            read_jsonl(root / f"trees/{item.github_id}.jsonl") == read_jsonl(source / f"trees/{item.github_id}.jsonl")
            for item in selected
        )
    )
    if not unchanged:
        raise ValueError("Source evidence changed; use a new run ID.")
