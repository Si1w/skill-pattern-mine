"""Construct monthly package net changes from frozen Git histories.

The flow for one fork is: complete histories of fork and upstream, the first
parent lineage of the fork, the months in which each package changed, origin
evidence for every change against the upstream package history, and finally
one MonthlyRecord per package and month with complete endpoint contents.
"""

import base64
import hashlib
import json
import logging
from collections import Counter, defaultdict
from datetime import datetime, timezone
from difflib import SequenceMatcher, unified_diff
from importlib.metadata import version
from pathlib import Path, PurePosixPath

from src.config import ExperimentSettings
from src.domain import (
    FileChange,
    Fork,
    Instance,
    MonthlyRecord,
    OriginEvidence,
    PackageFile,
    PackageRevision,
    RepositorySnapshot,
    SourceCommit,
    TreeEntry,
)
from src.github import ApiError
from src.run import RunRecord
from src.storage import read_json, read_jsonl, record_error, write_json, write_jsonl
from src.verify import verify_run

logger = logging.getLogger(__name__)

MANIFEST = "SKILL.md"
REGULAR_FILE_MODES = {"100644", "100755"}


def month_of(commit: SourceCommit) -> str:
    """UTC calendar month of the committer date (ADR 0015)."""
    return commit.committer_date.astimezone(timezone.utc).strftime("%Y-%m")


# --- Inputs ---------------------------------------------------------------


def load_extraction_inputs(root: Path, run: RunRecord, *, allow_partial: bool = False) -> list[tuple[Fork, str]]:
    """Pair every successfully compared, eligible fork with its frozen upstream SHA.

    Normal extraction requires finished and accepted acquisition; a bounded
    pilot may explicitly allow partial inputs.
    """
    if allow_partial and not run.pilot:
        raise ValueError("Partial extraction requires a bounded pilot run; use a separate pilot ID.")
    if not allow_partial:
        progress_path = root / "progress.json"
        progress = read_json(progress_path) if progress_path.exists() else {}
        if progress.get("state") != "finished":
            raise ValueError("Extraction requires finished acquisition; use --allow_partial only in a pilot run.")
        if verify_run(root)["status"] != "passed":
            raise ValueError("Extraction requires passing acquisition acceptance.")
    omitted = {(row["fork"]["upstream"], row["github_id"]) for row in read_jsonl(root / "fork_exclusions.jsonl")}
    omitted |= {(row["upstream"], row["github_id"]) for row in read_jsonl(root / "fork_skips.jsonl")}
    compared = {(row["fork"]["upstream"], row["github_id"]) for row in read_jsonl(root / "comparisons.jsonl")}
    repositories = {
        row["repository"]["full_name"]: RepositorySnapshot.model_validate(row)
        for row in read_jsonl(root / "repositories.jsonl")
    }
    inputs = []
    for row in read_jsonl(root / "forks.jsonl"):
        identity = (row["upstream"], row["github_id"])
        if identity in omitted or identity not in compared:
            continue
        fork = Fork.model_validate(row)
        snapshot = repositories[fork.upstream]
        eligible = (
            snapshot.tree_complete
            and snapshot.repository.excluded_by is None
            and (run.pilot or snapshot.repository.screening_complete)
        )
        if eligible:
            inputs.append((fork, snapshot.default_branch_sha))
    if not inputs:
        raise ValueError("Extraction needs eligible forks with successful comparisons.")
    return inputs


def frozen_references(inputs: list[tuple[Fork, str]]) -> dict[str, str]:
    """Map every repository in the inputs to its single frozen head."""
    references = {}
    for fork, upstream_sha in inputs:
        for name, head in ((fork.full_name, fork.default_branch_sha), (fork.upstream, upstream_sha)):
            if references.get(name, head) != head:
                raise ValueError("Conflicting frozen Git references in extraction inputs.")
            references[name] = head
    return references


# --- Lineage and diffs -----------------------------------------------------


def first_parent_lineage(history: dict[str, SourceCommit], head: str, cutoff: datetime) -> list[SourceCommit]:
    """Follow first parents from the head, oldest first, up to the cutoff.

    Ancestry rather than timestamps defines the order; a lineage whose months
    run backwards, or that returns below the cutoff after crossing it, is
    rejected instead of being sorted.
    """
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
    selected, last_month, beyond_cutoff = [], "", False
    for commit in lineage:
        month = month_of(commit)
        if last_month and month < last_month:
            raise ApiError("First parent history crosses calendar months backwards.")
        last_month = month
        if commit.committer_date.astimezone(timezone.utc) >= cutoff:
            beyond_cutoff = True
        elif beyond_cutoff:
            raise ApiError("First parent history returns below the observation cutoff.")
        else:
            selected.append(commit)
    return selected


def file_changes(before: list[PackageFile], after: list[PackageFile]) -> list[FileChange]:
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
            patch = text_patch(path, left, right)
        else:
            patch = "Nontext content changed; complete encoded values are stored with this record.\n"
        changes.append(
            FileChange(
                path=path,
                status="added" if left is None else "removed" if right is None else "modified",
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


def text_patch(path: str, left: PackageFile | None, right: PackageFile | None) -> str:
    """Unified diff of two text files, marking a missing final newline."""
    lines = unified_diff(
        left.content.splitlines(keepends=True) if left else [],
        right.content.splitlines(keepends=True) if right else [],
        fromfile=path if left else "/dev/null",
        tofile=path if right else "/dev/null",
    )
    return "".join(
        line if line.endswith("\n") else line + "\n\\ No newline at end of file\n" for line in lines
    )


def patch_fingerprint(before: list[PackageFile], after: list[PackageFile]) -> str:
    """Fingerprint exact edits without unchanged text context or line numbers."""
    changes = []
    for change in file_changes(before, after):
        if all(encoding in {None, "utf-8"} for encoding in (change.encoding_before, change.encoding_after)):
            left = (change.content_before or "").splitlines(keepends=True)
            right = (change.content_after or "").splitlines(keepends=True)
            edits = [
                [left[a:b], right[c:d]]
                for tag, a, b, c, d in SequenceMatcher(None, left, right, autojunk=False).get_opcodes()
                if tag != "equal"
            ]
        else:
            edits = [change.before_blob_sha, change.after_blob_sha]
        changes.append([change.path, change.status, change.mode_before, change.mode_after, edits])
    return hashlib.sha256(json.dumps(changes, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()


# --- Package states --------------------------------------------------------


class PackageStore:
    """Resolve complete package states of one repository from a Git source.

    Trees and decoded blobs are kept in memory; the blob dictionary may be
    shared between a fork and its upstream because a verified Git blob has
    the same bytes in both repositories.
    """

    def __init__(self, source, repository: str, history: dict[str, SourceCommit], maximum_blob_bytes: int):
        self.source = source
        self.repository = repository
        self.history = history
        self.maximum_blob_bytes = maximum_blob_bytes
        self.trees: dict[str, dict[str, TreeEntry]] = {}
        self.blobs: dict[str, tuple[str, str]] = {}

    def entries(self, sha: str) -> dict[str, TreeEntry]:
        """Complete tree inventory of a commit, by path."""
        if sha not in self.trees:
            if sha not in self.history:
                raise ApiError(f"Missing commit metadata: {self.repository} {sha}")
            rows = self.source.tree(self.repository, self.history[sha].tree_sha)
            paths = {item.path: item for item in rows}
            if len(paths) != len(rows) or any(not item.sha for item in rows):
                raise ApiError("Incomplete or repeated tree entries.")
            self.trees[sha] = paths
        return self.trees[sha]

    def roots(self, sha: str) -> set[str]:
        """Package roots: directories holding a regular manifest, symlinks excluded."""
        return {
            str(PurePosixPath(item.path).parent)
            for item in self.entries(sha).values()
            if item.type == "blob" and item.mode in REGULAR_FILE_MODES and PurePosixPath(item.path).name == MANIFEST
        }

    def state(self, sha: str | None, root: str) -> dict[str, TreeEntry]:
        """All tracked files and submodule pointers under a package root."""
        if sha is None:
            return {}
        return {
            path: item
            for path, item in self.entries(sha).items()
            if item.type in {"blob", "commit"} and (root == "." or path.startswith(root + "/"))
        }

    def read_file(self, entry: TreeEntry) -> PackageFile:
        """Read one entry, verifying the blob identity before decoding its content."""
        if entry.type == "commit":
            return PackageFile(path=entry.path, sha=entry.sha, mode=entry.mode, encoding="gitlink", content=entry.sha)
        if entry.sha not in self.blobs:
            raw = self.source.blob(self.repository, entry.sha)
            if len(raw) > self.maximum_blob_bytes:
                raise ApiError(f"Oversized blob: {entry.path}")
            identity = hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()
            if identity != entry.sha:
                raise ApiError(f"Blob content failed integrity verification: {entry.path}")
            self.blobs[entry.sha] = decode_blob(raw)
        content, encoding = self.blobs[entry.sha]
        return PackageFile(path=entry.path, sha=entry.sha, mode=entry.mode, encoding=encoding, content=content)

    def snapshot(self, sha: str, root: str) -> list[PackageFile]:
        """Read a complete package endpoint."""
        return [self.read_file(item) for _, item in sorted(self.state(sha, root).items())]

    def fingerprint(self, parent: str | None, sha: str, root: str) -> str:
        """Fingerprint the package transition from parent to sha, reading only changed blobs."""
        before, after = self.state(parent, root), self.state(sha, root)
        changed = sorted(path for path in before.keys() | after.keys() if before.get(path) != after.get(path))
        return patch_fingerprint(
            [self.read_file(before[path]) for path in changed if path in before],
            [self.read_file(after[path]) for path in changed if path in after],
        )


def decode_blob(raw: bytes) -> tuple[str, str]:
    """Decode text as UTF-8; keep binary content as base64."""
    try:
        if b"\0" in raw:
            raise UnicodeDecodeError("utf-8", raw, 0, 1, "binary zero")
        return raw.decode("utf-8"), "utf-8"
    except UnicodeDecodeError:
        return base64.b64encode(raw).decode("ascii"), "base64"


# --- Origin evidence -------------------------------------------------------


def upstream_fingerprints(upstream: PackageStore, head: str, root: str) -> dict[str, list[str]]:
    """Index every upstream package transition by fingerprint; a match does not give direction."""
    logger.info("Collecting upstream origin evidence for %s", root)
    shas = upstream.source.path_commits(upstream.repository, head, None if root == "." else root)
    if len(set(shas)) != len(shas):
        raise ApiError(f"Repeated commits in upstream package history: {root}")
    signatures = defaultdict(list)
    for index, sha in enumerate(shas):
        if index % 20 == 0:
            logger.info("Checking upstream package transition %d/%d for %s", index + 1, len(shas), root)
        if sha not in upstream.history:
            raise ApiError("Package history is not part of the frozen upstream graph.")
        commit = upstream.history[sha]
        parent = commit.parent_shas[0] if commit.parent_shas else None
        if upstream.state(parent, root) != upstream.state(sha, root):
            signatures[upstream.fingerprint(parent, sha, root)].append(sha)
    return dict(signatures)


def ancestors(history: dict[str, SourceCommit], head: str) -> set[str]:
    """All commits reachable from head through any parent."""
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
    """Classify one package transition as fork candidate, upstream, or unresolved.

    The rules are conservative (ADR 0020): a commit or patch that also occurs
    upstream is unresolved, a merge that lands exactly on an upstream parent's
    package state is synchronization, and a merge that adopts a side branch is
    a candidate only when every transition the side branch introduced is one.
    """
    parent = commit.parent_shas[0]
    signature = store.fingerprint(parent, commit.sha, root)
    matches = set(signatures.get(signature, []))
    if commit.sha in upstream.history:
        matches.add(commit.sha)
    evidence = dict(commit_sha=commit.sha, parent_sha=parent, patch_fingerprint=signature)

    if commit.sha in upstream.history:
        return OriginEvidence(
            **evidence, kind="unresolved", matching_upstream_shas=sorted(matches),
            reason="The same commit occurs upstream; later integration prevents assigning origin direction.",
        )
    if len(commit.parent_shas) > 1:
        return classify_merge(commit, root, store, upstream, signatures, matches, evidence)
    if matches:
        return OriginEvidence(
            **evidence, kind="unresolved", matching_upstream_shas=sorted(matches),
            reason="The commit or equivalent patch occurs upstream; origin direction is not established.",
        )
    return OriginEvidence(
        **evidence, kind="fork_candidate",
        reason="Linear change with no matching commit or patch in the collected upstream package history.",
    )


def classify_merge(
    commit: SourceCommit,
    root: str,
    store: PackageStore,
    upstream: PackageStore,
    signatures: dict[str, list[str]],
    matches: set[str],
    evidence: dict,
) -> OriginEvidence:
    """Attribute a merge from the package states of its parents."""
    merged_state = store.state(commit.sha, root)
    side_parents = commit.parent_shas[1:]
    for other in side_parents:
        if other in upstream.history and merged_state == upstream.state(other, root):
            return OriginEvidence(
                **evidence, kind="upstream", matching_upstream_shas=[other],
                reason="The merge endpoint equals the complete package state of an upstream parent.",
            )
    introduced = []
    adopts_side_state = any(merged_state == store.state(other, root) for other in side_parents)
    if not matches and adopts_side_state:
        existing = ancestors(store.history, commit.parent_shas[0])
        new = set().union(*(ancestors(store.history, other) for other in side_parents)) - existing
        side_evidence = []
        for sha in sorted(new):
            source = store.history[sha]
            if source.parent_shas and store.state(source.parent_shas[0], root) != store.state(sha, root):
                introduced.append(sha)
                side_evidence.append(classify_origin(source, root, store, upstream, signatures))
        if side_evidence and all(item.kind == "fork_candidate" for item in side_evidence):
            return OriginEvidence(
                **evidence, kind="fork_candidate", introduced_commit_shas=introduced,
                reason="The merge adopts an exact side package state; "
                "introduced package transitions have no observed upstream overlap.",
            )
        matches = matches.union(*(item.matching_upstream_shas for item in side_evidence))
    return OriginEvidence(
        **evidence, kind="unresolved", matching_upstream_shas=sorted(matches), introduced_commit_shas=introduced,
        reason="Package changes in this merge cannot be attributed from parent states.",
    )


# --- Monthly records -------------------------------------------------------


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
    excluded = {item.kind for item in evidence} != {"fork_candidate"}
    identity = [fork.full_name.lower(), root, month, before_sha, after_sha]
    return MonthlyRecord(
        instance=Instance(
            instance_id=hashlib.sha256(json.dumps(identity, separators=(",", ":")).encode()).hexdigest(),
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
            exclusion_note=(
                "Source evidence includes upstream overlap or changes whose origin cannot be separated."
                if excluded
                else None
            ),
        ),
        before_files=before,
        after_files=after,
        origin_evidence=evidence,
        partial_month=cutoff.astimezone(timezone.utc).strftime("%Y-%m") == month,
    )


def package_changes_by_month(
    store: PackageStore, lineage: list[SourceCommit], month: str | None
) -> tuple[dict[tuple[str, str], list[int]], dict[str, set[str]]]:
    """Index lineage positions at which each package changed, keyed by month and root.

    Also returns, per month, the roots involved in a removal paired with an
    addition, whose identity cannot be established without review.
    """
    groups = defaultdict(list)
    moved = defaultdict(set)
    for index, commit in enumerate(lineage):
        current_month = month_of(commit)
        if not commit.parent_shas or (month and month != current_month):
            continue
        parent = commit.parent_shas[0]
        before_roots, after_roots = store.roots(parent), store.roots(commit.sha)
        if before_roots - after_roots and after_roots - before_roots:
            moved[current_month].update(before_roots ^ after_roots)
        for root in sorted(before_roots | after_roots):
            if store.state(parent, root) != store.state(commit.sha, root):
                groups[current_month, root].append(index)
    return groups, moved


def extract_fork(
    source,
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
    fork_history = source.history(fork.full_name, fork.default_branch_sha)
    upstream_history = source.history(fork.upstream, upstream_sha)
    write_jsonl(output / "fork_history.jsonl", fork_history.values())
    write_jsonl(output / "upstream_history.jsonl", upstream_history.values())
    lineage = first_parent_lineage(fork_history, fork.default_branch_sha, cutoff)
    store = PackageStore(source, fork.full_name, fork_history, config.extraction.maximum_blob_bytes)
    upstream = PackageStore(source, fork.upstream, upstream_history, config.extraction.maximum_blob_bytes)
    store.blobs = upstream.blobs
    groups, moved = package_changes_by_month(store, lineage, month)
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
                omissions.append({
                    **subject,
                    "reason": "unestablished_package_identity",
                    "detail": "A package root was removed while another was added in this month.",
                })
                continue
            shared = next((item.sha for item in reversed(lineage[:first]) if item.sha in upstream_history), None)
            if shared is None or root not in upstream.roots(shared):
                omissions.append({
                    **subject,
                    "reason": "unestablished_package_identity",
                    "detail": "No existing manifest at the preceding shared ancestor.",
                })
                continue
            if root not in signature_cache:
                signature_cache[root] = upstream_fingerprints(upstream, upstream_sha, root)
            events = [
                classify_origin(lineage[index], root, store, upstream, signature_cache[root])
                for index in indexes
            ]
            if all(item.kind == "upstream" for item in events):
                omissions.append({
                    **subject,
                    "reason": "upstream_synchronization",
                    "evidence": [item.model_dump(mode="json") for item in events],
                })
                continue
            records.append(
                build_record(
                    fork, root, current_month, before_sha, after_sha,
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


def check_extraction_manifest(
    root: Path, config: ExperimentSettings, inputs, cutoff: datetime, month, limit, partial_acquisition
) -> None:
    """Freeze the extraction request on first use; later runs must repeat it exactly."""
    request = {
        "partial_acquisition": partial_acquisition,
        "inputs": [{"fork": fork.model_dump(mode="json"), "upstream_sha": sha} for fork, sha in inputs],
        "cutoff_utc": cutoff.isoformat(),
        "month": month,
        "num_samples": limit,
        "settings": config.model_dump(mode="json"),
    }
    manifest = root / "extraction.json"
    if not manifest.exists():
        write_json(manifest, request)
    elif read_json(manifest) != request:
        raise ValueError("Extraction settings or references changed; use a new run ID.")


def extract_monthly(
    source,
    config: ExperimentSettings,
    root: Path,
    inputs: list[tuple[Fork, str]],
    cutoff: datetime,
    *,
    month: str | None,
    limit: int | None,
    partial_acquisition: bool = False,
) -> dict:
    """Write monthly records and an acceptance report without analytical claims.

    Every accepted fork is processed; the sample bound limits only the monthly
    intervals produced per fork (ADR 0020).
    """
    if cutoff.tzinfo is None or (limit is not None and limit < 1):
        raise ValueError("Require an aware cutoff and a positive sample bound.")
    check_extraction_manifest(root, config, inputs, cutoff, month, limit, partial_acquisition)
    records, omissions, errors, coverages = [], [], [], []
    for fork, upstream_sha in inputs:
        directory = root / "histories" / hashlib.sha256(fork.full_name.lower().encode()).hexdigest()[:16]
        try:
            rows, skipped, failures = extract_fork(
                source, config, fork, upstream_sha, cutoff, month=month, limit=limit, output=directory
            )
        except (ApiError, ValueError, KeyError) as error:
            record_error(errors, "monthly_history", fork.full_name, error)
            continue
        records.extend(rows)
        omissions.extend(skipped)
        errors.extend(failures)
        coverages.append({"fork": fork.full_name, **read_json(directory / "coverage.json")})
    write_jsonl(root / "monthly_records.jsonl", records)
    write_jsonl(root / "monthly_omissions.jsonl", omissions)
    write_jsonl(root / "monthly_errors.jsonl", errors)
    identities = [record.instance.instance_id for record in records]
    checks = {
        "no_extraction_errors": not errors,
        "histories_complete": bool(coverages) and all(item["histories_complete"] for item in coverages),
        "observations_produced": bool(records),
        "unique_instances": len(set(identities)) == len(identities),
        "endpoint_diffs_reproduce": all(
            file_changes(record.before_files, record.after_files) == record.instance.files for record in records
        ),
        "zero_states_consistent": all(
            (record.instance.net_change_status == "no_net_change") == (record.before_files == record.after_files)
            for record in records
        ),
    }
    report = {
        "status": "passed" if all(checks.values()) else "failed",
        "purpose": "monthly_engineering_validation",
        "input_scope": "partial_pilot" if partial_acquisition else "acquisition",
        "reader_versions": {name: version(name) for name in ("pydriller", "gitpython")},
        "git_fetches": source.fetches,
        "git_cache_hits": source.cache_hits,
        "checks": checks,
        "forks_processed": len(coverages),
        "coverage": coverages,
        "records": len(records),
        "customization_candidates": sum(record.instance.exclusion_reason is None for record in records),
        "excluded_unresolved_upstream": sum(record.instance.exclusion_reason is not None for record in records),
        "no_net_change": sum(record.instance.net_change_status == "no_net_change" for record in records),
        "omissions": dict(Counter(item["reason"] for item in omissions)),
        "errors": len(errors),
        "limitations": [
            "Origin rules require human validation; unmatched patches do not prove independent authorship.",
            "Calibration, bot and translation handling, and annotation remain separate work.",
        ],
    }
    write_json(root / "monthly_acceptance.json", report)
    return report
