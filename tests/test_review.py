"""Check that review exports preserve pending decisions and screening scope."""

import csv
import tempfile
import unittest
from pathlib import Path

import yaml

from src.github import write_json, write_jsonl
from src.review import export_repository_review


class ReviewTests(unittest.TestCase):
    """Human assessments must remain separate from measured repository facts."""

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        write_json(
            self.root / "run.json",
            {
                "cutoff_utc": "2026-09-16T12:00:00+00:00",
                "config": {
                    "screening": {
                        "minimum_forks": 1000,
                        "sensitivity_fork_thresholds": [500, 2000],
                        "skill_centricity_threshold": None,
                        "reviews": {},
                    }
                },
            },
        )
        write_json(self.root / "repository_summary.json", {"complete": False})
        write_json(
            self.root / "search_coverage.json",
            [{"complete": False, "stop_reason": "search_limit"}],
        )
        snapshots, metadata = [], []
        for identity, (forks, packages) in enumerate(
            [(1200, ["skills/example"]), (600, ["."]), (1500, []), (400, ["."])]
        ):
            name = f"owner/repo{identity}"
            snapshots.append(
                {
                    "github_id": identity,
                    "tree_complete": True,
                    "default_branch_sha": "a" * 40,
                    "evidence": [{"channel": "intent", "source": "topic:skills"}],
                    "repository": {
                        "full_name": name,
                        "forks_count": forks,
                        "skill_package_paths": packages,
                        "skill_centricity": {
                            "skill_files": 1 if packages else 0,
                            "tracked_files": 10,
                            "ratio": 0.1 if packages else 0,
                        },
                        "aggregator_keyword_hit": True,
                        "channels": ["intent"],
                        "excluded_by": "fork_threshold" if forks < 1000 else None,
                        "exclusion_note": None,
                        "retrieved_at": "2026-09-16T12:00:00+00:00",
                    },
                }
            )
            metadata.append(
                {"metadata": {"id": identity, "html_url": f"https://github.com/{name}"}}
            )
        write_jsonl(self.root / "repositories.jsonl", snapshots)
        write_jsonl(self.root / "candidate_metadata.jsonl", metadata)

    def test_pending_reviews_and_sensitivity_candidates_remain_visible(self):
        export_repository_review(self.root)
        worksheet = yaml.safe_load((self.root / "repository_review.yaml").read_text())
        self.assertFalse(worksheet["summary"]["complete"])
        self.assertEqual(worksheet["search_coverage"][0]["stop_reason"], "search_limit")
        candidates = worksheet["repositories"]
        self.assertEqual(set(candidates), {"owner/repo0", "owner/repo1"})
        self.assertEqual(candidates["owner/repo1"]["scope"], "sensitivity_only")
        self.assertIsNone(candidates["owner/repo0"]["review"]["is_aggregator"])
        self.assertIsNone(candidates["owner/repo0"]["review"]["exclude"])
        with (self.root / "repository_candidates.csv").open() as stream:
            rows = list(csv.DictReader(stream))
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[2]["package_count"], "0")

    def test_reexport_does_not_overwrite_human_decisions(self):
        path = self.root / "repository_review.yaml"
        path.write_text("human decision")
        with self.assertRaisesRegex(ValueError, "already exist"):
            export_repository_review(self.root)
        self.assertEqual(path.read_text(), "human decision")
        self.assertFalse((self.root / "repository_candidates.csv").exists())

    def test_unfinished_collection_cannot_be_exported_as_empty(self):
        (self.root / "repositories.jsonl").unlink()
        with self.assertRaisesRegex(ValueError, "has not produced"):
            export_repository_review(self.root)
        self.assertFalse((self.root / "repository_review.yaml").exists())
