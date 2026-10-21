"""Fork enumeration, frozen comparisons and inventory consistency."""

import json
import tempfile
import unittest
from pathlib import Path

from src.config import load_config
from src.domain import Fork
from src.forks import compare_fork, retrieve_forks
from src.github import ApiError
from src.repositories import retrieve_repositories
from src.run import prepare_run
from src.storage import read_jsonl, write_json
from src.verify import verify_run
from test_acquisition import FixtureClient
from test_github import Pages, page


def fork(sha="head"):
    return Fork(
        upstream="a/b",
        full_name="c/b",
        owner="c",
        created_at="2026-08-01T00:00:00Z",
        pushed_at="2026-09-01T00:00:00Z",
        retrieved_at="2026-09-16T00:00:00Z",
        default_branch="main",
        default_branch_sha=sha,
    )


def commit(sha, parents):
    return {
        "sha": sha,
        "parents": [{"sha": parent} for parent in parents],
        "author": None,
        "commit": {
            "tree": {"sha": "tree"},
            "author": {"date": "2026-08-31T23:00:00Z"},
            "committer": {"date": "2026-09-01T00:00:00Z"},
            "message": "A change",
        },
    }


class ComparisonTests(unittest.TestCase):
    """Comparisons use immutable SHAs and preserve dates and parent order."""

    def test_comparison_preserves_source_metadata(self):
        client = Pages({
            "repos/c/b/compare/base...head?per_page=100": page({
                "status": "ahead",
                "ahead_by": 1,
                "behind_by": 0,
                "merge_base_commit": {"sha": "base"},
                "commits": [commit("new", ["first", "second"])],
            })
        })
        result = compare_fork(client, fork(), 3, "base", per_page=100, limit=None)
        self.assertTrue(result.commits_complete)
        self.assertEqual(result.commits[0].parent_shas, ["first", "second"])
        self.assertNotEqual(result.commits[0].author_date, result.commits[0].committer_date)
        self.assertIsNone(result.commits[0].author_login)

    def test_comparison_follows_next_link_and_checks_total(self):
        first = "repos/c/b/compare/base...head?per_page=1"
        second = first + "&page=2"
        metadata = {"status": "ahead", "ahead_by": 2, "behind_by": 0, "merge_base_commit": {"sha": "base"}}
        client = Pages({
            first: page({**metadata, "commits": [commit("one", [])]}, "https://api.github.com/" + second),
            second: page({**metadata, "commits": [commit("two", [])]}),
        })
        result = compare_fork(client, fork(), 3, "base", per_page=1, limit=None)
        self.assertTrue(result.commits_complete)
        self.assertEqual([item.sha for item in result.commits], ["one", "two"])
        self.assertIn(second, client.calls)

    def test_missing_comparison_commits_are_an_error(self):
        client = Pages({
            "repos/c/b/compare/base...head?per_page=100": page({
                "status": "ahead",
                "ahead_by": 1,
                "behind_by": 0,
                "merge_base_commit": {"sha": "base"},
                "commits": [],
            })
        })
        with self.assertRaises(ApiError):
            compare_fork(client, fork(), 3, "base", per_page=100, limit=None)


class InventoryTests(unittest.TestCase):
    """Reject suspect inventories before spending requests on comparisons."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.config = load_config(Path("configs/skill-pattern-mine.yaml"))
        self.config.screening.selection_mode = "calibrated_ratio"
        self.config.retrieval.topic_seeds = []
        prepare_run(self.root, self.config, pilot=True, limit=2, offline=False)
        retrieve_repositories(FixtureClient(), self.config, self.root, limit=2)

    def test_duplicate_pages_fail_before_any_fork_metadata_request(self):
        calls = []

        class DuplicateClient(FixtureClient):
            def get(self, endpoint):
                calls.append(endpoint)
                if "/forks?" in endpoint:
                    row = super().get(endpoint).body[0]
                    return page([row, row])
                return super().get(endpoint)

        retrieve_forks(DuplicateClient(), self.config, self.root, limit=None, pilot=True)
        self.assertEqual(len(calls), 1)
        coverage = json.loads((self.root / "fork_coverage.json").read_text())[0]
        self.assertFalse(coverage["complete"])
        self.assertEqual(coverage["duplicate_rows"], 1)
        self.assertEqual(len(read_jsonl(self.root / "fork_errors.jsonl")), 1)
        self.assertEqual(read_jsonl(self.root / "forks.jsonl"), [])

    def test_creation_time_reversal_is_not_complete_coverage(self):
        class ReversedClient(FixtureClient):
            def get(self, endpoint):
                result = super().get(endpoint)
                return page(list(reversed(result.body))) if "/forks?" in endpoint else result

        retrieve_forks(ReversedClient(), self.config, self.root, limit=None, pilot=True)
        coverage = json.loads((self.root / "fork_coverage.json").read_text())[0]
        self.assertEqual(coverage["creation_time_inversions"], 1)
        self.assertFalse(coverage["complete"])

    def test_metadata_404_recovers_by_same_numeric_identity(self):
        class RenamedClient(FixtureClient):
            def get(self, endpoint):
                if endpoint == "repos/fork/skills":
                    raise ApiError("Old name unavailable", status=404)
                if endpoint == "repositories/3":
                    return super().get("repos/fork/skills")
                return super().get(endpoint)

        results = retrieve_forks(RenamedClient(), self.config, self.root, limit=2, pilot=True)
        self.assertEqual(len(results), 2)
        self.assertEqual(read_jsonl(self.root / "fork_errors.jsonl"), [])

    def test_numeric_fallback_still_validates_identity(self):
        class ReplacedClient(FixtureClient):
            def get(self, endpoint):
                if endpoint == "repos/fork/skills":
                    raise ApiError("Old name unavailable", status=404)
                if endpoint == "repositories/3":
                    return super().get("repos/same/skills")
                return super().get(endpoint)

        results = retrieve_forks(ReplacedClient(), self.config, self.root, limit=2, pilot=True)
        self.assertEqual(len(results), 1)
        self.assertEqual(len(read_jsonl(self.root / "fork_errors.jsonl")), 1)

    def test_other_failures_do_not_trigger_numeric_fallback(self):
        calls = []

        class UnauthorizedClient(FixtureClient):
            def get(self, endpoint):
                calls.append(endpoint)
                if endpoint == "repos/fork/skills":
                    raise ApiError("Unauthorized", status=401)
                return super().get(endpoint)

        retrieve_forks(UnauthorizedClient(), self.config, self.root, limit=2, pilot=True)
        self.assertNotIn("repositories/3", calls)
        self.assertEqual(len(read_jsonl(self.root / "fork_errors.jsonl")), 1)

    def test_acceptance_independently_checks_inventory_consistency(self):
        retrieve_forks(FixtureClient(), self.config, self.root, limit=2, pilot=True)
        self.assertEqual(verify_run(self.root)["status"], "passed")
        coverage = json.loads((self.root / "fork_coverage.json").read_text())
        coverage[0]["duplicate_rows"] = 1
        write_json(self.root / "fork_coverage.json", coverage)
        self.assertFalse(verify_run(self.root)["checks"]["fork_inventory_consistent"])

    def test_interruption_preserves_checkpoint_within_first_upstream(self):
        class InterruptedClient(FixtureClient):
            def get(self, endpoint):
                if "/forks?" in endpoint:
                    template = super().get(endpoint).body[0]
                    return page(
                        [{**template, "id": n, "full_name": f"f{n}/skills"} for n in range(250)]
                        + [{**template, "id": 250, "full_name": "interrupt/skills"}]
                    )
                if endpoint == "repos/interrupt/skills":
                    raise KeyboardInterrupt
                if endpoint.startswith("repos/f") and endpoint.count("/") == 2:
                    body = super().get("repos/fork/skills").body
                    name = endpoint.removeprefix("repos/")
                    return page({**body, "id": int(name.split("/")[0][1:]), "full_name": name})
                return super().get(endpoint)

        with self.assertRaises(KeyboardInterrupt):
            retrieve_forks(InterruptedClient(), self.config, self.root, limit=None, pilot=True)
        self.assertEqual(len(read_jsonl(self.root / "forks.jsonl")), 250)
        summary = json.loads((self.root / "fork_summary.json").read_text())
        self.assertEqual(summary["upstreams_processed"], 0)
        self.assertFalse(summary["complete"])


if __name__ == "__main__":
    unittest.main()
