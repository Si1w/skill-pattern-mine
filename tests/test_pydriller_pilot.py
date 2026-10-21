"""Compatibility expectations for the local history reader."""

import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path


class LocalHistoryTests(unittest.TestCase):
    """Exercise real Git objects without network access or project commits."""

    def test_fixture_pilot_records_file_selection_and_refuses_overwrite(self):
        from src.pydriller_pilot import run_pilot

        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "report.json"
            source = Path(directory) / "unused-for-fixtures.json"
            settings = {"repetitions": 1, "git_timeout_seconds": 180, "sample_keys": []}
            report = run_pilot(
                settings, source_path=source, output=output, limit=1, step="fixtures"
            )
            self.assertTrue(report["adapted_checks_passed"])
            self.assertEqual(report["input"], str(source.resolve()))
            self.assertEqual(
                json.loads(output.read_text())["output"], str(output.resolve())
            )
            original = output.read_bytes()
            with self.assertRaisesRegex(ValueError, "already exists"):
                run_pilot(
                    settings, source_path=source, output=output, limit=1, step="fixtures"
                )
            self.assertEqual(output.read_bytes(), original)

    def test_merges_deletion_modes_binary_and_cancellation(self):
        from src.pydriller_pilot import LocalObjects, fixture_repository, monthly_record
        from src.extract import PackageStore, file_changes

        with tempfile.TemporaryDirectory() as directory:
            repo, expected = fixture_repository(Path(directory))
            client = LocalObjects(repo)
            history, commits = client.history(
                repo.head.commit.hexsha, retain_commits=True
            )
            store = PackageStore(client, "fixture/repo", history, 10485760)
            cutoff = datetime(2026, 6, 1, tzinfo=timezone.utc)
            for month, ends in expected.items():
                result = monthly_record(
                    store, repo.head.commit.hexsha, cutoff, "skills/demo", month
                )
                self.assertEqual((result["before_sha"], result["after_sha"]), ends)
            merge = monthly_record(
                store, repo.head.commit.hexsha, cutoff, "skills/demo", "2026-03"
            )
            self.assertEqual(len(merge["changed_commits"]), 1)
            self.assertEqual(len(commits[merge["after_sha"]].parents), 2)
            may = monthly_record(
                store, repo.head.commit.hexsha, cutoff, "skills/demo", "2026-05"
            )
            self.assertEqual(len(may["changed_commits"]), 2)
            self.assertEqual(
                file_changes(
                    store.snapshot(may["before_sha"], "skills/demo"),
                    store.snapshot(may["after_sha"], "skills/demo"),
                ),
                [],
            )
            april = monthly_record(
                store, repo.head.commit.hexsha, cutoff, "skills/demo", "2026-04"
            )
            changes = file_changes(
                store.snapshot(april["before_sha"], "skills/demo"),
                store.snapshot(april["after_sha"], "skills/demo"),
            )
            self.assertTrue(any(c.status == "removed" for c in changes))
            self.assertTrue(any(c.encoding_after == "base64" for c in changes))
            self.assertTrue(
                any(
                    c.mode_before == "100644" and c.mode_after == "100755"
                    for c in changes
                )
            )
            repo.close()
