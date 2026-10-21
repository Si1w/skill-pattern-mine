"""Read GitHub REST responses through gh and preserve replayable evidence."""

import hashlib
import json
import logging
import os
import re
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

from src.storage import utcnow, write_json

logger = logging.getLogger(__name__)

KEPT_HEADERS = {
    "link",
    "etag",
    "date",
    "x-github-request-id",
    "x-ratelimit-remaining",
    "x-ratelimit-reset",
    "x-github-api-version-selected",
}
CREDENTIAL_FIELDS = {"token", "temp_clone_token", "access_token", "authorization"}


class ApiError(RuntimeError):
    """An API response could not establish the requested data."""

    def __init__(self, message: str, *, status: int | None = None):
        super().__init__(message)
        self.status = status


class NoCommonAncestor(ApiError):
    """GitHub explicitly rejected a comparison of two unrelated frozen histories."""

    def __init__(self, endpoint: str, message: str, retrieved_at: str):
        super().__init__(message, status=404)
        self.endpoint = endpoint
        self.retrieved_at = retrieved_at


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
        pair
        and isinstance(body, dict)
        and body.get("message") == f"No common ancestor between {pair[1]} and {pair[2]}."
    )


def redact(value):
    """Remove credential fields that can appear in repository responses."""
    if isinstance(value, dict):
        return {
            key: redact(item)
            for key, item in value.items()
            if key.lower() not in CREDENTIAL_FIELDS
        }
    if isinstance(value, list):
        return [redact(item) for item in value]
    return value


def parse_response(stdout: str) -> tuple[int, dict[str, str], dict | list]:
    """Split the gh output into status, lower case headers and a redacted body.

    Output without an HTTP status line is reported as status 0, which the
    client treats as a transient failure.
    """
    raw_headers, separator, raw_body = stdout.replace("\r\n", "\n").partition("\n\n")
    if not separator or not raw_headers.startswith("HTTP/"):
        return 0, {}, {}
    lines = raw_headers.splitlines()
    status = int(lines[0].split()[1])
    headers = {}
    for line in lines[1:]:
        if ":" in line:
            key, value = line.split(":", 1)
            headers[key.lower()] = value.strip()
    return status, headers, redact(json.loads(raw_body))


def rate_limit_delay(headers: dict[str, str]) -> float:
    """Seconds until the quota is usable again, from the response headers."""
    delay = max(1.0, float(headers.get("retry-after", 60)))
    if headers.get("x-ratelimit-remaining") == "0":
        delay = max(delay, float(headers.get("x-ratelimit-reset", 0)) - time.time() + 1)
    return delay


def is_rate_limited(status: int, headers: dict[str, str], body) -> bool:
    """GitHub signals exhausted quota with 429, or 403 plus a rate limit hint."""
    message = str(body.get("message", "")).lower() if isinstance(body, dict) else ""
    return status == 429 or (
        status == 403
        and (
            headers.get("x-ratelimit-remaining") == "0"
            or "rate limit" in message
            or "retry-after" in headers
        )
    )


class GitHubClient:
    """Cache successful responses and 404 evidence within one run.

    Every endpoint is requested at most once per run. Successful responses and
    404 responses are saved under raw/ and replayed on later calls; other
    failures are retried with backoff and then raised.
    """

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
        self.requests = 0
        self.cache_hits = 0
        self._quota_reset = 0.0
        (root / "raw").mkdir(parents=True, exist_ok=True)

    def get(self, endpoint: str) -> Page:
        """Replay a saved response or fetch, save and return a live one."""
        endpoint = api_path(endpoint)
        path = self._cache_path(endpoint)
        if path.exists():
            self.cache_hits += 1
            return self._replay(endpoint, json.loads(path.read_text()))
        if self.offline:
            raise ApiError(f"Offline cache miss: {endpoint}")
        return self._fetch(endpoint, path)

    def _cache_path(self, endpoint: str) -> Path:
        digest = hashlib.sha256(f"{self.api_version}:{endpoint}".encode()).hexdigest()
        return self.root / "raw" / f"{digest}.json"

    def _replay(self, endpoint: str, saved: dict) -> Page:
        """Return a saved success, or raise the saved 404 exactly as it was recorded."""
        if saved["endpoint"] != endpoint or saved["api_version"] != self.api_version:
            raise ApiError("Cached request identity does not match.")
        if saved["status"] == 200:
            return Page(saved["body"], saved["headers"], saved["retrieved_at"])
        self._raise_not_found(endpoint, saved["body"], saved["retrieved_at"])

    def _raise_not_found(self, endpoint: str, body, retrieved_at: str):
        if no_common_ancestor(endpoint, body):
            raise NoCommonAncestor(endpoint, body["message"], retrieved_at)
        raise ApiError(f"GitHub GET failed (status 404, attempt 1): {endpoint}", status=404)

    def _fetch(self, endpoint: str, path: Path) -> Page:
        """Request until success, a 404, or the retry budget is spent."""
        attempt = 0
        while attempt < self.max_attempts:
            if self.wait_for_rate_limit and self._quota_reset > time.time():
                self._wait_for_quota(self._quota_reset - time.time())
                self._quota_reset = 0.0
            attempt += 1
            captured_at = utcnow()
            status, headers, body = self._request(endpoint)
            self._journal(endpoint, captured_at, status, attempt)
            if status in {200, 404}:
                kept = {key: value for key, value in headers.items() if key in KEPT_HEADERS}
                self._save(path, endpoint, status, captured_at, kept, body)
                if headers.get("x-ratelimit-remaining") == "0":
                    self._quota_reset = float(headers.get("x-ratelimit-reset", 0)) + 1
                if status == 200:
                    return Page(body, kept, captured_at)
                self._raise_not_found(endpoint, body, captured_at)
            rate_limited = is_rate_limited(status, headers, body)
            if rate_limited and self.wait_for_rate_limit:
                self._wait_for_quota(rate_limit_delay(headers))
                attempt -= 1  # Waiting for quota does not consume a retry.
                continue
            retryable = status == 0 or status >= 500 or rate_limited
            if not retryable or attempt == self.max_attempts:
                raise ApiError(
                    f"GitHub GET failed (status {status}, attempt {attempt}): {endpoint}",
                    status=status,
                )
            delay = 2 ** (attempt - 1)
            if rate_limited:
                delay = max(delay, rate_limit_delay(headers))
            if delay > 60:
                raise ApiError(f"GitHub rate limit requires later resume: {endpoint}")
            logger.warning("Retrying GitHub status %s in %.0f seconds: %s", status, delay, endpoint)
            time.sleep(delay)
        raise ApiError(f"No response: {endpoint}")

    def _request(self, endpoint: str) -> tuple[int, dict[str, str], dict | list]:
        """Run one gh call; timeouts and unparsable output become status 0."""
        self.requests += 1
        command = [
            "gh", "api", "--hostname", "github.com", "--method", "GET", "--include",
            "--header", "Accept: application/vnd.github+json",
            "--header", f"X-GitHub-Api-Version: {self.api_version}",
            endpoint,
        ]
        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
                env={**os.environ, "GH_PROMPT_DISABLED": "1", "GH_PAGER": "cat"},
            )
            status, headers, body = parse_response(result.stdout)
        except FileNotFoundError as error:
            raise ApiError("The gh CLI is required for live acquisition.") from error
        except (subprocess.TimeoutExpired, ValueError):
            return 0, {}, {}
        if status == 200 and result.returncode != 0:
            return 0, headers, body
        return status, headers, body

    def _save(self, path, endpoint, status, captured_at, headers, body) -> None:
        write_json(
            path,
            {
                "endpoint": endpoint,
                "api_version": self.api_version,
                "status": status,
                "retrieved_at": captured_at,
                "headers": headers,
                "body": body,
            },
        )

    def _wait_for_quota(self, delay: float) -> None:
        """Pause full acquisition in short intervals without losing its request."""
        logger.warning("Waiting %.0f seconds for GitHub quota renewal", delay)
        while delay > 0:
            interval = min(60, delay)
            time.sleep(interval)
            delay -= interval

    def _journal(self, endpoint: str, captured_at: str, status: int, attempt: int) -> None:
        """Record request outcomes without credentials or response bodies."""
        row = {"endpoint": endpoint, "retrieved_at": captured_at, "status": status, "attempt": attempt}
        with (self.root / "requests.jsonl").open("a") as stream:
            stream.write(json.dumps(row) + "\n")


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
        if limit is not None and len(rows) >= limit and (next_path or len(batch) > available):
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
