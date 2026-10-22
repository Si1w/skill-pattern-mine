"""Freeze run settings once and read them back on resume."""

import shutil
from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel

from src.config import ExperimentSettings
from src.storage import write_json

PROJECT_ROOT = Path(__file__).resolve().parents[1]


class RunRecord(BaseModel):
    """Settings frozen when a run is created; resumes must not change them."""

    schema_version: int = 1
    created_at: datetime
    cutoff_utc: datetime
    partial_final_month: bool
    pilot: bool
    num_samples: int | None
    config: ExperimentSettings
    source_run_id: str | None = None
    scope: str = "Repository screening and frozen fork divergence; no monthly observations or labels."
    provenance: dict = {}


def load_run(root: Path) -> RunRecord:
    """Read the frozen settings of an existing run."""
    return RunRecord.model_validate_json((root / "run.json").read_text())


def prepare_run(
    root: Path,
    config: ExperimentSettings,
    *,
    pilot: bool | None,
    limit: int | None,
    offline: bool,
    source_run_id: str | None = None,
) -> RunRecord:
    """Create the run record or validate a resume against the saved one."""
    path = root / "run.json"
    if path.exists():
        run = load_run(root)
        check_resume(run, config, pilot=pilot, limit=limit, source_run_id=source_run_id)
        return run
    if offline:
        raise ValueError("Offline replay requires an existing run.")
    if limit is not None and limit < 1:
        raise ValueError("--num_samples must be positive.")
    if pilot and limit is None:
        raise ValueError("An engineering pilot requires --num_samples.")
    now = datetime.now(timezone.utc)
    cutoff = min(now, config.observation.cutoff_utc).astimezone(timezone.utc)
    run = RunRecord(
        created_at=now,
        cutoff_utc=cutoff,
        partial_final_month=cutoff != cutoff.replace(day=1, hour=0, minute=0, second=0, microsecond=0),
        pilot=bool(pilot),
        num_samples=limit,
        config=config,
        source_run_id=source_run_id,
        provenance={"run_id": root.name, "source_directory": "source"},
    )
    copy_source_snapshot(root / "source")
    write_json(path, run.model_dump(mode="json"))
    return run


def check_resume(
    run: RunRecord,
    config: ExperimentSettings,
    *,
    pilot: bool | None,
    limit: int | None,
    source_run_id: str | None,
) -> None:
    """Reject resumes that would silently change frozen settings."""
    if run.config != config:
        raise ValueError("Configuration changed. Use the original config or a new run ID.")
    if pilot is not None and run.pilot != pilot:
        raise ValueError("Pilot mode cannot change within a run.")
    if limit is not None and run.num_samples != limit:
        raise ValueError("Sample bounds cannot change within a run.")
    if source_run_id is not None and source_run_id != run.source_run_id:
        raise ValueError("Source run cannot change within a run.")


def copy_source_snapshot(destination: Path) -> None:
    """Keep the exact source files and lockfile the run was created with."""
    files = [PROJECT_ROOT / "pyproject.toml", PROJECT_ROOT / "uv.lock"]
    for folder, pattern in (("src", "*.py"), ("eval", "*.py"), ("configs", "*.yaml")):
        files.extend(sorted((PROJECT_ROOT / folder).rglob(pattern)))
    for source in files:
        target = destination / source.relative_to(PROJECT_ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
