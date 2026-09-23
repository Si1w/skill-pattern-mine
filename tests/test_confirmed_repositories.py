"""Verify selection from frozen evidence without broadening the approved cohort."""

import json
import tempfile
import unittest
from pathlib import Path

from src.acquisition import import_confirmed_repositories, prepare_run, verify_run
from src.config import RepositoryReview, load_config
from src.github import read_jsonl, write_jsonl
from src.retrieve import retrieve_forks, retrieve_repositories
from test_acquisition import FixtureClient


class ConfirmedRepositoryTests(unittest.TestCase):
    """Keep source evidence intact and reject incomplete or conflicting selections."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.source = Path(self.temp.name) / "source"
        self.target = Path(self.temp.name) / "target"
        self.config = load_config(Path("configs/skill-pattern-mine.yaml"))
        self.config.screening.selection_mode = "calibrated_ratio"
        self.config.screening.reviews = {}
        self.config.retrieval.topic_seeds = []
        self.config.retrieval.description_queries = ["skill in:description"]
        self.config.retrieval.manifest_queries = ["filename:plugin.json"]
        prepare_run(self.source, self.config, pilot=True, limit=2, offline=False)
        retrieve_repositories(FixtureClient(), self.config, self.source, limit=2)
        self.config.screening.selection_mode = "confirmed_reviews"
        self.config.screening.reviews["owner/skills"] = RepositoryReview(
            is_aggregator=False, exclude=False, reason="Approved by the user."
        )

    def prepare(self):
        return prepare_run(
            self.target, self.config, pilot=True, limit=2, offline=False,
            source_run_id=self.source.name,
        )

    def test_selected_flow_preserves_source_and_replays_with_frozen_settings(self):
        original = (self.source / "repositories.jsonl").read_bytes()
        run = self.prepare()
        import_confirmed_repositories(self.source, self.target, self.config)
        records = read_jsonl(self.target / "repositories.jsonl")
        self.assertEqual(len(records), 1)
        self.assertTrue(records[0]["repository"]["screening_complete"])
        retrieve_forks(FixtureClient(), self.config, self.target, limit=2, pilot=True)
        report = verify_run(self.target)
        self.assertEqual(report["status"], "passed", report)
        import_confirmed_repositories(self.source, self.target, self.config)
        self.assertEqual((self.source / "repositories.jsonl").read_bytes(), original)
        self.assertEqual(
            prepare_run(self.target, self.config, pilot=None, limit=None, offline=True),
            run,
        )
        with self.assertRaisesRegex(ValueError, "Source run"):
            prepare_run(self.target, self.config, pilot=None, limit=None, offline=True, source_run_id="other")

    def test_missing_approved_repository_fails_before_writing_selection(self):
        self.config.screening.reviews["missing/repo"] = RepositoryReview(
            is_aggregator=False, reason="Approved."
        )
        self.prepare()
        with self.assertRaisesRegex(ValueError, "Missing approved"):
            import_confirmed_repositories(self.source, self.target, self.config)
        self.assertFalse((self.target / "repositories.jsonl").exists())

    def test_duplicate_source_identity_is_rejected(self):
        path = self.source / "repositories.jsonl"
        rows = read_jsonl(path)
        write_jsonl(path, [*rows, rows[0]])
        self.prepare()
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            import_confirmed_repositories(self.source, self.target, self.config)

    def test_cosmetic_source_change_does_not_invalidate_saved_selection(self):
        self.prepare()
        import_confirmed_repositories(self.source, self.target, self.config)
        path = self.source / "run.json"
        path.write_text(path.read_text() + "\n")
        import_confirmed_repositories(self.source, self.target, self.config)

    def test_changed_tree_cannot_replace_saved_selection(self):
        self.prepare()
        import_confirmed_repositories(self.source, self.target, self.config)
        path = self.source / "trees/1.jsonl"
        rows = read_jsonl(path)
        rows[0]["sha"] = "changed"
        write_jsonl(path, rows)
        with self.assertRaisesRegex(ValueError, "Source evidence changed"):
            import_confirmed_repositories(self.source, self.target, self.config)

    def test_repository_count_is_not_limited_by_forks_per_repository(self):
        rows = read_jsonl(self.source / "repositories.jsonl")
        original = rows[0]
        for number in (10, 11):
            row = json.loads(json.dumps(original))
            name = f"owner/extra{number}"
            row['github_id'] = number
            row['repository']['full_name'] = name
            rows.append(row)
            (self.source / 'trees' / f'{number}.jsonl').write_bytes(
                (self.source / 'trees' / f"{original['github_id']}.jsonl").read_bytes()
            )
            self.config.screening.reviews[name] = RepositoryReview(
                is_aggregator=False, reason="Approved."
            )
        write_jsonl(self.source / 'repositories.jsonl', rows)
        self.prepare()
        import_confirmed_repositories(self.source, self.target, self.config)
        self.assertEqual(len(read_jsonl(self.target / 'repositories.jsonl')), 3)
        report = verify_run(self.target)
        self.assertTrue(report['checks']['sample_bounds_respected'])
        self.assertTrue(report['checks']['confirmed_membership_matches'])
        self.assertEqual(report['status'], 'failed')  # Forks have not been collected.
