"""Validated inputs and run settings for rebuttal analysis."""

from pydantic import BaseModel, ConfigDict, Field


class Settings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    blind_sample_size: int = Field(default=293, ge=1)
    seed: int = 42
    bootstrap_repetitions: int = Field(default=2000, ge=20)


class Instance(BaseModel):
    model_config = ConfigDict(extra="forbid")
    modification_id: str
    upstream: str
    commit_messages: list[str]
    patch: str
    labels: list[str]


class RunRecord(BaseModel):
    run_id: str
    started_at: str
    settings: Settings
    num_samples: int | None
    source_sha256: dict[str, str]
    git_commit: str | None = None
    git_status: str = "unavailable: workspace has no Git metadata"
    status: str = "running"


class BlindTask(BaseModel):
    task_id: str
    patch: str
    labels: list[str] | None = None
    evidence: str = ""
    uncertainty: str = ""
