"""Configuration is strict and exposes the derived screening facts the stages need."""

import unittest
from pathlib import Path

from pydantic import ValidationError

from src.config import ExperimentSettings, ScreeningSettings, load_config


class ConfigurationTests(unittest.TestCase):
    def setUp(self):
        self.config = load_config(Path("configs/skill-pattern-mine.yaml"))

    def test_unknown_fields_are_rejected(self):
        snapshot = self.config.model_dump()
        snapshot["unknown_parameter"] = 1
        with self.assertRaises(ValidationError):
            ExperimentSettings.model_validate(snapshot)

    def test_round_trip_through_json_is_stable(self):
        self.assertEqual(ExperimentSettings.model_validate_json(self.config.model_dump_json()), self.config)

    def test_confirmed_repositories_are_compared_without_case(self):
        screening = self.config.screening
        screening.repositories = ["Owner/Kept"]
        self.assertEqual(screening.confirmed_repositories(), {"owner/kept"})

    def test_duplicate_confirmed_repository_is_rejected(self):
        with self.assertRaises(ValidationError):
            ScreeningSettings(
                minimum_forks=1000, maximum_forks_per_star=1.0, maximum_packages=300, repositories=["a/b", "A/B"]
            )

    def test_shipped_configuration_lists_thirty_four_confirmed_repositories(self):
        self.assertEqual(len(self.config.screening.confirmed_repositories()), 34)
        self.assertEqual(self.config.screening.minimum_forks, 2000)
        self.assertEqual(self.config.screening.maximum_packages, 300)

