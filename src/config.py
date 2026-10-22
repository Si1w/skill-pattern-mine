"""Load and validate experiment settings from the YAML file."""

from pathlib import Path
from typing import Literal

import yaml
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator


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
    """The exclusive upper bound of the observation window (ADRs 0015 and 0045).

    Months are assigned by UTC committer time. A run freezes the earlier of
    this cutoff and its own start time, so a run can never observe the future.
    """

    cutoff_utc: AwareDatetime


class ScreeningSettings(Settings):
    """The fork threshold plus the confirmed repositories that define the cohort (ADR 0042).

    The list holds the human decisions of ADRs 0025 and 0026; it is never inferred
    from keywords or measured ratios. Candidates outside the list stay pending.
    """

    minimum_forks: int = Field(ge=0)
    maximum_forks_per_star: float = Field(gt=0, description="Forks above stars signal a fork campaign (ADR 0048).")
    maximum_packages: int = Field(ge=1, description="More packages than this is catalog scale (ADR 0048).")
    repositories: list[str] = Field(default_factory=list)

    @field_validator("repositories")
    @classmethod
    def unique_names(cls, names: list[str]) -> list[str]:
        """Reject a repository listed twice, ignoring case."""
        lowered = [name.lower() for name in names]
        if len(set(lowered)) != len(lowered):
            raise ValueError("A confirmed repository is listed more than once.")
        return names

    def confirmed_repositories(self) -> set[str]:
        """Lower case names of the confirmed repositories."""
        return {name.lower() for name in self.repositories}


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
