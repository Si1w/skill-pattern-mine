"""Read and write the JSON and JSONL artifacts of a run."""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)


def record_error(errors: list[dict], stage: str, subject: str, error: Exception) -> None:
    """Preserve a failure separately from empty responses and screened exclusions."""
    logger.error("%s failed for %s: %s", stage, subject, error)
    errors.append({"stage": stage, "subject": subject, "error": str(error)})


def utcnow() -> str:
    """Return an aware UTC timestamp in ISO format."""
    return datetime.now(timezone.utc).isoformat()


def read_json(path: Path):
    """Read one JSON artifact."""
    return json.loads(path.read_text())


def write_json(path: Path, value) -> None:
    """Replace a JSON artifact atomically after serialization succeeds."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
    temporary.replace(path)


def read_jsonl(path: Path) -> list[dict]:
    """Read complete records, treating a missing optional artifact as empty."""
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def write_jsonl(path: Path, rows) -> None:
    """Replace a JSONL artifact without leaving partial records.

    Rows may be dictionaries or Pydantic models.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w") as stream:
        for row in rows:
            if hasattr(row, "model_dump"):
                row = row.model_dump(mode="json")
            stream.write(json.dumps(row, ensure_ascii=False) + "\n")
    temporary.replace(path)
