"""Load and validate acquisition settings from the experiment YAML file."""

from pathlib import Path
from typing import Literal

import yaml
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field


class Settings(BaseModel):
    """Reject unknown settings so that misspelled parameters cannot be ignored."""

    model_config = ConfigDict(extra="forbid")


class GitHubSettings(Settings):
    """Request limits and API version."""

    api_version: str
    per_page: int = Field(ge=1, le=100)
    branch_scope: Literal["frozen_default_branch"]
    max_attempts: int = Field(default=3, ge=1, le=10)
    timeout_seconds: int = Field(default=60, ge=1, le=60)


class RegistryPointer(Settings):
    """A repository pointer with its public registry provenance."""

    repository: str = Field(pattern=r"^[\w.-]+/[\w.-]+$")
    source_url: str = Field(pattern=r"^https://")


class RetrievalSettings(Settings):
    """Discovery queries and deterministic acquisition ordering."""

    topic_seeds: list[str]
    topic_contains: str
    maximum_topics: int = Field(ge=1)
    description_queries: list[str] = Field(min_length=1)
    manifest_queries: list[str] = Field(min_length=1)
    registry_pointers: list[RegistryPointer] = Field(default_factory=list)
    fork_sort: Literal["newest", "oldest", "stargazers", "watchers"]


class ObservationSettings(Settings):
    """Observation bounds; collection may also retain metadata outside them."""

    timestamp_field: Literal["commit.committer.date"]
    timezone: Literal["UTC"]
    start: Literal["earliest_eligible_modification"]
    end_exclusive_cap: AwareDatetime
    cutoff_utc: AwareDatetime | None
    include_partial_final_month: Literal[True]


class RepositoryReview(Settings):
    """A recorded human assessment; never inferred from a keyword match."""

    is_aggregator: bool
    exclude: bool = False
    reason: str = Field(min_length=1)


class ScreeningSettings(Settings):
    """Formal inclusion requires a calibrated threshold and manual review."""

    minimum_forks: int = Field(ge=0)
    selection_mode: Literal["calibrated_ratio", "confirmed_reviews"] = "calibrated_ratio"
    sensitivity_fork_thresholds: list[int]
    skill_centricity_metric: Literal["tracked_package_blobs_over_all_tracked_blobs"]
    skill_centricity_threshold: float | None = Field(ge=0, le=1)
    reviews: dict[str, RepositoryReview] = Field(default_factory=dict)


class AnalysisSettings(Settings):
    """Approved policy reserved for the later monthly analysis."""

    unresolved_upstream_policy: Literal["exclude_from_main"]
    analyze_excluded_intervals: Literal[False]


class ExtractionSettings(Settings):
    """Limits and operational rules for monthly endpoint extraction."""

    maximum_blob_bytes: int = Field(default=10485760, ge=1)
    lineage: Literal["first_parent"] = "first_parent"
    origin_policy: Literal["conservative_overlap"] = "conservative_overlap"
    history_backend: Literal["github_api", "pydriller"] = "github_api"
    git_timeout_seconds: int = Field(default=180, ge=1)


class ExperimentSettings(Settings):
    """The configuration frozen into every acquisition run."""

    dataset: str
    seed: int
    github: GitHubSettings
    retrieval: RetrievalSettings
    observation: ObservationSettings
    screening: ScreeningSettings
    analysis: AnalysisSettings
    extraction: ExtractionSettings = Field(default_factory=ExtractionSettings)


def load_config(path: Path) -> ExperimentSettings:
    """Read YAML safely and validate all known fields."""
    return ExperimentSettings.model_validate(yaml.safe_load(path.read_text()))


def load_saved_config(snapshot: dict) -> ExperimentSettings:
    """Read historical settings without retired output paths or artifact changes."""
    return ExperimentSettings.model_validate(
        {key: value for key, value in snapshot.items() if key != "outputs"}
    )
