"""Keep current configuration strict while reading historical snapshots."""

import unittest
from pathlib import Path

from pydantic import ValidationError

from src.config import ExperimentSettings, load_config, load_saved_config


class ConfigurationTests(unittest.TestCase):
    """Retired paths must not hide changes to experiment settings."""

    def test_saved_paths_are_removed_without_mutating_the_snapshot(self):
        config = load_config(Path("configs/skill-pattern-mine.yaml"))
        snapshot = config.model_dump(mode="json")
        snapshot["outputs"] = {
            "data_root": "data/skill-pattern-mine",
            "figures_root": "eval/tables-and-figures",
        }
        self.assertEqual(load_saved_config(snapshot), config)
        self.assertIn("outputs", snapshot)
        with self.assertRaises(ValidationError):
            ExperimentSettings.model_validate(snapshot)

    def test_saved_unknown_experiment_fields_still_fail(self):
        snapshot = load_config(Path("configs/skill-pattern-mine.yaml")).model_dump()
        snapshot["unknown_parameter"] = 1
        with self.assertRaises(ValidationError):
            load_saved_config(snapshot)
