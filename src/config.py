"""Load and validate experiment settings from the YAML file."""

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
    """Observation bounds; months are assigned by UTC committer time (ADR 0015)."""

    end_exclusive_cap: AwareDatetime
    cutoff_utc: AwareDatetime | None = Field(
        description="Fixed cutoff; None freezes the acquisition start time instead."
    )


class RepositoryReview(Settings):
    """A recorded human assessment; never inferred from a keyword match."""

    is_aggregator: bool
    exclude: bool = False
    reason: str = Field(min_length=1)

    @property
    def approved(self) -> bool:
        """A repository enters the confirmed cohort only with an explicit approval."""
        return not self.exclude and not self.is_aggregator


class ScreeningSettings(Settings):
    """Structural thresholds plus the human reviews that define the cohort (ADR 0042)."""

    minimum_forks: int = Field(ge=0)
    sensitivity_fork_thresholds: list[int]
    reviews: dict[str, RepositoryReview] = Field(default_factory=dict)

    @property
    def lowest_fork_threshold(self) -> int:
        """Candidates are kept down to the lowest sensitivity threshold."""
        return min([self.minimum_forks, *self.sensitivity_fork_thresholds])

    def review_for(self, full_name: str) -> RepositoryReview | None:
        """Look up a review by repository name, ignoring case."""
        for name, review in self.reviews.items():
            if name.lower() == full_name.lower():
                return review
        return None

    def approved_repositories(self) -> set[str]:
        """Lower case names of the repositories approved by human review."""
        return {name.lower() for name, review in self.reviews.items() if review.approved}


class ExtractionSettings(Settings):
    """Limits for monthly endpoint extraction from local Git history."""

    maximum_blob_bytes: int = Field(default=10485760, ge=1)
    git_timeout_seconds: int = Field(default=180, ge=1)


class ExperimentSettings(Settings):
    """The configuration frozen into every run."""

    dataset: str
    seed: int
    github: GitHubSettings
    retrieval: RetrievalSettings
    observation: ObservationSettings
    screening: ScreeningSettings
    extraction: ExtractionSettings = Field(default_factory=ExtractionSettings)


def load_config(path: Path) -> ExperimentSettings:
    """Read YAML safely and validate all known fields."""
    return ExperimentSettings.model_validate(yaml.safe_load(path.read_text()))
