"""Regression checks for unstable fork inventories and evidence recovery."""

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from src.acquisition import import_recovery_cache, prepare_run, verify_run
from src.config import load_config
from src.github import ApiError, read_jsonl, write_json
from src.retrieve import retrieve_forks, retrieve_repositories
from test_acquisition import FixtureClient
from test_github import page


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

    def test_missing_previous_identity_is_not_silently_dropped(self):
        write_json(self.root / "recovery_inventory.json", {
            "owner/skills": [{"id": 999, "full_name": "missing/skills"}]
        })
        retrieve_forks(FixtureClient(), self.config, self.root, limit=None, pilot=True)
        coverage = json.loads((self.root / "fork_coverage.json").read_text())[0]
        self.assertEqual(coverage["missing_previous_ids"], [999])
        self.assertFalse(coverage["complete"])
        self.assertEqual(len(read_jsonl(self.root / "forks.jsonl")), 2)
        self.assertEqual(len(read_jsonl(self.root / "fork_errors.jsonl")), 1)
        self.assertEqual(verify_run(self.root)["status"], "failed")

    def test_missing_accessible_fork_is_reconciled_only_with_network_evidence(self):
        write_json(self.root / "recovery_inventory.json", {
            "owner/skills": [{"id": 999, "full_name": "renamed/skills"}]
        })

        class MissingClient(FixtureClient):
            def get(self, endpoint):
                if endpoint == "repositories/999":
                    body = super().get("repos/same/skills").body
                    return page({**body, "id": 999, "full_name": "renamed/skills", "parent": {"id": 1}})
                return super().get(endpoint)

        retrieve_forks(MissingClient(), self.config, self.root, limit=None, pilot=True)
        coverage = json.loads((self.root / "fork_coverage.json").read_text())[0]
        self.assertEqual(coverage["reconciled_ids"], [999])
        self.assertEqual(coverage["missing_previous_ids"], [])
        self.assertTrue(coverage["complete"])
        self.assertEqual(len(read_jsonl(self.root / "forks.jsonl")), 3)
        self.assertEqual(read_jsonl(self.root / "fork_errors.jsonl"), [])

    def test_missing_id_in_another_network_remains_an_error(self):
        write_json(self.root / "recovery_inventory.json", {
            "owner/skills": [{"id": 999, "full_name": "other/skills"}]
        })

        class ForeignClient(FixtureClient):
            def get(self, endpoint):
                if endpoint == "repositories/999":
                    body = super().get("repos/same/skills").body
                    return page({**body, "id": 999, "parent": {"id": 888}, "source": {"id": 888}})
                return super().get(endpoint)

        retrieve_forks(ForeignClient(), self.config, self.root, limit=None, pilot=True)
        coverage = json.loads((self.root / "fork_coverage.json").read_text())[0]
        self.assertEqual(coverage["missing_previous_ids"], [999])
        self.assertEqual(coverage["reconciled_ids"], [])
        self.assertEqual(len(read_jsonl(self.root / "forks.jsonl")), 2)

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
                    return page([
                        {**template, "id": n, "full_name": f"f{n}/skills"}
                        for n in range(250)
                    ] + [{**template, "id": 250, "full_name": "interrupt/skills"}])
                if endpoint == "repos/interrupt/skills":
                    raise KeyboardInterrupt
                if endpoint.startswith("repos/f") and endpoint.count("/") == 2:
                    body = super().get("repos/fork/skills").body
                    name = endpoint.removeprefix("repos/")
                    return page({**body, "id": int(name.split('/')[0][1:]), "full_name": name})
                return super().get(endpoint)

        with self.assertRaises(KeyboardInterrupt):
            retrieve_forks(InterruptedClient(), self.config, self.root, limit=None, pilot=True)
        self.assertEqual(len(read_jsonl(self.root / "forks.jsonl")), 250)
        summary = json.loads((self.root / "fork_summary.json").read_text())
        self.assertEqual(summary["upstreams_processed"], 0)
        self.assertFalse(summary["complete"])


class RecoveryTests(unittest.TestCase):
    """A new order must retain original settings and attributable raw evidence."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.source = Path(self.temp.name) / "original"
        self.root = Path(self.temp.name) / "recovered"
        self.config = load_config(Path("configs/skill-pattern-mine.yaml"))
        self.config.retrieval.fork_sort = "stargazers"
        self.original = prepare_run(self.source, self.config, pilot=False, limit=None,
                                    offline=False, source_run_id="candidates")
        self.config.retrieval.fork_sort = "oldest"

    def prepare(self, **kwargs):
        return prepare_run(self.root, self.config, pilot=None, limit=None, offline=False,
                           recovery_run_id=self.source.name, **kwargs)

    def cache(self, endpoint, body):
        version = self.config.github.api_version
        digest = hashlib.sha256(f"{version}:{endpoint}".encode()).hexdigest()
        path = self.source / "raw" / f"{digest}.json"
        write_json(path, {"endpoint": endpoint, "api_version": version, "status": 200,
                          "retrieved_at": "2026-09-22T14:48:04Z", "headers": {}, "body": body})
        return path

    def test_recovery_preserves_cutoff_source_and_allows_only_order_change(self):
        run = self.prepare()
        self.assertEqual(run["cutoff_utc"], self.original["cutoff_utc"])
        self.assertEqual(run["source_run_id"], "candidates")
        self.assertEqual(run["config"]["retrieval"]["fork_sort"], "oldest")
        self.assertEqual(json.loads((self.source / "run.json").read_text()), self.original)

    def test_recovery_rejects_changed_research_parameters(self):
        self.config.seed = 123
        with self.assertRaisesRegex(ValueError, "research settings"):
            self.prepare()
        self.assertFalse((self.root / "run.json").exists())

    def test_cache_import_preserves_bytes_but_never_reuses_listing(self):
        self.prepare()
        (self.source / "repositories.jsonl").write_text(json.dumps({
            "github_id": 1, "repository": {"full_name": "owner/skills"}
        }) + '\n')
        metadata = self.cache("repos/fork/skills", {"id": 3})
        listing = self.cache("repositories/1/forks?per_page=100&sort=stargazers", [
            {"id": 3, "full_name": "fork/skills"}, {"id": 3, "full_name": "fork/skills"}
        ])
        report = import_recovery_cache(self.source, self.root)
        self.assertEqual(report["responses"], 1)
        self.assertEqual(report["known_forks"], {"owner/skills": 1})
        self.assertEqual((self.root / "raw" / metadata.name).read_bytes(), metadata.read_bytes())
        self.assertFalse((self.root / "raw" / listing.name).exists())
        self.assertEqual(import_recovery_cache(self.source, self.root), report)

    def test_cache_filename_mismatch_is_rejected(self):
        self.prepare()
        path = self.cache("repos/fork/skills", {"id": 3})
        path.rename(path.with_name("wrong.json"))
        with self.assertRaisesRegex(ValueError, "request identity"):
            import_recovery_cache(self.source, self.root)

    def test_same_creation_order_reuses_listing_and_retains_prior_missing_ids(self):
        run = json.loads((self.source / "run.json").read_text())
        run["config"]["retrieval"]["fork_sort"] = "oldest"
        write_json(self.source / "run.json", run)
        (self.source / "repositories.jsonl").write_text(json.dumps({
            "github_id": 1, "repository": {"full_name": "owner/skills"}
        }) + '\n')
        write_json(self.source / "recovery_inventory.json", {
            "owner/skills": [{"id": 999, "full_name": "missing/skills"}]
        })
        self.prepare()
        listing = self.cache("repositories/1/forks?per_page=100&sort=oldest", [
            {"id": 3, "full_name": "fork/skills"}
        ])
        report = import_recovery_cache(self.source, self.root)
        self.assertEqual(report["listing_pages"], 1)
        self.assertEqual((self.root / "raw" / listing.name).read_bytes(), listing.read_bytes())
        self.assertEqual(report["known_forks"], {"owner/skills": 2})
        self.assertNotIn("response_sha256", report)

    def test_recovery_preserves_404_for_offline_skip_replay(self):
        self.prepare()
        path = self.cache("repositories/999", {"message": "Not Found"})
        saved = json.loads(path.read_text())
        saved["status"] = 404
        write_json(path, saved)
        report = import_recovery_cache(self.source, self.root)
        self.assertEqual(report["responses"], 1)
        self.assertEqual((self.root / "raw" / path.name).read_bytes(), path.read_bytes())

    def test_recovery_never_overwrites_a_different_frozen_response(self):
        self.prepare()
        path = self.cache("repos/fork/skills", {"id": 3})
        write_json(self.root / "raw" / path.name, {"different": True})
        with self.assertRaisesRegex(ValueError, "overwrite frozen"):
            import_recovery_cache(self.source, self.root)


if __name__ == "__main__":
    unittest.main()
