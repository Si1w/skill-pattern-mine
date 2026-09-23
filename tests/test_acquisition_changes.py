"""Verify skipped forks, comparison reuse and safe extraction boundaries."""

import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.acquisition import load_extraction_inputs, prepare_run, verify_run
from src.config import load_config
from src.github import ApiError, GitHubClient, read_jsonl, write_json, write_jsonl
from src.retrieve import retrieve_forks, retrieve_repositories
from test_acquisition import BASE, HEAD, FixtureClient
from test_github import page


class AcquisitionChangesTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.config = load_config(Path("configs/skill-pattern-mine.yaml"))
        self.config.screening.selection_mode = "calibrated_ratio"
        self.config.retrieval.topic_seeds = []
        self.run = prepare_run(self.root, self.config, pilot=True, limit=3, offline=False)
        retrieve_repositories(FixtureClient(), self.config, self.root, limit=3)

    def test_404_at_each_fork_stage_is_accounted_for_and_not_extracted(self):
        for stage, endpoint in (
            ("fork_metadata", "repositories/3"),
            ("fork_branch", "repos/fork/skills/branches/main"),
            ("fork_comparison", f"repos/fork/skills/compare/{BASE}...{HEAD}?per_page=100"),
        ):
            with self.subTest(stage=stage):
                class MissingClient(FixtureClient):
                    def get(self, request):
                        if request == endpoint or (stage == "fork_metadata" and request == "repos/fork/skills"):
                            raise ApiError("Not Found", status=404)
                        return super().get(request)

                retrieve_forks(MissingClient(), self.config, self.root, limit=None, pilot=True)
                skips = read_jsonl(self.root / "fork_skips.jsonl")
                self.assertEqual([(r["github_id"], r["stage"]) for r in skips], [(3, stage)])
                self.assertEqual(read_jsonl(self.root / "fork_errors.jsonl"), [])
                self.assertEqual(verify_run(self.root)["status"], "passed")
                inputs = load_extraction_inputs(self.root, self.run)
                self.assertEqual([fork.full_name for fork, _ in inputs], ["same/skills"])

    def test_missing_inventory_404_is_skipped_but_other_failures_block(self):
        write_json(self.root / "recovery_inventory.json", {
            "owner/skills": [{"id": 999, "full_name": "missing/skills"}]
        })
        for status in (404, 403, 500):
            with self.subTest(status=status):
                class MissingClient(FixtureClient):
                    def get(self, endpoint):
                        if endpoint == "repositories/999":
                            raise ApiError("Unavailable", status=status)
                        return super().get(endpoint)

                retrieve_forks(MissingClient(), self.config, self.root, limit=None, pilot=True)
                report = verify_run(self.root)
                self.assertEqual(report["status"], "passed" if status == 404 else "failed")
                coverage = json.loads((self.root / "fork_coverage.json").read_text())[0]
                self.assertEqual(coverage["missing_previous_ids"], [999])
                if status == 404:
                    self.assertEqual(report["skipped_forks"], 1)
                    write_jsonl(self.root / "fork_skips.jsonl", [])
                    self.assertEqual(verify_run(self.root)["status"], "failed")

    def test_upstream_listing_404_still_fails(self):
        class MissingClient(FixtureClient):
            def get(self, endpoint):
                if "/forks?" in endpoint:
                    raise ApiError("Not Found", status=404)
                return super().get(endpoint)

        retrieve_forks(MissingClient(), self.config, self.root, limit=None, pilot=True)
        self.assertEqual(read_jsonl(self.root / "fork_skips.jsonl"), [])
        self.assertEqual(verify_run(self.root)["status"], "failed")

    def test_complete_pair_reuse_preserves_fork_identity_and_source(self):
        calls = []

        class SharedClient(FixtureClient):
            def get(self, endpoint):
                calls.append(endpoint)
                if "/branches/" in endpoint:
                    return page({"commit": {"sha": HEAD}})
                if endpoint.startswith("repos/same/skills/compare/"):
                    raise AssertionError("Repeated pair must not request another comparison")
                return super().get(endpoint)

        rows = retrieve_forks(SharedClient(), self.config, self.root, limit=None, pilot=True)
        self.assertEqual([r.github_id for r in rows], [3, 4])
        self.assertEqual(rows[1].fork.full_name, "same/skills")
        self.assertEqual(rows[1].reused_from, "fork/skills")
        self.assertEqual(rows[0].commits, rows[1].commits)
        self.assertIn("repos/same/skills/branches/main", calls)
        self.assertEqual(verify_run(self.root)["status"], "passed")
        saved = read_jsonl(self.root / "comparisons.jsonl")
        saved[1]["reused_from"] = "missing/skills"
        write_jsonl(self.root / "comparisons.jsonl", saved)
        self.assertEqual(verify_run(self.root)["status"], "failed")

    def test_incomplete_comparison_is_not_shared(self):
        calls = []

        class SharedClient(FixtureClient):
            def get(self, endpoint):
                calls.append(endpoint)
                if "/branches/" in endpoint:
                    return page({"commit": {"sha": HEAD}})
                if "/compare/" in endpoint:
                    return super().get(endpoint.replace("repos/same/", "repos/fork/"))
                return super().get(endpoint)

        rows = retrieve_forks(SharedClient(), self.config, self.root, limit=2, pilot=True)
        self.assertTrue(any(p.startswith("repos/same/skills/compare/") for p in calls))
        self.assertTrue(all(r.reused_from is None for r in rows))

    def test_skip_and_reused_comparison_replay_exactly_without_network(self):
        def response(args, **kwargs):
            endpoint = args[-1]
            status = 200
            if endpoint in {"repos/missing/skills", "repositories/5"}:
                status, body = 404, {"message": "Not Found"}
            elif "/branches/" in endpoint:
                body = {"commit": {"sha": HEAD}}
            else:
                body = FixtureClient().get(endpoint).body
                if "/forks?" in endpoint:
                    body = [*body, {**body[-1], "id": 5, "full_name": "missing/skills"}]
            return subprocess.CompletedProcess(
                args, 0 if status == 200 else 1,
                f"HTTP/2.0 {status} Status\n\n{json.dumps(body)}", "",
            )

        live = GitHubClient(self.root, api_version=self.config.github.api_version)
        with patch("src.github.subprocess.run", side_effect=response) as network:
            retrieve_forks(live, self.config, self.root, limit=None, pilot=True)
        self.assertEqual(network.call_count, 8)
        artifacts = ["forks.jsonl", "comparisons.jsonl", "fork_skips.jsonl", "fork_errors.jsonl", "fork_coverage.json"]
        original = {name: (self.root / name).read_bytes() for name in artifacts}
        offline = GitHubClient(self.root, api_version=self.config.github.api_version, offline=True)
        with patch("src.github.subprocess.run", side_effect=AssertionError("Network forbidden")):
            retrieve_forks(offline, self.config, self.root, limit=None, pilot=True)
        self.assertEqual(original, {name: (self.root / name).read_bytes() for name in artifacts})
        self.assertEqual(verify_run(self.root)["status"], "passed")

    def test_extraction_rejects_unfinished_collection_before_freezing_inputs(self):
        retrieve_forks(FixtureClient(), self.config, self.root, limit=None, pilot=True)
        progress = json.loads((self.root / "progress.json").read_text())
        progress["state"] = "running"
        write_json(self.root / "progress.json", progress)
        with self.assertRaisesRegex(ValueError, "finished"):
            load_extraction_inputs(self.root, self.run)
        self.assertFalse((self.root / "extraction.json").exists())
        self.assertEqual(len(load_extraction_inputs(self.root, self.run, allow_partial=True)), 2)
        with self.assertRaisesRegex(ValueError, "pilot"):
            load_extraction_inputs(self.root, {**self.run, "pilot": False}, allow_partial=True)

    def test_finished_but_invalid_collection_cannot_start_normal_extraction(self):
        retrieve_forks(FixtureClient(), self.config, self.root, limit=None, pilot=True)
        write_jsonl(self.root / "fork_errors.jsonl", [{"stage": "fork_comparison", "error": "failure"}])
        with self.assertRaisesRegex(ValueError, "acceptance"):
            load_extraction_inputs(self.root, self.run)


if __name__ == "__main__":
    unittest.main()
