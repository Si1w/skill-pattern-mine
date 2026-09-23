"""Read GitHub REST responses through gh and preserve replayable evidence."""

import hashlib
import json
import logging
import os
import re
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

logger = logging.getLogger(__name__)


class ApiError(RuntimeError):
    """An API response could not establish the requested data."""

    def __init__(self, message: str, *, status: int | None = None):
        super().__init__(message)
        self.status = status


class NoCommonAncestor(ApiError):
    """GitHub explicitly rejected a comparison of two unrelated frozen histories."""

    def __init__(self, endpoint: str, message: str, retrieved_at: str):
        super().__init__(message)
        self.endpoint = endpoint
        self.retrieved_at = retrieved_at


def utcnow() -> str:
    """Return an aware UTC acquisition timestamp."""
    return datetime.now(timezone.utc).isoformat()


def write_json(path: Path, value) -> None:
    """Replace a JSON artifact atomically after serialization succeeds."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
    temporary.replace(path)


def write_jsonl(path: Path, rows) -> None:
    """Replace a JSONL artifact without leaving partial records."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w") as stream:
        for row in rows:
            if hasattr(row, "model_dump"):
                row = row.model_dump(mode="json")
            stream.write(json.dumps(row, ensure_ascii=False) + "\n")
    temporary.replace(path)


def read_jsonl(path: Path) -> list[dict]:
    """Read complete records, allowing a missing optional artifact."""
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def api_path(value: str) -> str:
    """Allow pagination to the GitHub API only, without URL credentials."""
    if value.startswith("https://"):
        parsed = urlsplit(value)
        if parsed.netloc != "api.github.com" or parsed.fragment:
            raise ApiError("Pagination left the GitHub API origin.")
        return parsed.path.lstrip("/") + ("?" + parsed.query if parsed.query else "")
    if "://" in value or value.startswith(("/", "-")):
        raise ApiError("Invalid GitHub API endpoint.")
    return value


def no_common_ancestor(endpoint: str, body) -> bool:
    """Match an explicit comparison rejection to the exact requested commit pair."""
    pair = re.fullmatch(
        r"repos/[^/]+/[^/]+/compare/([0-9a-f]{40})\.\.\.([0-9a-f]{40})(?:\?.*)?",
        endpoint,
    )
    return bool(
        pair and isinstance(body, dict)
        and body.get("message") == f"No common ancestor between {pair[1]} and {pair[2]}."
    )


def redact(value):
    """Remove credential fields that can appear in repository responses."""
    if isinstance(value, dict):
        return {
            key: redact(item)
            for key, item in value.items()
            if key.lower()
            not in {"token", "temp_clone_token", "access_token", "authorization"}
        }
    if isinstance(value, list):
        return [redact(item) for item in value]
    return value


@dataclass
class Page:
    """A successful response with retrieval time and pagination headers."""

    body: dict | list
    headers: dict[str, str]
    retrieved_at: str

    @property
    def next_path(self) -> str | None:
        """Read the next link; short and empty pages can still have successors."""
        for item in self.headers.get("link", "").split(","):
            match = re.search(r'<([^>]+)>;\s*rel="next"', item)
            if match:
                return api_path(match.group(1))
        return None


class GitHubClient:
    """Cache successful responses and 404 evidence within one run."""

    def __init__(
        self,
        root: Path,
        *,
        api_version: str,
        max_attempts: int = 3,
        timeout_seconds: int = 60,
        offline: bool = False,
        wait_for_rate_limit: bool = False,
    ):
        self.root = root
        self.api_version = api_version
        self.max_attempts = max_attempts
        self.timeout_seconds = timeout_seconds
        self.offline = offline
        self.wait_for_rate_limit = wait_for_rate_limit
        self._quota_reset = 0.0
        self.requests = 0
        self.cache_hits = 0
        (root / "raw").mkdir(parents=True, exist_ok=True)

    def get(self, endpoint: str) -> Page:
        """Replay successes and frozen 404 failures without treating missing data as empty."""
        endpoint = api_path(endpoint)
        digest = hashlib.sha256(f"{self.api_version}:{endpoint}".encode()).hexdigest()
        path = self.root / "raw" / f"{digest}.json"
        if path.exists():
            saved = json.loads(path.read_text())
            if (
                saved["endpoint"] != endpoint
                or saved["api_version"] != self.api_version
            ):
                raise ApiError("Cached request identity does not match.")
            self.cache_hits += 1
            if saved["status"] == 404 and no_common_ancestor(endpoint, saved["body"]):
                raise NoCommonAncestor(endpoint, saved["body"]["message"], saved["retrieved_at"])
            if saved["status"] != 200:
                raise ApiError(
                    f"GitHub GET failed (status {saved['status']}, attempt 1): {endpoint}",
                    status=saved["status"],
                )
            return Page(saved["body"], saved["headers"], saved["retrieved_at"])
        if self.offline:
            raise ApiError(f"Offline cache miss: {endpoint}")
        attempt = 0
        while attempt < self.max_attempts:
            if self.wait_for_rate_limit and self._quota_reset > time.time():
                self._wait_for_quota(self._quota_reset - time.time())
                self._quota_reset = 0.0
            attempt += 1
            self.requests += 1
            status, headers, body = 0, {}, {}
            captured_at = utcnow()
            try:
                result = subprocess.run(
                    [
                        "gh",
                        "api",
                        "--hostname",
                        "github.com",
                        "--method",
                        "GET",
                        "--include",
                        "--header",
                        "Accept: application/vnd.github+json",
                        "--header",
                        f"X-GitHub-Api-Version: {self.api_version}",
                        endpoint,
                    ],
                    capture_output=True,
                    text=True,
                    timeout=self.timeout_seconds,
                    env={**os.environ, "GH_PROMPT_DISABLED": "1", "GH_PAGER": "cat"},
                )
                raw_headers, separator, raw_body = result.stdout.replace(
                    "\r\n", "\n"
                ).partition("\n\n")
                if separator and raw_headers.startswith("HTTP/"):
                    status = int(raw_headers.splitlines()[0].split()[1])
                    headers = {
                        key.lower(): value.strip()
                        for line in raw_headers.splitlines()[1:]
                        if ":" in line
                        for key, value in [line.split(":", 1)]
                    }
                    body = redact(json.loads(raw_body))
                unrelated = status == 404 and no_common_ancestor(endpoint, body)
                if (result.returncode == 0 and status == 200) or status == 404:
                    kept = {
                        key: value
                        for key, value in headers.items()
                        if key
                        in {
                            "link",
                            "etag",
                            "date",
                            "x-github-request-id",
                            "x-ratelimit-remaining",
                            "x-ratelimit-reset",
                            "x-github-api-version-selected",
                        }
                    }
                    write_json(
                        path,
                        {
                            "endpoint": endpoint,
                            "api_version": self.api_version,
                            "status": status,
                            "retrieved_at": captured_at,
                            "headers": kept,
                            "body": body,
                        },
                    )
                    self._journal(endpoint, captured_at, status, attempt)
                    if headers.get("x-ratelimit-remaining") == "0":
                        self._quota_reset = float(headers.get("x-ratelimit-reset", 0)) + 1
                    if unrelated:
                        raise NoCommonAncestor(endpoint, body["message"], captured_at)
                    if status == 404:
                        raise ApiError(
                            f"GitHub GET failed (status 404, attempt 1): {endpoint}",
                            status=404,
                        )
                    return Page(body, kept, captured_at)
            except FileNotFoundError as error:
                raise ApiError(
                    "The gh CLI is required for live acquisition."
                ) from error
            except (subprocess.TimeoutExpired, ValueError):
                status = 0
            self._journal(endpoint, captured_at, status, attempt)
            message = str(body.get("message", "")) if isinstance(body, dict) else ""
            rate_limited = status == 429 or (
                status == 403
                and (
                    headers.get("x-ratelimit-remaining") == "0"
                    or "rate limit" in message.lower()
                    or "retry-after" in headers
                )
            )
            retryable = status == 0 or status >= 500 or rate_limited
            if rate_limited and self.wait_for_rate_limit:
                delay = max(1, float(headers.get("retry-after", 60)))
                if headers.get("x-ratelimit-remaining") == "0":
                    delay = max(delay, float(headers.get("x-ratelimit-reset", 0)) - time.time() + 1)
                self._wait_for_quota(delay)
                attempt -= 1
                continue
            if not retryable or attempt == self.max_attempts:
                raise ApiError(
                    f"GitHub GET failed (status {status}, attempt {attempt}): {endpoint}",
                    status=status,
                )
            delay = 2 ** (attempt - 1)
            if rate_limited:
                delay = max(delay, float(headers.get("retry-after", 60)))
                if headers.get("x-ratelimit-remaining") == "0":
                    delay = max(
                        delay,
                        float(headers.get("x-ratelimit-reset", 0)) - time.time() + 1,
                    )
            if delay > 60:
                raise ApiError(f"GitHub rate limit requires later resume: {endpoint}")
            logger.warning(
                "Retrying GitHub status %s in %.0f seconds: %s", status, delay, endpoint
            )
            time.sleep(delay)
        raise ApiError(f"No response: {endpoint}")

    def _wait_for_quota(self, delay: float) -> None:
        """Pause full acquisition in short intervals without losing its request."""
        logger.warning("Waiting %.0f seconds for GitHub quota renewal", delay)
        while delay > 0:
            interval = min(60, delay)
            time.sleep(interval)
            delay -= interval

    def _journal(
        self, endpoint: str, captured_at: str, status: int, attempt: int
    ) -> None:
        """Record request outcomes without credentials or response bodies."""
        with (self.root / "requests.jsonl").open("a") as stream:
            stream.write(
                json.dumps(
                    {
                        "endpoint": endpoint,
                        "retrieved_at": captured_at,
                        "status": status,
                        "attempt": attempt,
                    }
                )
                + "\n"
            )


def collect_pages(
    client, endpoint: str, *, key: str | None = None, limit: int | None = None
) -> tuple[list, dict]:
    """Collect bounded pages and report why enumeration stopped."""
    if limit is not None and limit < 1:
        raise ValueError("The sample limit must be positive.")
    rows, visited = [], set()
    total = None
    incomplete = False
    while endpoint:
        if endpoint in visited:
            raise ApiError("Pagination contains a repeated link.")
        visited.add(endpoint)
        response = client.get(endpoint)
        body = response.body
        batch = body[key] if key else body
        if not isinstance(batch, list):
            raise ApiError(f"Expected an API list: {endpoint}")
        if isinstance(body, dict):
            total = body.get("total_count", total)
            incomplete = incomplete or body.get("incomplete_results", False)
        available = None if limit is None else limit - len(rows)
        rows.extend(batch if available is None else batch[:available])
        next_path = response.next_path
        if (
            limit is not None
            and len(rows) >= limit
            and (next_path or len(batch) > available)
        ):
            reason = "sample_limit"
            break
        if total is not None and total > 1000 and (not next_path or len(rows) >= 1000):
            reason = "search_limit"
            break
        if not next_path:
            reason = (
                "incomplete_response"
                if incomplete or (total is not None and len(rows) != total)
                else "exhausted"
            )
            break
        endpoint = next_path
    return rows, {
        "complete": reason == "exhausted",
        "stop_reason": reason,
        "pages": len(visited),
        "returned": len(rows),
        "total_count": total,
        "incomplete_results": incomplete,
    }
