"""Read frozen Git histories and preserve evidence for offline extraction.

GitSource fetches each frozen reference once into a temporary bare repository
and answers four questions about it: the complete history, a complete tree,
the bytes of a blob, and the commits that touched a path. Every answer is
saved as JSON evidence so a later run can replay extraction offline.
"""

import base64
import hashlib
import json
import logging
import os
import re
import subprocess
import tempfile
from pathlib import Path

from git import Repo, Tree
from git.exc import GitError
from pydriller import Repository

from src.domain import SourceCommit, TreeEntry
from src.github import ApiError
from src.storage import read_json, utcnow, write_json

logger = logging.getLogger(__name__)

GITLINK_MODE = 0o160000


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


# --- Local reads on a GitPython repository ---------------------------------


def read_history(repo: Repo, head: str) -> list[SourceCommit]:
    """Read all ancestors with PyDriller; GitHub account logins stay unavailable."""
    rows = []
    for commit in Repository(repo.git_dir, only_in_branch=head).traverse_commits():
        rows.append(
            SourceCommit(
                sha=commit.hash,
                tree_sha=repo.commit(commit.hash).tree.hexsha,
                parent_shas=commit.parents,
                author_date=commit.author_date,
                committer_date=commit.committer_date,
                message=commit.msg,
            )
        )
    return rows


def read_tree(repo: Repo, tree_sha: str) -> list[TreeEntry]:
    """Read a complete recursive tree, reporting submodule pointers as commits."""
    tree = Tree(repo, bytes.fromhex(tree_sha), 0o40000, "")
    return [
        TreeEntry(
            path=item.path,
            sha=item.hexsha,
            mode=f"{item.mode:06o}",
            type="commit" if item.mode == GITLINK_MODE else item.type,
        )
        for item in tree.traverse()
    ]


def read_blob(repo: Repo, sha: str, maximum_bytes: int) -> bytes:
    """Read blob bytes after checking the object type and size."""
    stream = repo.odb.stream(bytes.fromhex(sha))
    if stream.type != b"blob" or stream.size > maximum_bytes:
        raise ApiError("Requested Git object is not a supported size blob.")
    return stream.read()


def read_path_commits(repo: Repo, head: str, path: str | None) -> list[str]:
    """Commits reachable from head that touched the path; None means the whole tree."""
    options = {"paths": ":(literal)" + path} if path else {}
    return [commit.hexsha for commit in repo.iter_commits(head, **options)]


# --- Evidence cache around the local reads ---------------------------------


class GitSource:
    """Fetch frozen objects once per reference, with a separate evidence cache.

    No repository checkout is performed. The temporary bare repository is
    removed on exit; the saved evidence supports offline replay.
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
            if not re.fullmatch(r"[\w.-]+/[\w.-]+", name) or not re.fullmatch(r"[0-9a-f]{40}", head):
                raise ValueError("Git acquisition requires repository names and frozen full SHAs.")
        self.root = root
        self.references = references
        self.timeout_seconds = timeout_seconds
        self.maximum_blob_bytes = maximum_blob_bytes
        self.offline = offline
        self.fetches = 0
        self.cache_hits = 0
        self.workspace_path: Path | None = None
        self._temporary = None
        self._repo: Repo | None = None
        self._fetched: set[str] = set()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        try:
            if self._repo is not None:
                self._repo.close()
        finally:
            if self._temporary is not None:
                self._temporary.cleanup()

    # Public reads. Each is cached by repository, frozen head and request.

    def history(self, repository: str, head: str) -> dict[str, SourceCommit]:
        """Return the validated complete history of precisely the frozen reference."""
        if self.references.get(repository) != head:
            raise ApiError("Requested Git history differs from the frozen head.")
        body = self._cached(repository, "history", lambda repo: [
            row.model_dump(mode="json") for row in read_history(repo, head)
        ])
        try:
            return validate_history([SourceCommit.model_validate(row) for row in body], head)
        except (TypeError, ValueError) as error:
            raise ApiError("Invalid cached Git ancestry.") from error

    def tree(self, repository: str, tree_sha: str) -> list[TreeEntry]:
        """Return the complete recursive tree of one tree object."""
        body = self._cached(repository, f"tree:{tree_sha}", lambda repo: [
            entry.model_dump(mode="json") for entry in read_tree(repo, tree_sha)
        ])
        return [TreeEntry.model_validate(row) for row in body]

    def blob(self, repository: str, sha: str) -> bytes:
        """Return the raw bytes of one blob."""
        body = self._cached(repository, f"blob:{sha}", lambda repo: base64.b64encode(
            read_blob(repo, sha, self.maximum_blob_bytes)
        ).decode("ascii"))
        return base64.b64decode(body)

    def path_commits(self, repository: str, head: str, path: str | None) -> list[str]:
        """Return the commits reachable from head that changed the path."""
        if self.references.get(repository) != head:
            raise ApiError("Requested Git history differs from the frozen head.")
        return self._cached(repository, f"path_commits:{path or ''}", lambda repo: read_path_commits(repo, head, path))

    # Internals.

    def _cached(self, repository: str, request: str, produce):
        """Replay saved evidence or produce it from the fetched repository and save it."""
        if repository not in self.references:
            raise ApiError("Git request references a repository outside the frozen inputs.")
        identity = {
            "provider": "pydriller",
            "repository": repository,
            "head": self.references[repository],
            "request": request,
        }
        digest = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
        path = self.root / f"{digest}.json"
        if path.exists():
            saved = read_json(path)
            if saved["identity"] != identity:
                raise ApiError("Local Git cache identity does not match.")
            self.cache_hits += 1
            return saved["body"]
        try:
            body = produce(self._repository(repository))
        except (GitError, subprocess.SubprocessError, OSError, ValueError, KeyError) as error:
            raise ApiError(f"Git evidence failed for {repository}: {type(error).__name__}") from error
        write_json(path, {"identity": identity, "body": body, "retrieved_at": utcnow()})
        return body

    def _repository(self, repository: str) -> Repo:
        """Fetch the frozen head of a repository into the shared bare repository once."""
        if self.offline:
            raise ApiError("Offline Git evidence is missing; network access is disabled.")
        if self._repo is None:
            self._temporary = tempfile.TemporaryDirectory(prefix="skill-pattern-mine-git-")
            self.workspace_path = Path(self._temporary.name)
            self._repo = Repo.init(self.workspace_path, bare=True)
        if repository not in self._fetched:
            head = self.references[repository]
            logger.info("Fetching frozen Git history: %s %s", repository, head[:12])
            self.fetches += 1
            subprocess.run(
                [
                    "git", "-C", str(self._repo.git_dir), "-c", "gc.auto=0",
                    "fetch", "--no-tags", "--quiet",
                    f"https://github.com/{repository}.git", head,
                ],
                check=True,
                capture_output=True,
                timeout=self.timeout_seconds,
                env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
            )
            if self._repo.commit(head).hexsha != head:
                raise ApiError("Git fetch did not resolve the frozen commit.")
            self._fetched.add(repository)
        return self._repo
