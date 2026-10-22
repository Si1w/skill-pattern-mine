"""Behavioral checks for complete trees and repository screening."""

import unittest
from datetime import datetime, timezone

from src.config import ScreeningSettings
from src.domain import Repository, RetrievalChannel
from src.github import ApiError
from src.domain import RetrievalEvidence
from src.repositories import complete_tree, fetch_candidate_metadata, fork_bands, screen_repository
from test_github import Pages, page


def entry(path, kind="blob", sha="blob"):
    """A minimal tree entry as returned by GitHub."""
    return {
        "path": path,
        "type": kind,
        "mode": "040000" if kind == "tree" else "100644",
        "sha": sha,
    }


class TreeTests(unittest.TestCase):
    """A truncated inventory must be expanded or fail explicitly."""

    def test_truncated_recursive_tree_expands_subtrees_at_each_path(self):
        client = Pages(
            {
                "repos/a/b/git/trees/root?recursive=1": page(
                    {"truncated": True, "tree": []}
                ),
                "repos/a/b/git/trees/root": page(
                    {
                        "truncated": False,
                        "tree": [
                            entry("one", "tree", "sub"),
                            entry("two", "tree", "sub"),
                        ],
                    }
                ),
                "repos/a/b/git/trees/sub": page(
                    {"truncated": False, "tree": [entry("SKILL.md")]}
                ),
            }
        )
        result = complete_tree(client, "a/b", "root")
        self.assertEqual(
            {item.path for item in result if item.type == "blob"},
            {"one/SKILL.md", "two/SKILL.md"},
        )

    def test_truncated_tree_is_not_expanded_unless_asked(self):
        client = Pages(
            {"repos/a/b/git/trees/root?recursive=1": page({"truncated": True, "tree": []})}
        )
        self.assertIsNone(complete_tree(client, "a/b", "root", expand_truncated=False))

    def test_truncated_subtree_cannot_be_used_for_ratio(self):
        client = Pages(
            {
                "repos/a/b/git/trees/root?recursive=1": page(
                    {"truncated": True, "tree": []}
                ),
                "repos/a/b/git/trees/root": page({"truncated": True, "tree": []}),
            }
        )
        with self.assertRaises(ApiError):
            complete_tree(client, "a/b", "root")


class ForkBandTests(unittest.TestCase):
    """Intent queries are split until every band can be listed completely."""

    def test_bands_split_until_each_total_is_under_the_search_cap(self):
        totals = {">=1000": 1164, "1000..1999": 539, ">=2000": 625}

        class Client:
            def get(self, endpoint):
                qualifier = endpoint.split("forks%3A")[1].split("+fork")[0]
                return page({"total_count": totals[qualifier.replace("%3E%3D", ">=")]})

        self.assertEqual(
            fork_bands(Client(), "skill", 1000, None), ["forks:1000..1999", "forks:>=2000"]
        )

    def test_small_total_is_one_open_band(self):
        class Client:
            def get(self, endpoint):
                return page({"total_count": 3})

        self.assertEqual(fork_bands(Client(), "skill", 1000, None), ["forks:>=1000"])


class CandidateMetadataTests(unittest.TestCase):
    """A candidate that disappeared after the search is a recorded skip, not a failure."""

    def test_missing_candidate_is_skipped_and_other_errors_are_kept(self):
        class Client:
            def get(self, endpoint):
                if endpoint == "repos/gone/repo":
                    raise ApiError("not found", status=404)
                raise ApiError("server error", status=500)

        evidence = [RetrievalEvidence(channel=RetrievalChannel.INTENT, source="skill")]
        errors, skips = [], []
        rows = fetch_candidate_metadata(
            Client(), {"gone/repo": evidence, "broken/repo": evidence}, errors, skips
        )
        self.assertEqual(rows, [])
        self.assertEqual([item["full_name"] for item in skips], ["gone/repo"])
        self.assertEqual([item["subject"] for item in errors], ["broken/repo"])


class ScreeningTests(unittest.TestCase):
    """Confirmation cannot be replaced with engineering defaults."""

    def setUp(self):
        self.repo = Repository(
            full_name="a/b",
            channels=[RetrievalChannel.INTENT],
            retrieved_at=datetime.now(timezone.utc),
            forks_count=1200,
            stars_count=5000,
            skill_package_paths=[],
        )
        self.config = ScreeningSettings(minimum_forks=1000, maximum_forks_per_star=1.0, maximum_packages=300)
        self.entries = [entry("skills/one/SKILL.md"), entry("README.md")]

    def screen(self):
        from src.domain import TreeEntry

        return screen_repository(
            self.repo,
            [TreeEntry.model_validate(item) for item in self.entries],
            self.config,
        )

    def test_unconfirmed_candidate_remains_pending(self):
        result = self.screen()
        self.assertFalse(result.screening_complete)
        self.assertIsNone(result.excluded_by)
        self.assertEqual(result.skill_centricity.ratio, 0.5)

    def test_keyword_hit_alone_does_not_exclude_aggregator(self):
        self.repo.aggregator_keyword_hit = True
        self.assertIsNone(self.screen().excluded_by)

    def test_retention_requires_confirmation(self):
        self.assertFalse(self.screen().screening_complete)
        self.config.repositories = ["A/B"]
        result = self.screen()
        self.assertTrue(result.screening_complete)
        self.assertIsNone(result.excluded_by)

    def test_no_manifest_is_structurally_excluded(self):
        self.entries = [entry("README.md")]
        self.assertEqual(self.screen().excluded_by, "not_skill_centric")

    def test_low_ratio_stays_descriptive(self):
        self.config.repositories = ["a/b"]
        result = self.screen()
        self.assertTrue(result.screening_complete)
        self.assertIsNone(result.excluded_by)
        self.assertEqual(result.skill_centricity.ratio, 0.5)

    def test_fork_threshold_precedes_content_rules(self):
        self.repo.forks_count = 499
        self.entries = []
        self.assertEqual(self.screen().excluded_by, "fork_threshold")

    def test_more_forks_than_stars_is_a_fork_campaign(self):
        self.repo.stars_count = 1199
        result = self.screen()
        self.assertEqual(result.excluded_by, "forks_exceed_stars")
        self.assertTrue(result.screening_complete)

    def test_too_many_packages_is_catalog_scale(self):
        self.config.maximum_packages = 1
        self.entries = [entry("skills/one/SKILL.md"), entry("skills/two/SKILL.md")]
        self.assertEqual(self.screen().excluded_by, "catalog_scale")
        self.config.maximum_packages = 2
        self.assertIsNone(self.screen().excluded_by)

    def test_structural_exclusion_applies_to_confirmed_repository(self):
        self.config.repositories = ["a/b"]
        self.entries = [entry("README.md")]
        result = self.screen()
        self.assertEqual(result.excluded_by, "not_skill_centric")
        self.assertTrue(result.screening_complete)


if __name__ == "__main__":
    unittest.main()
