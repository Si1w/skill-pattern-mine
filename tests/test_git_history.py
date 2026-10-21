"""Behavior of production Git acquisition, replay and cleanup."""

import json
import subprocess
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from src.config import load_config
from src.domain import Fork
from src.extract import extract_monthly
from src.git_objects import GitSource
from src.github import ApiError
from src.pydriller_pilot import fixture_repository


class GitSourceTests(unittest.TestCase):
    """Use real Git objects while replacing only the network fetch destination."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.repo, self.expected = fixture_repository(self.root / "fixture")
        self.addCleanup(self.repo.close)
        self.head = self.repo.head.commit.hexsha
        self.base = self.expected["2026-02"][0]
        self.refs = {"user/skills": self.head, "up/skills": self.base}
        self.config = load_config(Path("configs/skill-pattern-mine.yaml"))
        self.config.extraction.history_backend = "pydriller"
        self.fork = Fork(
            upstream="up/skills",
            full_name="user/skills",
            owner="user",
            created_at="2026-01-01T00:00:00Z",
            pushed_at="2026-05-03T00:00:00Z",
            retrieved_at="2026-06-01T00:00:00Z",
            default_branch="main",
            default_branch_sha=self.head,
        )
        self.run = subprocess.run

    def fetch_locally(self, command, **kwargs):
        """Keep the production fetch command but use the constructed repository."""
        command = [
            str(self.repo.working_tree_dir)
            if str(arg).startswith("https://github.com/")
            else arg
            for arg in command
        ]
        return self.run(command, **kwargs)

    def source(self, *, offline=False):
        return GitSource(
            self.root / "cache",
            self.refs,
            timeout_seconds=30,
            maximum_blob_bytes=10485760,
            offline=offline,
        )

    def test_frozen_ancestry_replay_and_cleanup(self):
        with patch("src.git_objects.subprocess.run", side_effect=self.fetch_locally):
            with self.source() as source:
                history = source.history("up/skills", self.base)
                self.assertEqual(set(history), {self.base})
                source.history("up/skills", self.base)
                self.assertEqual(source.fetches, 1)
                workspace = source.workspace_path
        self.assertFalse(workspace.exists())
        with patch(
            "src.git_objects.subprocess.run",
            side_effect=AssertionError("Offline Git access"),
        ):
            with self.source(offline=True) as source:
                self.assertEqual(history, source.history("up/skills", self.base))
                self.assertIsNone(source.workspace_path)

    def test_production_months_preserve_merges_and_replay(self):
        class NoApi:
            offline = False

            def get(self, endpoint):
                raise AssertionError(f"Unexpected API call: {endpoint}")

        client = NoApi()
        output = self.root / "run"
        with patch("src.git_objects.subprocess.run", side_effect=self.fetch_locally):
            result = extract_monthly(
                client,
                self.config,
                output,
                [(self.fork, self.base)],
                datetime(2026, 6, 1, tzinfo=timezone.utc),
                month=None,
                limit=None,
            )
        self.assertEqual(result["status"], "passed", result)
        self.assertEqual(result["history_backend"], "pydriller")
        self.assertEqual(result["git_fetches"], 2)
        self.assertTrue(result["temporary_git_removed"])
        rows = [
            json.loads(line)
            for line in (output / "monthly_records.jsonl").read_text().splitlines()
        ]
        by_month = {r["instance"]["month"]: r for r in rows}
        self.assertEqual(set(by_month), set(self.expected))
        for month, ends in self.expected.items():
            self.assertEqual(
                by_month[month]["instance"]["before"]["commit_sha"], ends[0]
            )
            self.assertEqual(
                by_month[month]["instance"]["after"]["commit_sha"], ends[1]
            )
        self.assertEqual(
            by_month["2026-05"]["instance"]["net_change_status"], "no_net_change"
        )
        files = by_month["2026-04"]["instance"]["files"]
        self.assertTrue(any(f["status"] == "removed" for f in files))
        self.assertTrue(any(f["encoding_after"] == "base64" for f in files))
        self.assertTrue(
            any(
                f["mode_before"] == "100644" and f["mode_after"] == "100755"
                for f in files
            )
        )
        before = (output / "monthly_records.jsonl").read_bytes()
        client.offline = True
        with patch(
            "src.git_objects.subprocess.run",
            side_effect=AssertionError("Offline Git access"),
        ):
            replay = extract_monthly(
                client,
                self.config,
                output,
                [(self.fork, self.base)],
                datetime(2026, 6, 1, tzinfo=timezone.utc),
                month=None,
                limit=None,
            )
        self.assertEqual(replay["status"], "passed", replay)
        self.assertEqual(replay["git_fetches"], 0)
        self.assertEqual(before, (output / "monthly_records.jsonl").read_bytes())

    def test_missing_offline_evidence_fails_without_fetching(self):
        with patch(
            "src.git_objects.subprocess.run",
            side_effect=AssertionError("Offline Git access"),
        ):
            with self.source(offline=True) as source:
                with self.assertRaisesRegex(ApiError, "Offline"):
                    source.history("up/skills", self.base)

    def test_failed_fetch_is_not_cached_and_removes_workspace(self):
        with patch(
            "src.git_objects.subprocess.run",
            side_effect=subprocess.TimeoutExpired("git", 30),
        ):
            with self.source() as source:
                with self.assertRaises(ApiError):
                    source.history("up/skills", self.base)
                workspace = source.workspace_path
        self.assertFalse(workspace.exists())
        self.assertFalse(list((self.root / "cache").glob("*.json")))

    def test_cache_identity_and_history_closure_are_verified(self):
        with patch("src.git_objects.subprocess.run", side_effect=self.fetch_locally):
            with self.source() as source:
                source.history("user/skills", self.head)
        path = next((self.root / "cache").glob("*.json"))
        saved = json.loads(path.read_text())
        saved["body"] = [c for c in saved["body"] if c["sha"] != self.base]
        path.write_text(json.dumps(saved))
        with self.source(offline=True) as source:
            with self.assertRaisesRegex(ApiError, "ancestr"):
                source.history("user/skills", self.head)

    def test_root_history_and_gitlinks_do_not_follow_external_repositories(self):
        self.repo.git.update_index(
            "--add", "--cacheinfo", f"160000,{self.base},skills/demo/external"
        )
        commit = self.repo.index.commit("test: gitlink")
        self.refs["user/skills"] = commit.hexsha
        with patch("src.git_objects.subprocess.run", side_effect=self.fetch_locally):
            with self.source() as source:
                rows = source.get(
                    f"repos/user/skills/commits?sha={commit.hexsha}&per_page=100"
                ).body
                self.assertIn(self.base, {r["sha"] for r in rows})
                tree = source.get(
                    f"repos/user/skills/git/trees/{commit.tree.hexsha}?recursive=1"
                ).body
                entry = next(
                    r for r in tree["tree"] if r["path"] == "skills/demo/external"
                )
                self.assertEqual(entry["type"], "commit")
                self.assertEqual(entry["sha"], self.base)
