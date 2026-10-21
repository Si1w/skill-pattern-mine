"""Configuration is strict and exposes the derived screening facts the stages need."""

import unittest
from pathlib import Path

from pydantic import ValidationError

from src.config import ExperimentSettings, RepositoryReview, load_config


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

    def test_approved_repositories_exclude_manual_and_aggregator_reviews(self):
        screening = self.config.screening
        screening.reviews = {
            "Owner/Kept": RepositoryReview(is_aggregator=False, reason="Approved."),
            "owner/manual": RepositoryReview(is_aggregator=False, exclude=True, reason="Excluded."),
            "owner/aggregator": RepositoryReview(is_aggregator=True, reason="Aggregator."),
        }
        self.assertEqual(screening.approved_repositories(), {"owner/kept"})
        self.assertIsNotNone(screening.review_for("OWNER/KEPT"))
        self.assertIsNone(screening.review_for("owner/other"))

    def test_lowest_fork_threshold_includes_sensitivity_values(self):
        screening = self.config.screening
        screening.minimum_forks, screening.sensitivity_fork_thresholds = 1000, [500, 2000]
        self.assertEqual(screening.lowest_fork_threshold, 500)
