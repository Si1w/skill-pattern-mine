"""Check extraction scope before any expensive command line work."""

import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.acquisition import prepare_run
from src.config import load_config
from src.github import write_json
from src.retrieve import retrieve_forks, retrieve_repositories
from test_acquisition import FixtureClient

PROJECT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("acquisition_main", PROJECT / "eval/skill-pattern-mine/main.py")
ENTRY = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ENTRY)


class ExtractionCommandTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.project = Path(self.temp.name)
        self.root = self.project / "data/skill-pattern-mine/runs/fixture"
        self.config = load_config(PROJECT / "configs/skill-pattern-mine.yaml")
        self.config.screening.selection_mode = "calibrated_ratio"
        self.config.retrieval.topic_seeds = []

    def run_command(self, *extra):
        with (
            patch.object(ENTRY, "PROJECT_ROOT", self.project),
            patch.object(ENTRY, "load_config", return_value=self.config),
            patch("sys.argv", ["main.py", "--step", "extract", "--run_id", "fixture", *extra]),
            patch.object(ENTRY, "extract_monthly") as extract,
        ):
            extract.return_value = {
                "status": "passed", "history_backend": "pydriller", "git_fetches": 0,
                "git_cache_hits": 0, "errors": 0, "records": 1,
                "customization_candidates": 1, "excluded_unresolved_upstream": 0,
            }
            result = ENTRY.main()
            return result, extract.call_args

    def test_full_run_cannot_bypass_completion_with_partial_flag(self):
        prepare_run(self.root, self.config, pilot=False, limit=None, offline=False)
        code, call = self.run_command("--allow_partial")
        self.assertEqual(code, 1)
        self.assertIsNone(call)
        self.assertFalse((self.root / "extraction.json").exists())

    def test_unfinished_pilot_requires_explicit_partial_flag(self):
        prepare_run(self.root, self.config, pilot=True, limit=2, offline=False)
        retrieve_repositories(FixtureClient(), self.config, self.root, limit=2)
        retrieve_forks(FixtureClient(), self.config, self.root, limit=2, pilot=True)
        write_json(self.root / "progress.json", {"state": "running"})
        code, call = self.run_command()
        self.assertEqual(code, 1)
        self.assertIsNone(call)
        code, call = self.run_command("--allow_partial")
        self.assertEqual(code, 0)
        self.assertTrue(call.kwargs["partial_acquisition"])

    def test_completed_pilot_passes_normal_extraction_inputs(self):
        prepare_run(self.root, self.config, pilot=True, limit=2, offline=False)
        retrieve_repositories(FixtureClient(), self.config, self.root, limit=2)
        retrieve_forks(FixtureClient(), self.config, self.root, limit=2, pilot=True)
        code, call = self.run_command()
        self.assertEqual(code, 0)
        self.assertFalse(call.kwargs["partial_acquisition"])


if __name__ == "__main__":
    unittest.main()
