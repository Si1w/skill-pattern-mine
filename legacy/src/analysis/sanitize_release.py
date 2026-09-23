"""Build a sanitized public release artifact from analysis instances.

The analysis pipeline keeps public GitHub fork identifiers so the study can be
audited internally. This module creates a separate release view that
pseudonymizes fork-owner identifiers and redacts obvious secrets in text
fields while preserving all aggregate analysis fields.

Pseudonymization is deterministic: the same input always produces the same
UUID v5, so cross-file joins on modification_id remain valid after sanitization.

modification_id format: "{upstream}::{fork_owner}::{branch}"
Public form:            UUID v5 derived from the full modification_id string

Usage:
    uv run python -m analysis.sanitize_release
    uv run python -m analysis.sanitize_release --input data/analysis/instances.jsonl --out data/artifact/instances.public.jsonl
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import logging
import re
import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INPUT = ROOT / "data" / "analysis" / "instances.jsonl"
DEFAULT_OUT = ROOT / "data" / "artifact" / "instances.public.jsonl"
SALT = "skill-pattern-mine-public-artifact-v1"
_NAMESPACE = uuid.UUID(bytes=hashlib.sha256(SALT.encode()).digest()[:16])
LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
LOGGER = logging.getLogger(__name__)

SECRET_PATTERNS = [
    re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{20,}\b"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
    re.compile(r"(?i)\b(api[_-]?key|token|secret|password)\s*[:=]\s*['\"]?[^'\"\s,;}]+"),
]

LOCAL_PATH_PATTERNS = [
    re.compile(r"/Users/[^/\s]+"),
    re.compile(r"/home/[^/\s]+"),
    re.compile(r"(?i)\b[A-Z]:\\Users\\[^\\\s]+"),
]


def stable_uuid(value: str) -> str:
    """Return a deterministic UUID v5 string for the given value."""
    return str(uuid.uuid5(_NAMESPACE, value))


def digest(value: str, prefix: str) -> str:
    """Return a stable short pseudonym for one sensitive identifier."""
    payload = f"{SALT}:{prefix}:{value}".encode()
    return f"{prefix}-{hashlib.sha256(payload).hexdigest()[:12]}"


def pseudonymize_owner(owner: str) -> str:
    return digest(owner, "fork-owner")


def pseudonymize_sha(sha: str) -> str:
    return digest(sha, "sha")


def pseudonymize_modification_id(modification_id: str) -> str:
    """Replace modification_id with a stable UUID v5.

    Expects the format "{upstream}::{fork_owner}::{branch}". Returns the
    original string unchanged if it does not match.
    """
    if modification_id.count("::") != 2:
        return modification_id
    return stable_uuid(modification_id)


def redact_text(value: str) -> str:
    """Redact obvious secret values and private local user directories."""
    redacted = value
    for pattern in SECRET_PATTERNS:
        redacted = pattern.sub(
            lambda m: f"{m.group(1)}=<REDACTED>" if m.groups() else "<REDACTED>",
            redacted,
        )
    for pattern in LOCAL_PATH_PATTERNS:
        redacted = pattern.sub("<LOCAL_USER_PATH>", redacted)
    return redacted


def redact_any(value: Any) -> Any:
    """Recursively redact text while preserving JSON shape."""
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, list):
        return [redact_any(item) for item in value]
    if isinstance(value, dict):
        return {key: redact_any(item) for key, item in value.items()}
    return value


def sanitize_instance(instance: dict) -> dict:
    """Return the public-release view of one analysis instance (instances / msg_*)."""
    sanitized = redact_any(copy.deepcopy(instance))
    if mid := sanitized.get("modification_id"):
        sanitized["modification_id"] = pseudonymize_modification_id(mid)
    return sanitized


def sanitize_diff(diff: dict) -> dict:
    """Return the public-release view of one diff record (diffs.jsonl)."""
    sanitized = redact_any(copy.deepcopy(diff))
    if owner := sanitized.get("fork_owner"):
        sanitized["fork_owner"] = pseudonymize_owner(owner)
    if sha := sanitized.get("merge_base_sha"):
        sanitized["merge_base_sha"] = pseudonymize_sha(sha)
    if sha := sanitized.get("head_sha"):
        sanitized["head_sha"] = pseudonymize_sha(sha)
    for commit in sanitized.get("commits", []):
        if sha := commit.get("sha"):
            commit["sha"] = pseudonymize_sha(sha)
    return sanitized


def sanitize_fork(fork: dict) -> dict:
    """Return the public-release view of one fork record (forks.jsonl)."""
    sanitized = redact_any(copy.deepcopy(fork))
    owner = sanitized.get("owner", "")
    if owner:
        anon = pseudonymize_owner(owner)
        sanitized["owner"] = anon
        if full_name := sanitized.get("full_name"):
            sanitized["full_name"] = full_name.replace(owner, anon, 1)
        if clone_url := sanitized.get("clone_url"):
            sanitized["clone_url"] = clone_url.replace(f"/{owner}/", f"/{anon}/", 1)
    return sanitized


def read_jsonl(path: Path) -> Iterator[dict]:
    """Yield JSON rows from a JSONL file."""
    with path.open() as f:
        for line in f:
            if line.strip():
                yield json.loads(line)


def write_sanitized_jsonl(input_path: Path, out_path: Path, kind: str = "instance") -> int:
    """Write sanitized rows and return the number of rows written.

    kind: "instance" | "diff" | "fork"
    """
    sanitizers = {
        "instance": sanitize_instance,
        "diff": sanitize_diff,
        "fork": sanitize_fork,
    }
    sanitize = sanitizers[kind]
    out_path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with out_path.open("w") as f:
        for row in read_jsonl(input_path):
            f.write(json.dumps(sanitize(row), ensure_ascii=False) + "\n")
            count += 1
    return count


def main() -> None:
    """CLI entry point."""
    logging.basicConfig(level=logging.INFO, format=LOG_FORMAT)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--kind", choices=["instance", "diff", "fork"], default="instance")
    args = parser.parse_args()

    count = write_sanitized_jsonl(args.input, args.out, kind=args.kind)
    LOGGER.info("wrote %d sanitized rows to %s", count, args.out)


if __name__ == "__main__":
    main()
