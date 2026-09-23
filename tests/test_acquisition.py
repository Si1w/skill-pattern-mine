"""Exercise a complete acquisition with deterministic API responses."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.parse import urlsplit

from src.acquisition import prepare_run, verify_run
from src.config import load_config
from src.github import ApiError, GitHubClient, read_jsonl
from src.retrieve import retrieve_forks, retrieve_repositories
from test_github import page

BASE = "a" * 40
HEAD = "b" * 40


class FixtureClient:
    """Serve one upstream, an excluded candidate and two different forks."""

    def get(self, endpoint):
        path = urlsplit(endpoint).path
        if path.startswith("search/"):
            hits = [{"full_name": "owner/skills"}, {"full_name": "owner/small"}]
            if path.endswith("code"):
                hits = [{"repository": hits[0], "path": ".claude-plugin/plugin.json"}]
            return page(
                {"items": hits, "total_count": len(hits), "incomplete_results": False}
            )
        if path == "repos/owner/skills/forks":
            return page(
                [
                    {
                        "id": 3,
                        "full_name": "fork/skills",
                        "fork": True,
                        "private": False,
                        "created_at": "2026-08-01T00:00:00Z",
                    },
                    {
                        "id": 4,
                        "full_name": "same/skills",
                        "fork": True,
                        "private": False,
                        "created_at": "2026-08-02T00:00:00Z",
                    },
                ]
            )
        if "/branches/" in path:
            return page(
                {"commit": {"sha": HEAD if path.startswith("repos/fork/") else BASE}}
            )
        if "/git/commits/" in path:
            return page({"tree": {"sha": "tree"}})
        if "/git/trees/" in path:
            return page(
                {
                    "truncated": False,
                    "tree": [
                        {
                            "path": "skills/one/SKILL.md",
                            "type": "blob",
                            "mode": "100644",
                            "sha": "blob",
                        },
                        {
                            "path": "README.md",
                            "type": "blob",
                            "mode": "100644",
                            "sha": "readme",
                        },
                    ],
                }
            )
        if "/compare/" in path:
            count = 3 if path.startswith("repos/fork/") else 0
            commits = [
                {
                    "sha": str(index) * 40,
                    "parents": [{"sha": BASE}],
                    "author": {"login": "fork"},
                    "commit": {
                        "message": "Change",
                        "tree": {"sha": "tree"},
                        "author": {"date": "2026-08-30T00:00:00Z"},
                        "committer": {"date": "2026-09-01T00:00:00Z"},
                    },
                }
                for index in range(count)
            ]
            return page(
                {
                    "status": "ahead" if count else "identical",
                    "ahead_by": count,
                    "behind_by": 0,
                    "merge_base_commit": {"sha": BASE},
                    "commits": commits,
                }
            )
        if path.count("/") == 2:
            name = path.removeprefix("repos/")
            identity = {
                "owner/skills": 1,
                "owner/small": 2,
                "fork/skills": 3,
                "same/skills": 4,
            }[name]
            return page(
                {
                    "id": identity,
                    "full_name": name,
                    "forks_count": 2000 if identity == 1 else 10,
                    "stargazers_count": 0,
                    "topics": [],
                    "private": False,
                    "fork": identity > 2,
                    "default_branch": "main",
                    "owner": {"login": name.split("/")[0]},
                    "created_at": "2026-08-01T00:00:00Z",
                    "pushed_at": "2026-09-01T00:00:00Z",
                }
            )
        raise ApiError(f"Unexpected fixture endpoint: {endpoint}")


class AcquisitionTests(unittest.TestCase):
    """Check stage integration, repeat execution and frozen settings."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.config = load_config(Path("configs/skill-pattern-mine.yaml"))
        self.config.screening.selection_mode = "calibrated_ratio"
        self.config.retrieval.topic_seeds = []
        self.config.retrieval.description_queries = ["skill in:description"]
        self.config.retrieval.manifest_queries = ["filename:plugin.json"]

    def test_complete_flow_preserves_overlap_pending_status_and_commit_bounds(self):
        prepare_run(self.root, self.config, pilot=True, limit=2, offline=False)
        repositories = retrieve_repositories(
            FixtureClient(), self.config, self.root, limit=2
        )
        self.assertEqual(
            set(repositories[0].repository.channels), {"intent", "manifest"}
        )
        self.assertFalse(repositories[0].repository.screening_complete)
        self.assertEqual(repositories[1].repository.excluded_by, "fork_threshold")
        comparisons = retrieve_forks(
            FixtureClient(), self.config, self.root, limit=2, pilot=True
        )
        self.assertEqual(len(comparisons), 2)
        self.assertEqual(len(comparisons[0].commits), 2)
        self.assertFalse(comparisons[0].commits_complete)
        self.assertEqual(comparisons[1].status, "identical")
        report = verify_run(self.root)
        self.assertEqual(report["status"], "passed", report)
        self.assertEqual(report["formally_retained_repositories"], 0)
        first = (self.root / "comparisons.jsonl").read_bytes()
        retrieve_forks(FixtureClient(), self.config, self.root, limit=2, pilot=True)
        self.assertEqual(first, (self.root / "comparisons.jsonl").read_bytes())
        self.assertEqual(len(read_jsonl(self.root / "forks.jsonl")), 2)

    def test_formal_fork_mining_rejects_pending_screening(self):
        retrieve_repositories(FixtureClient(), self.config, self.root, limit=2)
        with self.assertRaisesRegex(ValueError, "calibrated"):
            retrieve_forks(
                FixtureClient(), self.config, self.root, limit=2, pilot=False
            )

    def test_unrelated_fork_is_accounted_for_as_an_evidenced_exclusion(self):
        import subprocess

        prepare_run(self.root, self.config, pilot=True, limit=2, offline=False)
        retrieve_repositories(FixtureClient(), self.config, self.root, limit=2)
        cached = GitHubClient(self.root, api_version=self.config.github.api_version)

        class UnrelatedForkClient(FixtureClient):
            def get(self, endpoint):
                if endpoint.startswith("repos/fork/skills/compare/"):
                    return cached.get(endpoint)
                return super().get(endpoint)

        message = f"No common ancestor between {BASE} and {HEAD}."
        response = subprocess.CompletedProcess(
            [], 1, f'HTTP/2.0 404 Not Found\n\n{json.dumps({"message": message})}', ''
        )
        with patch("src.github.subprocess.run", return_value=response):
            comparisons = retrieve_forks(
                UnrelatedForkClient(), self.config, self.root, limit=2, pilot=True
            )
        self.assertEqual(len(comparisons), 1)
        excluded = read_jsonl(self.root / "fork_exclusions.jsonl")
        self.assertEqual(len(excluded), 1)
        self.assertEqual(excluded[0]["reason"], "no_common_ancestor")
        self.assertEqual(read_jsonl(self.root / "fork_errors.jsonl"), [])
        report = verify_run(self.root)
        self.assertEqual(report["status"], "passed", report)
        self.assertEqual(report["excluded_forks"], 1)
        cached.offline = True
        retrieve_forks(UnrelatedForkClient(), self.config, self.root, limit=2, pilot=True)
        self.assertEqual(read_jsonl(self.root / "fork_exclusions.jsonl"), excluded)
        next((self.root / "raw").glob("*.json")).unlink()
        self.assertFalse(verify_run(self.root)["checks"]["exclusion_evidence_matches"])

    def test_resume_keeps_original_cutoff_and_rejects_changed_sample_bounds(self):
        first = prepare_run(self.root, self.config, pilot=True, limit=2, offline=False)
        self.assertEqual(
            prepare_run(self.root, self.config, pilot=None, limit=None, offline=True),
            first,
        )
        with self.assertRaisesRegex(ValueError, "Sample bounds"):
            prepare_run(self.root, self.config, pilot=True, limit=3, offline=False)
        self.config.seed += 1
        with self.assertRaisesRegex(ValueError, "Configuration changed"):
            prepare_run(self.root, self.config, pilot=True, limit=2, offline=False)

    def test_offline_cannot_create_a_run(self):
        with self.assertRaisesRegex(ValueError, "existing run"):
            prepare_run(self.root, self.config, pilot=True, limit=2, offline=True)

    def test_historical_paths_do_not_block_resume_or_hide_parameter_changes(self):
        saved = prepare_run(self.root, self.config, pilot=True, limit=2, offline=False)
        saved["config"]["outputs"] = {
            "data_root": "data/skill-pattern-mine",
            "figures_root": "eval/tables-and-figures",
        }
        path = self.root / "run.json"
        path.write_text(json.dumps(saved))
        original = path.read_bytes()
        self.assertEqual(
            prepare_run(self.root, self.config, pilot=None, limit=None, offline=True),
            saved,
        )
        self.assertEqual(path.read_bytes(), original)
        self.config.seed += 1
        with self.assertRaisesRegex(ValueError, "Configuration changed"):
            prepare_run(self.root, self.config, pilot=None, limit=None, offline=True)

    def test_missing_outputs_cannot_pass_acceptance(self):
        prepare_run(self.root, self.config, pilot=True, limit=2, offline=False)
        self.assertEqual(verify_run(self.root)["status"], "failed")


if __name__ == "__main__":
    unittest.main()
