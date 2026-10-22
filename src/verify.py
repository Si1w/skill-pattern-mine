"""Validate saved acquisition artifacts without network access."""

import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path

from src.domain import ForkComparison, ForkExclusion, ForkSkip, RepositorySnapshot, TreeEntry
from src.github import no_common_ancestor
from src.preprocess import measure_skill_centricity
from src.run import RunRecord, load_run
from src.storage import read_json, read_jsonl, utcnow, write_json

FULL_SHA = re.compile(r"[0-9a-f]{40}")


@dataclass
class Artifacts:
    """Everything the fork and repository stages wrote for one run."""

    root: Path
    run: RunRecord
    repositories: list[RepositorySnapshot]
    comparisons: list[ForkComparison]
    exclusions: list[ForkExclusion]
    skips: list[ForkSkip]
    frozen: list[dict]
    errors: list[dict]
    search_coverage: list[dict]
    fork_coverage: list[dict]
    repository_summary: dict
    fork_summary: dict
    upstreams: dict[str, RepositorySnapshot] = field(init=False)

    def __post_init__(self):
        self.upstreams = {item.repository.full_name: item for item in self.repositories}

    @property
    def outcomes(self) -> list[ForkComparison | ForkExclusion]:
        """Every frozen fork that produced a comparison or an evidenced exclusion."""
        return [*self.comparisons, *self.exclusions]

    @property
    def measured(self) -> list[RepositorySnapshot]:
        return [item for item in self.repositories if item.tree_complete]

    @property
    def retained(self) -> list[RepositorySnapshot]:
        """Repositories that passed screening; a pilot may also collect pending ones."""
        return [
            item
            for item in self.measured
            if item.repository.excluded_by is None
            and (item.repository.screening_complete or self.run.pilot)
        ]

    @property
    def expected_upstreams(self) -> set[str]:
        return {item.repository.full_name for item in self.retained}

    @property
    def observed_upstreams(self) -> set[str]:
        return {item.fork.upstream for item in self.outcomes} | {item.upstream for item in self.skips}

    @property
    def outcome_pairs(self) -> set[tuple[str, int]]:
        return {(item.fork.upstream, item.github_id) for item in self.outcomes}

    @property
    def skip_pairs(self) -> set[tuple[str, int]]:
        return {(item.upstream, item.github_id) for item in self.skips}


def load_artifacts(root: Path) -> Artifacts:
    """Read and validate every saved artifact; missing optional files read as empty."""

    def optional_json(name: str, default):
        path = root / name
        return read_json(path) if path.exists() else default

    return Artifacts(
        root=root,
        run=load_run(root),
        repositories=[RepositorySnapshot.model_validate(row) for row in read_jsonl(root / "repositories.jsonl")],
        comparisons=[ForkComparison.model_validate(row) for row in read_jsonl(root / "comparisons.jsonl")],
        exclusions=[ForkExclusion.model_validate(row) for row in read_jsonl(root / "fork_exclusions.jsonl")],
        skips=[ForkSkip.model_validate(row) for row in read_jsonl(root / "fork_skips.jsonl")],
        frozen=read_jsonl(root / "forks.jsonl"),
        errors=read_jsonl(root / "repository_errors.jsonl") + read_jsonl(root / "fork_errors.jsonl"),
        search_coverage=optional_json("search_coverage.json", []),
        fork_coverage=optional_json("fork_coverage.json", []),
        repository_summary=optional_json("repository_summary.json", {}),
        fork_summary=optional_json("fork_summary.json", {}),
    )


# --- Checks; each returns True when the artifacts satisfy one acceptance rule ---


def both_discovery_channels_recorded(a: Artifacts) -> bool:
    """Intent and manifest searches both ran without error."""
    channels = {row["channel"] for row in a.search_coverage if row["stop_reason"] != "error"}
    return channels == {"intent", "manifest"}


def repositories_measured(a: Artifacts) -> bool:
    return bool(a.measured)


def both_stages_finished(a: Artifacts) -> bool:
    """Both summaries exist and the fork stage processed every upstream."""
    return (
        bool(a.repository_summary)
        and bool(a.fork_summary)
        and a.fork_summary.get("upstreams_processed") == a.fork_summary.get("upstreams")
    )


def tree_measurements_reproduce(a: Artifacts) -> bool:
    """Saved trees reproduce the saved package file ratios."""
    checks = []
    for item in a.measured:
        path = a.root / "trees" / f"{item.github_id}.jsonl"
        entries = [TreeEntry.model_validate(row) for row in read_jsonl(path)]
        checks.append(
            path.exists() and measure_skill_centricity(entries, complete=True) == item.repository.skill_centricity
        )
    return bool(checks) and all(checks)


def eligible_upstreams_compared(a: Artifacts) -> bool:
    return bool(a.expected_upstreams) and a.observed_upstreams == a.expected_upstreams


def forks_processed(a: Artifacts) -> bool:
    return bool(a.outcomes or a.skips)


def exclusion_evidence_matches(a: Artifacts) -> bool:
    """Every exclusion is backed by the saved 404 response for exactly that commit pair."""
    api_version = a.run.config.github.api_version
    for item in a.exclusions:
        digest = hashlib.sha256(f"{api_version}:{item.endpoint}".encode()).hexdigest()
        path = a.root / "raw" / f"{digest}.json"
        saved = read_json(path) if path.exists() else {}
        matches = (
            saved.get("status") == item.status
            and saved.get("endpoint") == item.endpoint
            and saved.get("api_version") == api_version
            and saved.get("retrieved_at") == item.retrieved_at.isoformat()
            and saved.get("body", {}).get("message") == item.message
            and f"/compare/{item.upstream_sha}...{item.fork.default_branch_sha}?" in item.endpoint
            and no_common_ancestor(item.endpoint, saved.get("body"))
        )
        if not matches:
            return False
    return True


def reused_comparisons_match(a: Artifacts) -> bool:
    """A reused comparison copies a complete source comparison of the same SHA pair."""
    sources = {(item.fork.upstream, item.fork.full_name): item for item in a.comparisons}
    hidden = {"fork", "github_id", "reused_from"}
    for item in a.comparisons:
        if item.reused_from is None:
            continue
        source = sources.get((item.fork.upstream, item.reused_from))
        if not (
            source is not None
            and source.reused_from is None
            and source.commits_complete
            and source.fork.default_branch_sha == item.fork.default_branch_sha
            and source.model_dump(exclude=hidden) == item.model_dump(exclude=hidden)
        ):
            return False
    return True


def skips_accounted_for(a: Artifacts) -> bool:
    """Skips are unique, counted in the summary, and frozen skips match forks.jsonl."""
    frozen_rows = {(row["upstream"], row["github_id"]): row["default_branch_sha"] for row in a.frozen}
    return (
        len(a.skip_pairs) == len(a.skips)
        and not (a.skip_pairs & a.outcome_pairs)
        and a.fork_summary.get("skipped_forks", 0) == len(a.skips)
        and all(item.upstream in a.expected_upstreams for item in a.skips)
        and all(
            item.default_branch_sha is None
            or frozen_rows.get((item.upstream, item.github_id)) == item.default_branch_sha
            for item in a.skips
        )
    )


def all_frozen_forks_accounted_for(a: Artifacts) -> bool:
    """Every frozen fork ended as a comparison, an exclusion or a later skip."""
    frozen_pairs = {(row["upstream"], row["github_id"]) for row in a.frozen}
    frozen_skips = {(item.upstream, item.github_id) for item in a.skips if item.default_branch_sha is not None}
    return (
        len(a.frozen) == len(frozen_pairs) == len(a.outcomes) + len(frozen_skips)
        and frozen_pairs == a.outcome_pairs | frozen_skips
    )


def no_acquisition_errors(a: Artifacts) -> bool:
    return not a.errors


def unique_repository_ids(a: Artifacts) -> bool:
    return len(a.upstreams) == len(a.repositories) == len({item.github_id for item in a.repositories})


def unique_forks_per_upstream(a: Artifacts) -> bool:
    return len(a.outcomes) == len(a.outcome_pairs)


def frozen_references_match(a: Artifacts) -> bool:
    """Comparisons use the frozen upstream SHA and a full fork SHA."""
    return all(
        item.fork.upstream in a.upstreams
        and a.upstreams[item.fork.upstream].default_branch_sha == item.upstream_sha
        and FULL_SHA.fullmatch(item.fork.default_branch_sha)
        for item in a.outcomes
    )


def commit_counts_consistent(a: Artifacts) -> bool:
    return all(
        len(item.commits) == item.ahead_by if item.commits_complete else len(item.commits) <= item.ahead_by
        for item in a.comparisons
    )


def sample_bounds_respected(a: Artifacts) -> bool:
    """A bounded run never exceeds its limit of repositories, forks or commits."""
    limit = a.run.num_samples
    if limit is None:
        return True
    imported = a.run.source_run_id is not None
    forks_per_upstream = {
        name: sum(item.fork.upstream == name for item in a.outcomes) + sum(item.upstream == name for item in a.skips)
        for name in a.observed_upstreams
    }
    return (
        (imported or len(a.repositories) <= limit)
        and all(count <= limit for count in forks_per_upstream.values())
        and all(len(item.commits) <= limit for item in a.comparisons)
    )


def confirmed_membership_matches(a: Artifacts) -> bool:
    """A run imported from a source run contains exactly the confirmed repositories, all retained."""
    confirmed = a.run.config.screening.confirmed_repositories()
    retained = {
        item.repository.full_name.lower()
        for item in a.measured
        if item.repository.screening_complete and item.repository.excluded_by is None
    }
    everything = {item.repository.full_name.lower() for item in a.repositories}
    return bool(confirmed) and confirmed == retained == everything


def fork_inventory_consistent(a: Artifacts) -> bool:
    return bool(a.fork_coverage) and all(
        not item.get("duplicate_rows", 0) and not item.get("creation_time_inversions", 0)
        for item in a.fork_coverage
    )


def enumeration_complete(a: Artifacts) -> bool:
    """Both stage summaries and every fork listing report complete coverage."""
    return (
        a.repository_summary.get("complete", False)
        and a.fork_summary.get("complete", False)
        and bool(a.fork_coverage)
        and all(item.get("complete", False) for item in a.fork_coverage)
    )


def screening_complete(a: Artifacts) -> bool:
    return all(item.repository.screening_complete for item in a.repositories)


ALWAYS = [
    both_discovery_channels_recorded,
    repositories_measured,
    both_stages_finished,
    tree_measurements_reproduce,
    eligible_upstreams_compared,
    forks_processed,
    exclusion_evidence_matches,
    reused_comparisons_match,
    skips_accounted_for,
    all_frozen_forks_accounted_for,
    no_acquisition_errors,
    unique_repository_ids,
    unique_forks_per_upstream,
    frozen_references_match,
    commit_counts_consistent,
    sample_bounds_respected,
    fork_inventory_consistent,
]
IMPORTED_ONLY = [confirmed_membership_matches]
FULL_RUN_ONLY = [enumeration_complete, screening_complete]


def verify_run(root: Path) -> dict:
    """Run every applicable check and write the acceptance report."""
    a = load_artifacts(root)
    checks = list(ALWAYS)
    if a.run.source_run_id is not None:
        checks += IMPORTED_ONLY
    if not a.run.pilot:
        checks += FULL_RUN_ONLY
    results = {check.__name__: bool(check(a)) for check in checks}
    report = {
        "status": "passed" if all(results.values()) else "failed",
        "checked_at": utcnow(),
        "purpose": "engineering_pilot" if a.run.pilot else "acquisition_validation",
        "checks": results,
        "repositories": len(a.repositories),
        "forks": len(a.comparisons),
        "frozen_forks": len(a.frozen),
        "excluded_forks": len(a.exclusions),
        "skipped_forks": len(a.skips),
        "reused_comparisons": sum(item.reused_from is not None for item in a.comparisons),
        "source_commits": sum(len(item.commits) for item in a.comparisons),
        "coverage_complete": a.repository_summary.get("complete", False) and a.fork_summary.get("complete", False),
        "discovery_coverage_complete": bool(a.search_coverage) and all(item["complete"] for item in a.search_coverage),
        "complete_comparisons": sum(item.commits_complete for item in a.comparisons),
        "formally_retained_repositories": sum(
            item.repository.screening_complete and item.repository.excluded_by is None for item in a.repositories
        ),
        "limitations": [
            "This validates acquisition, not monthly origin attribution or annotation.",
            "Pilot bounds do not define a representative sample.",
            "Divergence commits may predate or follow the observation cutoff; "
            "temporal selection belongs to monthly extraction.",
            "HTTP 404 skips are omitted from the available corpus; "
            "acceptance does not imply every listed fork was accessible.",
        ],
    }
    write_json(root / "acceptance.json", report)
    return report
