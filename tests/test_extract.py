"""Behavioral fixtures for monthly endpoints and conservative origin evidence."""

import hashlib
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from src.config import load_config
from src.domain import Fork, OriginEvidence, PackageFile, SourceCommit, TreeEntry
from src.extract import (
    build_record,
    extract_monthly,
    first_parent_lineage,
    file_changes,
    patch_fingerprint,
)
from src.github import ApiError


def blob(text):
    """Compute a Git blob identifier for fixture contents."""
    raw = text.encode()
    return hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()


def package(text, mode="100644", extra=True):
    """Include an unchanged file so endpoint tests cover full packages."""
    files = [
        PackageFile(
            path="skills/demo/SKILL.md",
            sha=blob(text),
            mode=mode,
            encoding="utf-8",
            content=text,
        )
    ]
    if extra:
        files.append(
            PackageFile(
                path="skills/demo/reference.txt",
                sha=blob("unchanged"),
                mode="100644",
                encoding="utf-8",
                content="unchanged",
            )
        )
    return files


def commit(sha, parent=None, date="2026-03-10T00:00:00Z"):
    """Create a source commit with an explicit first parent."""
    return SourceCommit(
        sha=sha,
        tree_sha=sha,
        parent_shas=[parent] if parent else [],
        author_date=date,
        committer_date=date,
        message="Fixture",
    )


def evidence(sha, parent, kind="fork_candidate"):
    """Represent a classified package transition."""
    return OriginEvidence(
        commit_sha=sha,
        parent_sha=parent,
        kind=kind,
        reason="Fixture",
        patch_fingerprint="signature",
    )


class LineageTests(unittest.TestCase):
    """API order and side branches must not become chronological endpoints."""

    def test_parent_order_wins_over_api_order_and_times_within_month(self):
        history = {
            "b": commit("b", "a", "2026-03-05T00:00:00Z"),
            "a": commit("a", date="2026-03-10T00:00:00Z"),
        }
        self.assertEqual(
            [
                row.sha
                for row in first_parent_lineage(
                    history, "b", datetime(2026, 4, 1, tzinfo=timezone.utc)
                )
            ],
            ["a", "b"],
        )

    def test_merge_uses_first_parent_without_extra_side_observations(self):
        history = {
            "root": commit("root"),
            "side": commit("side", "root"),
            "main": commit("main", "root"),
            "merge": commit("merge", "main"),
        }
        history["merge"].parent_shas.append("side")
        self.assertEqual(
            [
                row.sha
                for row in first_parent_lineage(
                    history, "merge", datetime(2026, 4, 1, tzinfo=timezone.utc)
                )
            ],
            ["root", "main", "merge"],
        )

    def test_missing_parent_is_not_a_root(self):
        with self.assertRaises(ApiError):
            first_parent_lineage(
                {"a": commit("a", "missing")},
                "a",
                datetime(2026, 4, 1, tzinfo=timezone.utc),
            )

    def test_backward_months_are_not_silently_sorted(self):
        history = {
            "a": commit("a", date="2026-04-01T00:00:00Z"),
            "b": commit("b", "a", "2026-03-10T00:00:00Z"),
        }
        with self.assertRaisesRegex(ApiError, "month"):
            first_parent_lineage(
                history, "b", datetime(2026, 5, 1, tzinfo=timezone.utc)
            )

    def test_cutoff_is_exclusive_and_can_not_be_crossed_backwards(self):
        cutoff = datetime(2026, 3, 16, tzinfo=timezone.utc)
        history = {"a": commit("a"), "b": commit("b", "a", "2026-03-16T00:00:00Z")}
        self.assertEqual(
            [row.sha for row in first_parent_lineage(history, "b", cutoff)], ["a"]
        )
        history["c"] = commit("c", "b", "2026-03-15T00:00:00Z")
        with self.assertRaises(ApiError):
            first_parent_lineage(history, "c", cutoff)


class DiffTests(unittest.TestCase):
    """Net differences preserve bytes, modes and absence explicitly."""

    def test_context_changes_do_not_change_patch_fingerprint(self):
        left = patch_fingerprint(package("prefix\nold\n"), package("prefix\nnew\n"))
        right = patch_fingerprint(
            package("different prefix\nold\n"), package("different prefix\nnew\n")
        )
        self.assertEqual(left, right)

    def test_meaningful_whitespace_is_not_normalized_away(self):
        self.assertNotEqual(
            patch_fingerprint(package("a\n"), package(" a\n")),
            patch_fingerprint(package("a\n"), package("a \n")),
        )

    def test_mode_only_change_is_not_zero(self):
        changes = file_changes(package("same"), package("same", mode="100755"))
        self.assertEqual(len(changes), 1)
        self.assertEqual(changes[0].mode_after, "100755")

    def test_add_delete_and_binary_content_remain_explicit(self):
        before = package("old", extra=False)
        after = [
            PackageFile(
                path="skills/demo/data.bin",
                sha="binary",
                mode="100644",
                encoding="base64",
                content="AP8=",
            )
        ]
        changes = file_changes(before, after)
        self.assertEqual({row.status for row in changes}, {"added", "removed"})
        added = next(row for row in changes if row.status == "added")
        self.assertIsNone(added.content_before)
        self.assertEqual(added.encoding_after, "base64")


class MonthlyTests(unittest.TestCase):
    """Net states, source evidence and observation identity remain separate."""

    def setUp(self):
        self.fork = Fork(
            upstream="up/skills",
            full_name="user/skills",
            owner="user",
            created_at="2026-01-01T00:00:00Z",
            pushed_at="2026-03-21T00:00:00Z",
            retrieved_at="2026-03-22T00:00:00Z",
            default_branch="main",
            default_branch_sha="last",
        )

    def record(self, before, after, kinds=("fork_candidate",), month="2026-03"):
        events = [
            evidence(str(index), "baseline", kind) for index, kind in enumerate(kinds)
        ]
        return build_record(
            self.fork,
            "skills/demo",
            month,
            "baseline",
            "last",
            [row.commit_sha for row in events],
            events,
            before,
            after,
            datetime(2026, 4, 1, tzinfo=timezone.utc),
        )

    def test_first_change_is_included_and_unchanged_files_are_preserved(self):
        record = self.record(package("before\n"), package("after\n"))
        self.assertEqual(record.instance.before.commit_sha, "baseline")
        self.assertEqual(len(record.before_files), 2)
        self.assertEqual(len(record.instance.files), 1)
        self.assertIn("-before", record.instance.files[0].patch)
        self.assertIn("+after", record.instance.files[0].patch)

    def test_cancelled_modifications_remain_an_active_zero_record(self):
        record = self.record(
            package("original"),
            package("original"),
            kinds=("fork_candidate", "fork_candidate"),
        )
        self.assertEqual(record.instance.net_change_status, "no_net_change")
        self.assertEqual(record.instance.files, [])
        self.assertEqual(len(record.origin_evidence), 2)
        self.assertIsNone(record.instance.exclusion_reason)

    def test_mixed_or_ambiguous_origin_is_excluded_even_when_cancelled(self):
        for kinds in [("fork_candidate", "upstream"), ("unresolved",)]:
            record = self.record(package("same"), package("same"), kinds=kinds)
            self.assertEqual(record.instance.exclusion_reason, "unresolved_upstream")

    def test_equal_diffs_in_different_months_remain_distinct(self):
        march = self.record(package("a"), package("b"))
        february = self.record(package("a"), package("b"), month="2026-02")
        self.assertNotEqual(march.instance.instance_id, february.instance.instance_id)
        self.assertEqual(
            march.instance.instance_id,
            self.record(package("a"), package("b")).instance.instance_id,
        )


class FakeGitSource:
    """Serve complete graphs and real blob hashes from in-memory fixtures.

    Tree identifiers equal commit identifiers so that states can be looked up
    by commit directly.
    """

    fetches = 0
    cache_hits = 0

    def __init__(self, *, merge=False, overlap=False, corrupt=False, rename=False):
        self.blob_reads = []
        self.corrupt = corrupt
        self.commits = {
            "root": commit("root", date="2026-02-01T00:00:00Z"),
            "up": commit("up", "root", "2026-03-05T00:00:00Z"),
            "one": commit("one", "root", "2026-03-10T00:00:00Z"),
            "two": commit("two", "one", "2026-03-11T00:00:00Z"),
        }
        if merge:
            self.commits["two"].parent_shas.append("up")
        self.states = {
            "root": package("original\n"),
            "up": package("upstream\n"),
            "one": package("upstream\n" if overlap else "custom\n"),
            "two": package("upstream\n" if merge else "original\n"),
        }
        if rename:
            for sha in ("one", "two"):
                self.states[sha] = [
                    item.model_copy(update={"path": item.path.replace("skills/demo/", "skills/renamed/")})
                    for item in self.states[sha]
                ]
        self.contents = {item.sha: item.content for files in self.states.values() for item in files}

    def ancestors(self, head):
        pending, seen = [head], set()
        while pending:
            sha = pending.pop()
            if sha not in seen:
                seen.add(sha)
                pending.extend(self.commits[sha].parent_shas)
        return seen

    def history(self, repository, head):
        return {sha: self.commits[sha] for sha in self.ancestors(head)}

    def tree(self, repository, tree_sha):
        return [
            TreeEntry(path=item.path, sha=item.sha, mode=item.mode, type="blob")
            for item in self.states[tree_sha]
        ]

    def blob(self, repository, sha):
        self.blob_reads.append(sha)
        return b"wrong" if self.corrupt else self.contents[sha].encode()

    def path_commits(self, repository, head, path):
        return sorted(self.ancestors(head), reverse=True)


class IntegrationTests(unittest.TestCase):
    """Exercise history acquisition, origin evidence and monthly persistence."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.config = load_config(Path("configs/skill-pattern-mine.yaml"))
        self.fork = Fork(
            upstream="up/skills",
            full_name="user/skills",
            owner="user",
            created_at="2026-01-01T00:00:00Z",
            pushed_at="2026-03-21T00:00:00Z",
            retrieved_at="2026-03-22T00:00:00Z",
            default_branch="main",
            default_branch_sha="two",
        )

    def extract(self, client):
        return extract_monthly(
            client,
            self.config,
            self.root,
            [(self.fork, "up")],
            datetime(2026, 4, 1, tzinfo=timezone.utc),
            month="2026-03",
            limit=2,
        )

    def test_full_flow_preserves_cancellation_and_replays_identically(self):
        report = self.extract(FakeGitSource())
        self.assertEqual(report["status"], "passed", report)
        self.assertEqual(report["customization_candidates"], 1)
        self.assertEqual(report["no_net_change"], 1)
        self.assertEqual(report["input_scope"], "acquisition")
        first = (self.root / "monthly_records.jsonl").read_bytes()
        self.extract(FakeGitSource())
        self.assertEqual(first, (self.root / "monthly_records.jsonl").read_bytes())

    def test_synchronization_inside_customization_month_is_excluded(self):
        report = self.extract(FakeGitSource(merge=True))
        self.assertEqual(report["status"], "passed", report)
        self.assertEqual(report["excluded_unresolved_upstream"], 1)
        self.assertEqual(report["customization_candidates"], 0)

    def test_repeated_extraction_keeps_its_manifest_and_rejects_parameter_changes(self):
        self.extract(FakeGitSource())
        manifest = self.root / "extraction.json"
        original = manifest.read_bytes()
        records = (self.root / "monthly_records.jsonl").read_bytes()
        self.assertEqual(self.extract(FakeGitSource())["status"], "passed")
        self.assertEqual(manifest.read_bytes(), original)
        self.assertEqual((self.root / "monthly_records.jsonl").read_bytes(), records)
        self.config.seed += 1
        with self.assertRaisesRegex(ValueError, "settings or references"):
            self.extract(FakeGitSource())

    def test_equivalent_patch_with_different_sha_is_not_assigned_origin(self):
        report = self.extract(FakeGitSource(overlap=True))
        self.assertEqual(report["excluded_unresolved_upstream"], 1)
        self.assertEqual(report["no_net_change"], 1)

    def test_corrupted_blob_is_failure_not_zero_change(self):
        report = self.extract(FakeGitSource(corrupt=True))
        self.assertEqual(report["status"], "failed")
        self.assertEqual(report["errors"], 1)

    def test_shared_blob_bytes_are_fetched_once_across_repositories(self):
        client = FakeGitSource()
        self.extract(client)
        self.assertEqual(len(client.blob_reads), len(set(client.blob_reads)))

    def test_feature_merge_uses_introduced_history_to_retain_candidate(self):
        client = FakeGitSource()
        client.commits["feature"] = commit("feature", "root", "2026-03-09T00:00:00Z")
        client.commits["two"].parent_shas.append("feature")
        client.states["one"] = package("original\n")
        client.states["feature"] = package("feature\n")
        client.states["two"] = package("feature\n")
        client.contents[blob("feature\n")] = "feature\n"
        report = self.extract(client)
        self.assertEqual(report["customization_candidates"], 1)
        row = json.loads((self.root / "monthly_records.jsonl").read_text())
        self.assertEqual(
            row["origin_evidence"][0]["introduced_commit_shas"], ["feature"]
        )

    def test_feature_merge_with_replayed_upstream_patch_is_unresolved(self):
        client = FakeGitSource()
        client.commits["feature"] = commit("feature", "root", "2026-03-09T00:00:00Z")
        client.commits["two"].parent_shas.append("feature")
        client.states["one"] = package("original\n")
        client.states["feature"] = package("upstream\n")
        client.states["two"] = package("upstream\n")
        report = self.extract(client)
        self.assertEqual(report["excluded_unresolved_upstream"], 1)
        self.assertEqual(report["customization_candidates"], 0)
        self.assertEqual(report["no_net_change"], 0)

    def test_package_move_requires_identity_review(self):
        report = self.extract(FakeGitSource(rename=True))
        self.assertEqual(report["records"], 0)
        self.assertEqual(report["omissions"]["unestablished_package_identity"], 2)
        self.assertEqual(report["errors"], 0)

    def test_changed_extraction_scope_cannot_reuse_run(self):
        self.extract(FakeGitSource())
        with self.assertRaisesRegex(ValueError, "settings or references"):
            extract_monthly(
                FakeGitSource(),
                self.config,
                self.root,
                [(self.fork, "up")],
                datetime(2026, 4, 1, tzinfo=timezone.utc),
                month="2026-02",
                limit=2,
            )

    def test_later_upstream_integration_remains_ambiguous(self):
        client = FakeGitSource()
        client.commits["up"] = commit("up", "one", "2026-04-05T00:00:00Z")
        report = self.extract(client)
        self.assertEqual(report["excluded_unresolved_upstream"], 1)
        row = json.loads((self.root / "monthly_records.jsonl").read_text())
        self.assertIn("one", row["origin_evidence"][0]["matching_upstream_shas"])

    def test_pure_upstream_sync_is_not_customization_activity(self):
        client = FakeGitSource(merge=True)
        client.states["one"] = package("original\n")
        report = self.extract(client)
        self.assertEqual(report["customization_candidates"], 0)
        self.assertEqual(report["omissions"]["upstream_synchronization"], 1)
        self.assertEqual(report["errors"], 0)

    def test_merge_outside_package_does_not_exclude_its_month(self):
        client = FakeGitSource(merge=True)
        client.states["two"] = package("custom\n")
        report = self.extract(client)
        self.assertEqual(report["customization_candidates"], 1)
        self.assertEqual(report["excluded_unresolved_upstream"], 0)

    def test_missing_ancestor_is_reported_as_failure(self):
        client = FakeGitSource()
        complete = client.history

        def without_root(repository, head):
            return {sha: row for sha, row in complete(repository, head).items() if sha != "root"}

        client.history = without_root
        report = self.extract(client)
        self.assertEqual(report["status"], "failed")
        self.assertEqual(report["records"], 0)
        self.assertEqual(report["errors"], 1)


if __name__ == "__main__":
    unittest.main()
