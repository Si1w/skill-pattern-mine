"""Construct monthly package net changes from frozen GitHub histories."""

import base64
import hashlib
import json
import logging
from collections import Counter, defaultdict
from contextlib import ExitStack
from importlib.metadata import version
from datetime import datetime, timezone
from difflib import SequenceMatcher, unified_diff
from pathlib import Path, PurePosixPath
from urllib.parse import urlencode

from src.config import ExperimentSettings, load_saved_config
from src.git_objects import GitSource
from src.domain import (
    FileChange,
    Fork,
    Instance,
    MonthlyRecord,
    OriginEvidence,
    PackageFile,
    PackageRevision,
    SourceCommit,
)
from src.github import ApiError, collect_pages, write_json, write_jsonl
from src.retrieve import complete_tree, record_error

logger = logging.getLogger(__name__)


def source_commit(item: dict) -> SourceCommit:
    """Parse the nested API dates and preserve ordered parents."""
    return SourceCommit(
        sha=item["sha"],
        tree_sha=item["commit"]["tree"]["sha"],
        parent_shas=[parent["sha"] for parent in item["parents"]],
        author_date=item["commit"]["author"]["date"],
        committer_date=item["commit"]["committer"]["date"],
        message=item["commit"]["message"],
        author_login=(item.get("author") or {}).get("login"),
    )


def fetch_history(
    client, repository: str, head: str, per_page: int
) -> dict[str, SourceCommit]:
    """Fetch the entire reachable graph; sample bounds never truncate ancestry."""
    if isinstance(client, GitSource):
        return client.history(repository, head)
    logger.info("Collecting complete history for %s at %s", repository, head[:12])
    endpoint = f"repos/{repository}/commits?" + urlencode(
        {"sha": head, "per_page": per_page}
    )
    rows, coverage = collect_pages(client, endpoint)
    history = {row["sha"]: source_commit(row) for row in rows}
    if not coverage["complete"] or head not in history or len(history) != len(rows):
        raise ApiError(f"Incomplete or repeated commit history: {repository}")
    for commit in history.values():
        if any(parent not in history for parent in commit.parent_shas):
            raise ApiError(f"Missing ancestor in history: {repository} {commit.sha}")
    return history


def first_parent_lineage(
    history: dict[str, SourceCommit], head: str, cutoff: datetime
) -> list[SourceCommit]:
    """Follow ancestry rather than timestamps; reject ambiguous month ordering."""
    if cutoff.tzinfo is None:
        raise ValueError("The cutoff must include a timezone.")
    lineage, visited = [], set()
    cursor = head
    while cursor:
        if cursor in visited or cursor not in history:
            raise ApiError("Missing or cyclic first parent history.")
        visited.add(cursor)
        commit = history[cursor]
        lineage.append(commit)
        cursor = commit.parent_shas[0] if commit.parent_shas else None
    lineage.reverse()
    last_month, beyond_cutoff = "", False
    selected = []
    for commit in lineage:
        date = commit.committer_date.astimezone(timezone.utc)
        month = date.strftime("%Y-%m")
        if last_month and month < last_month:
            raise ApiError("First parent history crosses calendar months backwards.")
        last_month = month
        if date >= cutoff:
            beyond_cutoff = True
        elif beyond_cutoff:
            raise ApiError("First parent history returns below the observation cutoff.")
        else:
            selected.append(commit)
    return selected


def file_changes(
    before: list[PackageFile], after: list[PackageFile]
) -> list[FileChange]:
    """Compare complete file states, preserving modes and nontext bytes."""
    old = {item.path: item for item in before}
    new = {item.path: item for item in after}
    if len(old) != len(before) or len(new) != len(after):
        raise ApiError("Duplicate paths in a package snapshot.")
    changes = []
    for path in sorted(old.keys() | new.keys()):
        left, right = old.get(path), new.get(path)
        if left == right:
            continue
        mode_patch = ""
        if left and right and left.mode != right.mode:
            mode_patch = f"old mode {left.mode}\nnew mode {right.mode}\n"
        if all(item is None or item.encoding == "utf-8" for item in (left, right)):
            lines = unified_diff(
                left.content.splitlines(keepends=True) if left else [],
                right.content.splitlines(keepends=True) if right else [],
                fromfile=path if left else "/dev/null",
                tofile=path if right else "/dev/null",
            )
            patch = "".join(
                line
                if line.endswith("\n")
                else line + "\n\\ No newline at end of file\n"
                for line in lines
            )
        else:
            patch = "Nontext content changed; complete encoded values are stored with this record.\n"
        changes.append(
            FileChange(
                path=path,
                status="added"
                if left is None
                else "removed"
                if right is None
                else "modified",
                patch=mode_patch + patch,
                content_before=left.content if left else None,
                content_after=right.content if right else None,
                before_blob_sha=left.sha if left else None,
                after_blob_sha=right.sha if right else None,
                mode_before=left.mode if left else None,
                mode_after=right.mode if right else None,
                encoding_before=left.encoding if left else None,
                encoding_after=right.encoding if right else None,
            )
        )
    return changes


def patch_fingerprint(before: list[PackageFile], after: list[PackageFile]) -> str:
    """Fingerprint exact edits without unchanged text context or line numbers."""
    changes = []
    for change in file_changes(before, after):
        if all(
            encoding in {None, "utf-8"}
            for encoding in (change.encoding_before, change.encoding_after)
        ):
            left = (change.content_before or "").splitlines(keepends=True)
            right = (change.content_after or "").splitlines(keepends=True)
            edits = [
                [left[a:b], right[c:d]]
                for tag, a, b, c, d in SequenceMatcher(
                    None, left, right, autojunk=False
                ).get_opcodes()
                if tag != "equal"
            ]
        else:
            edits = [change.before_blob_sha, change.after_blob_sha]
        changes.append(
            [change.path, change.status, change.mode_before, change.mode_after, edits]
        )
    return hashlib.sha256(
        json.dumps(changes, ensure_ascii=False, separators=(",", ":")).encode()
    ).hexdigest()


class PackageStore:
    """Resolve immutable trees and complete blobs, reusing verified data in memory."""

    def __init__(
        self,
        client,
        repository: str,
        history: dict[str, SourceCommit],
        maximum_blob_bytes: int,
    ):
        self.client = client
        self.repository = repository
        self.history = history
        self.maximum_blob_bytes = maximum_blob_bytes
        self.trees = {}
        self.blobs = {}

    def entries(self, sha: str) -> dict:
        """Return a complete inventory, including object identifiers."""
        if sha not in self.trees:
            if sha not in self.history:
                raise ApiError(f"Missing commit metadata: {self.repository} {sha}")
            rows = complete_tree(
                self.client, self.repository, self.history[sha].tree_sha
            )
            paths = {item.path: item for item in rows}
            if len(paths) != len(rows) or any(not item.sha for item in rows):
                raise ApiError("Incomplete or repeated tree entries.")
            self.trees[sha] = paths
        return self.trees[sha]

    def roots(self, sha: str) -> set[str]:
        """Locate regular manifests, without following symlinks."""
        return {
            str(PurePosixPath(item.path).parent)
            for item in self.entries(sha).values()
            if item.type == "blob"
            and item.mode in {"100644", "100755"}
            and PurePosixPath(item.path).name == "SKILL.md"
        }

    def state(self, sha: str | None, root: str) -> dict:
        """Keep all tracked package files, including unchanged files and pointers."""
        if sha is None:
            return {}
        return {
            path: item
            for path, item in self.entries(sha).items()
            if item.type in {"blob", "commit"}
            and (root == "." or path.startswith(root + "/"))
        }

    def read_file(self, entry) -> PackageFile:
        """Validate blob size and Git object identity before decoding contents."""
        if entry.type == "commit":
            return PackageFile(
                path=entry.path,
                sha=entry.sha,
                mode=entry.mode,
                encoding="gitlink",
                content=entry.sha,
            )
        if entry.sha not in self.blobs:
            body = self.client.get(
                f"repos/{self.repository}/git/blobs/{entry.sha}"
            ).body
            if body["encoding"] != "base64" or body["size"] > self.maximum_blob_bytes:
                raise ApiError(f"Unsupported or oversized blob: {entry.path}")
            raw = base64.b64decode("".join(body["content"].split()), validate=True)
            identity = hashlib.sha1(
                b"blob " + str(len(raw)).encode() + b"\0" + raw
            ).hexdigest()
            if (
                len(raw) != body["size"]
                or identity != entry.sha
                or body["sha"] != entry.sha
            ):
                raise ApiError(
                    f"Blob content failed integrity verification: {entry.path}"
                )
            try:
                if b"\0" in raw:
                    raise UnicodeDecodeError("utf-8", raw, 0, 1, "binary zero")
                content, encoding = raw.decode("utf-8"), "utf-8"
            except UnicodeDecodeError:
                content, encoding = base64.b64encode(raw).decode("ascii"), "base64"
            self.blobs[entry.sha] = (content, encoding)
        content, encoding = self.blobs[entry.sha]
        return PackageFile(
            path=entry.path,
            sha=entry.sha,
            mode=entry.mode,
            encoding=encoding,
            content=content,
        )

    def snapshot(self, sha: str, root: str) -> list[PackageFile]:
        """Read a complete package endpoint."""
        return [
            self.read_file(item) for path, item in sorted(self.state(sha, root).items())
        ]

    def fingerprint(self, parent: str | None, sha: str, root: str) -> str:
        """Read only changed blobs to compare a source transition with upstream."""
        before, after = self.state(parent, root), self.state(sha, root)
        changed = {
            path
            for path in before.keys() | after.keys()
            if before.get(path) != after.get(path)
        }
        return patch_fingerprint(
            [
                self.read_file(before[path])
                for path in sorted(changed)
                if path in before
            ],
            [self.read_file(after[path]) for path in sorted(changed) if path in after],
        )


def upstream_fingerprints(
    store: PackageStore, head: str, root: str, per_page: int
) -> dict[str, list[str]]:
    """Index observed upstream patches; a match does not establish direction."""
    logger.info("Collecting upstream origin evidence for %s", root)
    parameters = {"sha": head, "per_page": per_page}
    if root != ".":
        parameters["path"] = root
    rows, coverage = collect_pages(
        store.client, f"repos/{store.repository}/commits?" + urlencode(parameters)
    )
    if not coverage["complete"] or len({row["sha"] for row in rows}) != len(rows):
        raise ApiError(f"Incomplete upstream package history: {root}")
    signatures = defaultdict(list)
    for index, row in enumerate(rows):
        if index % 20 == 0:
            logger.info(
                "Checking upstream package transition %d/%d for %s",
                index + 1,
                len(rows),
                root,
            )
        sha = row["sha"]
        if sha not in store.history:
            raise ApiError("Package history is not part of the frozen upstream graph.")
        commit = store.history[sha]
        parent = commit.parent_shas[0] if commit.parent_shas else None
        if store.state(parent, root) != store.state(sha, root):
            signatures[store.fingerprint(parent, sha, root)].append(sha)
    return dict(signatures)


def ancestors(history: dict[str, SourceCommit], head: str) -> set[str]:
    """Find reachable objects without assuming which parent introduced them."""
    pending, visited = [head], set()
    while pending:
        sha = pending.pop()
        if sha in visited:
            continue
        if sha not in history:
            raise ApiError("Missing ancestor while resolving merge origin.")
        visited.add(sha)
        pending.extend(history[sha].parent_shas)
    return visited


def classify_origin(
    commit: SourceCommit,
    root: str,
    store: PackageStore,
    upstream: PackageStore,
    signatures: dict[str, list[str]],
) -> OriginEvidence:
    """Classify observed overlap conservatively, without guessing authorship."""
    parent = commit.parent_shas[0]
    signature = store.fingerprint(parent, commit.sha, root)
    matches = sorted(
        set(
            signatures.get(signature, [])
            + ([commit.sha] if commit.sha in upstream.history else [])
        )
    )
    introduced = []
    if commit.sha in upstream.history:
        kind, reason = (
            "unresolved",
            "The same commit occurs upstream; later integration prevents assigning origin direction.",
        )
    elif len(commit.parent_shas) > 1:
        for other in commit.parent_shas[1:]:
            if other in upstream.history and store.state(
                commit.sha, root
            ) == upstream.state(other, root):
                return OriginEvidence(
                    commit_sha=commit.sha,
                    parent_sha=parent,
                    kind="upstream",
                    reason="The merge endpoint equals the complete package state of an upstream parent.",
                    matching_upstream_shas=[other],
                    patch_fingerprint=signature,
                )
        if not matches and any(
            store.state(commit.sha, root) == store.state(other, root)
            for other in commit.parent_shas[1:]
        ):
            existing = ancestors(store.history, parent)
            new = (
                set().union(
                    *(
                        ancestors(store.history, other)
                        for other in commit.parent_shas[1:]
                    )
                )
                - existing
            )
            side_evidence = []
            for sha in sorted(new):
                source = store.history[sha]
                if not source.parent_shas:
                    continue
                if store.state(source.parent_shas[0], root) != store.state(sha, root):
                    introduced.append(sha)
                    side_evidence.append(
                        classify_origin(source, root, store, upstream, signatures)
                    )
            if side_evidence and all(
                item.kind == "fork_candidate" for item in side_evidence
            ):
                return OriginEvidence(
                    commit_sha=commit.sha,
                    parent_sha=parent,
                    kind="fork_candidate",
                    reason="The merge adopts an exact side package state; introduced package transitions have no observed upstream overlap.",
                    introduced_commit_shas=introduced,
                    patch_fingerprint=signature,
                )
            matches = sorted(
                set(matches).union(
                    *(item.matching_upstream_shas for item in side_evidence)
                )
            )
        kind, reason = (
            "unresolved",
            "Package changes in this merge cannot be attributed from parent states.",
        )
    elif matches:
        kind, reason = (
            "unresolved",
            "The commit or equivalent patch occurs upstream; origin direction is not established.",
        )
    else:
        kind, reason = (
            "fork_candidate",
            "Linear change with no matching commit or patch in the collected upstream package history.",
        )
    return OriginEvidence(
        commit_sha=commit.sha,
        parent_sha=parent,
        kind=kind,
        reason=reason,
        matching_upstream_shas=matches,
        introduced_commit_shas=introduced,
        patch_fingerprint=signature,
    )


def build_record(
    fork: Fork,
    root: str,
    month: str,
    before_sha: str,
    after_sha: str,
    source_shas: list[str],
    evidence: list[OriginEvidence],
    before: list[PackageFile],
    after: list[PackageFile],
    cutoff: datetime,
) -> MonthlyRecord:
    """Build one stable observation, including explicit cancelled activity."""
    if not evidence:
        raise ValueError("Monthly activity requires source evidence.")
    changes = file_changes(before, after)
    kinds = {item.kind for item in evidence}
    excluded = kinds != {"fork_candidate"}
    identity = [fork.full_name.lower(), root, month, before_sha, after_sha]
    return MonthlyRecord(
        instance=Instance(
            instance_id=hashlib.sha256(
                json.dumps(identity, separators=(",", ":")).encode()
            ).hexdigest(),
            upstream=fork.upstream,
            fork=fork.full_name,
            fork_owner=fork.owner,
            fork_branch=fork.default_branch,
            month=month,
            skill_package_path=root,
            before=PackageRevision(commit_sha=before_sha, package_path=root),
            after=PackageRevision(commit_sha=after_sha, package_path=root),
            source_commit_shas=source_shas,
            net_change_status="changed" if changes else "no_net_change",
            files=changes,
            exclusion_reason="unresolved_upstream" if excluded else None,
            exclusion_note="Source evidence includes upstream overlap or changes whose origin cannot be separated."
            if excluded
            else None,
        ),
        before_files=before,
        after_files=after,
        origin_evidence=evidence,
        partial_month=cutoff.astimezone(timezone.utc).strftime("%Y-%m") == month,
    )


def extract_fork(
    client,
    config: ExperimentSettings,
    fork: Fork,
    upstream_sha: str,
    cutoff: datetime,
    *,
    month: str | None,
    limit: int | None,
    output: Path,
) -> tuple[list[MonthlyRecord], list[dict], list[dict]]:
    """Extract bounded monthly candidates after collecting complete histories."""
    output.mkdir(parents=True, exist_ok=True)
    fork_history = fetch_history(
        client, fork.full_name, fork.default_branch_sha, config.github.per_page
    )
    upstream_history = fetch_history(
        client, fork.upstream, upstream_sha, config.github.per_page
    )
    write_jsonl(output / "fork_history.jsonl", fork_history.values())
    write_jsonl(output / "upstream_history.jsonl", upstream_history.values())
    lineage = first_parent_lineage(fork_history, fork.default_branch_sha, cutoff)
    store = PackageStore(
        client, fork.full_name, fork_history, config.extraction.maximum_blob_bytes
    )
    upstream = PackageStore(
        client, fork.upstream, upstream_history, config.extraction.maximum_blob_bytes
    )
    # A verified Git blob has the same bytes in both repositories.
    store.blobs = upstream.blobs
    groups = defaultdict(list)
    moved = defaultdict(set)
    for index, commit in enumerate(lineage):
        current_month = commit.committer_date.astimezone(timezone.utc).strftime("%Y-%m")
        if not commit.parent_shas or (month and month != current_month):
            continue
        parent = commit.parent_shas[0]
        before_roots, after_roots = store.roots(parent), store.roots(commit.sha)
        if before_roots - after_roots and after_roots - before_roots:
            moved[current_month].update(before_roots ^ after_roots)
        for root in sorted(before_roots | after_roots):
            if store.state(parent, root) != store.state(commit.sha, root):
                groups[current_month, root].append(index)
    candidates = sorted(groups)
    records, omissions, errors, signature_cache = [], [], [], {}
    for current_month, root in candidates[:limit]:
        indexes = groups[current_month, root]
        first, last = indexes[0], indexes[-1]
        before_sha, after_sha = lineage[first].parent_shas[0], lineage[last].sha
        subject = {
            "fork": fork.full_name,
            "month": current_month,
            "package_path": root,
            "before_sha": before_sha,
            "after_sha": after_sha,
        }
        logger.info("Extracting %s %s %s", fork.full_name, current_month, root)
        try:
            if root in moved[current_month]:
                omissions.append(
                    {
                        **subject,
                        "reason": "unestablished_package_identity",
                        "detail": "A package root was removed while another was added in this month.",
                    }
                )
                continue
            shared = next(
                (
                    item.sha
                    for item in reversed(lineage[:first])
                    if item.sha in upstream_history
                ),
                None,
            )
            if shared is None or root not in upstream.roots(shared):
                omissions.append(
                    {
                        **subject,
                        "reason": "unestablished_package_identity",
                        "detail": "No existing manifest at the preceding shared ancestor.",
                    }
                )
                continue
            if root not in signature_cache:
                signature_cache[root] = upstream_fingerprints(
                    upstream, upstream_sha, root, config.github.per_page
                )
            events = [
                classify_origin(
                    lineage[index], root, store, upstream, signature_cache[root]
                )
                for index in indexes
            ]
            if all(item.kind == "upstream" for item in events):
                omissions.append(
                    {
                        **subject,
                        "reason": "upstream_synchronization",
                        "evidence": [item.model_dump(mode="json") for item in events],
                    }
                )
                continue
            records.append(
                build_record(
                    fork,
                    root,
                    current_month,
                    before_sha,
                    after_sha,
                    [item.sha for item in lineage[first : last + 1]],
                    events,
                    store.snapshot(before_sha, root),
                    store.snapshot(after_sha, root),
                    cutoff,
                )
            )
        except (ApiError, ValueError, KeyError) as error:
            record_error(errors, "monthly_package", json.dumps(subject), error)
    write_json(
        output / "coverage.json",
        {
            "fork_commits": len(fork_history),
            "upstream_commits": len(upstream_history),
            "first_parent_commits_before_cutoff": len(lineage),
            "histories_complete": True,
            "candidate_intervals": len(candidates),
            "processed_intervals": len(candidates[:limit]),
            "all_intervals_processed": len(candidates[:limit]) == len(candidates),
            "month_filter": month,
        },
    )
    return records, omissions, errors


def extract_monthly(
    client,
    config: ExperimentSettings,
    root: Path,
    inputs: list[tuple[Fork, str]],
    cutoff: datetime,
    *,
    month: str | None,
    limit: int | None,
    partial_acquisition: bool = False,
) -> dict:
    """Write monthly records and an acceptance report without analytical claims."""
    if cutoff.tzinfo is None or (limit is not None and limit < 1):
        raise ValueError("Require an aware cutoff and a positive sample bound.")
    request = {
        "partial_acquisition": partial_acquisition,
        "inputs": [
            {"fork": fork.model_dump(mode="json"), "upstream_sha": upstream_sha}
            for fork, upstream_sha in inputs
        ],
        "cutoff_utc": cutoff.isoformat(),
        "month": month,
        "num_samples": limit,
        "settings": config.model_dump(mode="json"),
    }
    manifest = root / "extraction.json"
    if manifest.exists():
        saved = json.loads(manifest.read_text())
        saved.setdefault("partial_acquisition", False)
        saved["settings"] = load_saved_config(saved["settings"]).model_dump(mode="json")
        if saved != request:
            raise ValueError(
                "Extraction settings or references changed; use a new run ID."
            )
    else:
        write_json(manifest, request)
    records, omissions, errors, coverages = [], [], [], []
    git = None
    with ExitStack() as stack:
        if config.extraction.history_backend == "pydriller":
            references = {}
            for fork, upstream_sha in inputs[:limit]:
                for name, head in (
                    (fork.full_name, fork.default_branch_sha),
                    (fork.upstream, upstream_sha),
                ):
                    if name in references and references[name] != head:
                        raise ValueError(
                            "Conflicting frozen Git references in extraction inputs."
                        )
                    references[name] = head
            git = stack.enter_context(
                GitSource(
                    root / "git_evidence",
                    references,
                    timeout_seconds=config.extraction.git_timeout_seconds,
                    maximum_blob_bytes=config.extraction.maximum_blob_bytes,
                    offline=getattr(client, "offline", False),
                )
            )
        for fork, upstream_sha in inputs[:limit]:
            directory = (
                root
                / "histories"
                / hashlib.sha256(fork.full_name.lower().encode()).hexdigest()[:16]
            )
            try:
                rows, skipped, failures = extract_fork(
                    git or client,
                    config,
                    fork,
                    upstream_sha,
                    cutoff,
                    month=month,
                    limit=limit,
                    output=directory,
                )
                records.extend(rows)
                omissions.extend(skipped)
                errors.extend(failures)
                coverages.append(
                    {
                        "fork": fork.full_name,
                        **json.loads((directory / "coverage.json").read_text()),
                    }
                )
            except (ApiError, ValueError, KeyError) as error:
                record_error(errors, "monthly_history", fork.full_name, error)
    write_jsonl(root / "monthly_records.jsonl", records)
    write_jsonl(root / "monthly_omissions.jsonl", omissions)
    write_jsonl(root / "monthly_errors.jsonl", errors)
    identities = [record.instance.instance_id for record in records]
    checks = {
        "no_extraction_errors": not errors,
        "histories_complete": bool(coverages)
        and all(item["histories_complete"] for item in coverages),
        "observations_produced": bool(records),
        "unique_instances": len(set(identities)) == len(identities),
        "endpoint_diffs_reproduce": all(
            file_changes(record.before_files, record.after_files)
            == record.instance.files
            for record in records
        ),
        "zero_states_consistent": all(
            (record.instance.net_change_status == "no_net_change")
            == (record.before_files == record.after_files)
            for record in records
        ),
    }
    report = {
        "status": "passed" if all(checks.values()) else "failed",
        "purpose": "monthly_engineering_validation",
        "input_scope": "partial_pilot" if partial_acquisition else "acquisition",
        "history_backend": config.extraction.history_backend,
        "reader_versions": {name: version(name) for name in ("pydriller", "gitpython")}
        if git
        else {},
        "git_fetches": git.fetches if git else 0,
        "git_cache_hits": git.cache_hits if git else 0,
        "temporary_git_removed": git is None
        or git.workspace_path is None
        or not git.workspace_path.exists(),
        "checks": checks,
        "forks_processed": len(coverages),
        "coverage": coverages,
        "records": len(records),
        "customization_candidates": sum(
            record.instance.exclusion_reason is None for record in records
        ),
        "excluded_unresolved_upstream": sum(
            record.instance.exclusion_reason is not None for record in records
        ),
        "no_net_change": sum(
            record.instance.net_change_status == "no_net_change" for record in records
        ),
        "omissions": dict(Counter(item["reason"] for item in omissions)),
        "errors": len(errors),
        "limitations": [
            "Origin rules require human validation; unmatched patches do not prove independent authorship.",
            "Calibration, bot and translation handling, and annotation remain separate work.",
        ],
    }
    write_json(root / "monthly_acceptance.json", report)
    return report
