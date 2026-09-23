"""Read frozen Git histories and preserve evidence for offline extraction."""

import base64
import hashlib
import json
import logging
import os
import re
import subprocess
import tempfile
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from git import Repo, Tree
from git.exc import GitError
from pydriller import Repository

from src.domain import SourceCommit
from src.github import ApiError, Page, utcnow, write_json

logger = logging.getLogger(__name__)


def validate_history(rows: list[SourceCommit], head: str) -> dict[str, SourceCommit]:
    """Require exactly the complete graph reachable from the frozen head."""
    history = {row.sha: row for row in rows}
    if len(history) != len(rows) or head not in history:
        raise ApiError("Incomplete or repeated frozen Git ancestry.")
    pending, seen = [head], set()
    while pending:
        sha = pending.pop()
        if sha in seen:
            continue
        if sha not in history:
            raise ApiError("Missing parent in frozen Git ancestry.")
        seen.add(sha)
        pending.extend(history[sha].parent_shas)
    if seen != history.keys():
        raise ApiError("Git history contains commits outside the frozen ancestry.")
    return history


class LocalObjects:
    """Expose complete Git objects using the extractor's existing page interface."""

    def __init__(self, repo: Repo, maximum_blob_bytes: int = 10485760):
        self.repo = repo
        self.maximum_blob_bytes = maximum_blob_bytes

    def history(self, head: str, *, retain_commits: bool = False) -> tuple[dict, dict]:
        """Read all ancestors with PyDriller; account mappings remain unavailable."""
        rows, objects = [], {}
        for commit in Repository(
            self.repo.git_dir, only_in_branch=head
        ).traverse_commits():
            rows.append(
                SourceCommit(
                    sha=commit.hash,
                    tree_sha=self.repo.commit(commit.hash).tree.hexsha,
                    parent_shas=commit.parents,
                    author_date=commit.author_date,
                    committer_date=commit.committer_date,
                    message=commit.msg,
                )
            )
            if retain_commits:
                objects[commit.hash] = commit
        return validate_history(rows, head), objects

    def get(self, endpoint: str) -> Page:
        """Read full trees and blobs, including merge states and submodule pointers."""
        parsed = urlsplit(endpoint)
        route = parsed.path.split("/", 3)[3]
        query = parse_qs(parsed.query)
        if route.startswith("git/trees/"):
            tree = Tree(self.repo, bytes.fromhex(route.rsplit("/", 1)[1]), 0o40000, "")
            entries = tree.traverse() if query.get("recursive") == ["1"] else iter(tree)
            body = {
                "truncated": False,
                "tree": [
                    {
                        "path": item.path,
                        "sha": item.hexsha,
                        "mode": f"{item.mode:06o}",
                        "type": "commit" if item.mode == 0o160000 else item.type,
                    }
                    for item in entries
                ],
            }
        elif route.startswith("git/blobs/"):
            sha = route.rsplit("/", 1)[1]
            obj = self.repo.odb.stream(bytes.fromhex(sha))
            if obj.type != b"blob" or obj.size > self.maximum_blob_bytes:
                raise ApiError("Requested Git object is not a supported size blob.")
            raw = obj.read()
            body = {
                "sha": sha,
                "size": len(raw),
                "encoding": "base64",
                "content": base64.b64encode(raw).decode(),
            }
        elif route == "commits" and "sha" in query:
            options = (
                {"paths": ":(literal)" + query["path"][0]} if "path" in query else {}
            )
            body = [
                {"sha": c.hexsha}
                for c in self.repo.iter_commits(query["sha"][0], **options)
            ]
        else:
            raise ApiError(f"Unsupported local Git request: {endpoint}")
        return Page(body=body, headers={}, retrieved_at=utcnow())


class GitSource:
    """Fetch frozen objects once per reference, with a separate evidence cache.

    No repository checkout is performed. Temporary Git objects are removed on
    every exit; persisted histories and object pages support offline replay.
    """

    def __init__(
        self,
        root: Path,
        references: dict[str, str],
        *,
        timeout_seconds: int,
        maximum_blob_bytes: int,
        offline: bool = False,
    ):
        for name, head in references.items():
            if not re.fullmatch(r"[\w.-]+/[\w.-]+", name) or not re.fullmatch(
                r"[0-9a-f]{40}", head
            ):
                raise ValueError(
                    "Git acquisition requires repository names and frozen full SHAs."
                )
        self.root, self.references = root, references
        self.timeout_seconds = timeout_seconds
        self.maximum_blob_bytes, self.offline = maximum_blob_bytes, offline
        self.fetches = self.cache_hits = 0
        self.workspace_path = None
        self._temporary = self._repo = None
        self._fetched = set()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        try:
            if self._repo is not None:
                self._repo.close()
        finally:
            if self._temporary is not None:
                self._temporary.cleanup()

    def _objects(self, repository: str) -> LocalObjects:
        """Fetch complete ancestry without tags, prompts or a moving branch name."""
        if self.offline:
            raise ApiError(
                "Offline Git evidence is missing; network access is disabled."
            )
        if self._repo is None:
            self._temporary = tempfile.TemporaryDirectory(
                prefix="skill-pattern-mine-git-"
            )
            self.workspace_path = Path(self._temporary.name)
            self._repo = Repo.init(self.workspace_path, bare=True)
        if repository not in self._fetched:
            head = self.references[repository]
            logger.info("Fetching frozen Git history: %s %s", repository, head[:12])
            self.fetches += 1
            subprocess.run(
                [
                    "git",
                    "-C",
                    str(self._repo.git_dir),
                    "-c",
                    "gc.auto=0",
                    "fetch",
                    "--no-tags",
                    "--quiet",
                    f"https://github.com/{repository}.git",
                    head,
                ],
                check=True,
                capture_output=True,
                timeout=self.timeout_seconds,
                env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
            )
            if self._repo.commit(head).hexsha != head:
                raise ApiError("Git fetch did not resolve the frozen commit.")
            self._fetched.add(repository)
        return LocalObjects(self._repo, self.maximum_blob_bytes)

    def _read(self, repository: str, request: str, *, history: bool = False) -> Page:
        """Validate cache identity and keep local evidence distinct from API data."""
        if repository not in self.references:
            raise ApiError(
                "Git request references a repository outside the frozen inputs."
            )
        identity = {
            "provider": "pydriller",
            "repository": repository,
            "head": self.references[repository],
            "request": request,
        }
        digest = hashlib.sha256(
            json.dumps(identity, sort_keys=True).encode()
        ).hexdigest()
        path = self.root / f"{digest}.json"
        try:
            if path.exists():
                saved = json.loads(path.read_text())
                if saved["identity"] != identity:
                    raise ApiError("Local Git cache identity does not match.")
                self.cache_hits += 1
                return Page(saved["body"], {}, saved["retrieved_at"])
            objects = self._objects(repository)
            if history:
                rows, _ = objects.history(self.references[repository])
                page = Page(
                    [r.model_dump(mode="json") for r in rows.values()], {}, utcnow()
                )
            else:
                page = objects.get(request)
            write_json(
                path,
                {
                    "identity": identity,
                    "body": page.body,
                    "retrieved_at": page.retrieved_at,
                },
            )
            return page
        except (
            GitError,
            subprocess.SubprocessError,
            OSError,
            ValueError,
            KeyError,
        ) as error:
            raise ApiError(
                f"Git evidence failed for {repository}: {type(error).__name__}"
            ) from error

    def history(self, repository: str, head: str) -> dict[str, SourceCommit]:
        """Return validated complete history for precisely the requested reference."""
        if self.references.get(repository) != head:
            raise ApiError("Requested Git history differs from the frozen head.")
        page = self._read(repository, "history", history=True)
        try:
            return validate_history(
                [SourceCommit.model_validate(r) for r in page.body], head
            )
        except (TypeError, ValueError) as error:
            raise ApiError("Invalid cached Git ancestry.") from error

    def get(self, endpoint: str) -> Page:
        """Serve the tree, blob and path history requests used by PackageStore."""
        parts = urlsplit(endpoint).path.split("/", 3)
        if len(parts) != 4 or parts[0] != "repos":
            raise ApiError("Invalid local Git endpoint.")
        return self._read(f"{parts[1]}/{parts[2]}", endpoint)
