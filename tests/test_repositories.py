"""Behavioral checks for complete trees and repository screening."""

import unittest
from datetime import datetime, timezone

from src.config import RepositoryReview, ScreeningSettings
from src.domain import Repository, RetrievalChannel
from src.github import ApiError
from src.repositories import complete_tree, screen_repository
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


class ScreeningTests(unittest.TestCase):
    """Human review cannot be replaced with engineering defaults."""

    def setUp(self):
        self.repo = Repository(
            full_name="a/b",
            channels=[RetrievalChannel.INTENT],
            retrieved_at=datetime.now(timezone.utc),
            forks_count=1200,
            stars_count=0,
            skill_package_paths=[],
        )
        self.config = ScreeningSettings(
            minimum_forks=1000,
            sensitivity_fork_thresholds=[500, 2000],
        )
        self.entries = [entry("skills/one/SKILL.md"), entry("README.md")]

    def screen(self):
        from src.domain import TreeEntry

        return screen_repository(
            self.repo,
            [TreeEntry.model_validate(item) for item in self.entries],
            self.config,
        )

    def test_unreviewed_candidate_remains_pending(self):
        result = self.screen()
        self.assertFalse(result.screening_complete)
        self.assertIsNone(result.excluded_by)
        self.assertEqual(result.skill_centricity.ratio, 0.5)

    def test_keyword_hit_alone_does_not_exclude_aggregator(self):
        self.repo.aggregator_keyword_hit = True
        self.assertIsNone(self.screen().excluded_by)

    def test_retention_requires_manual_review(self):
        self.assertFalse(self.screen().screening_complete)
        self.config.reviews["a/b"] = RepositoryReview(
            is_aggregator=False, reason="Inspected the repository purpose."
        )
        result = self.screen()
        self.assertTrue(result.screening_complete)
        self.assertIsNone(result.excluded_by)

    def test_no_manifest_is_structurally_excluded(self):
        self.entries = [entry("README.md")]
        self.assertEqual(self.screen().excluded_by, "not_skill_centric")

    def test_low_ratio_stays_descriptive_and_manual_exclusion_applies(self):
        self.assertFalse(self.screen().screening_complete)
        self.config.reviews["a/b"] = RepositoryReview(
            is_aggregator=False, exclude=False, reason="User approved the repository."
        )
        result = self.screen()
        self.assertTrue(result.screening_complete)
        self.assertIsNone(result.excluded_by)
        self.assertEqual(result.skill_centricity.ratio, 0.5)
        self.config.reviews["a/b"].exclude = True
        self.assertEqual(self.screen().excluded_by, "manual")

    def test_fork_threshold_precedes_content_rules(self):
        self.repo.forks_count = 499
        self.entries = []
        self.assertEqual(self.screen().excluded_by, "fork_threshold")

    def test_manual_aggregator_review_excludes_with_reason(self):
        self.config.reviews["a/b"] = RepositoryReview(
            is_aggregator=True, reason="Contains pointers to external repositories."
        )
        result = self.screen()
        self.assertEqual(result.excluded_by, "aggregator")
        self.assertIn("pointers", result.exclusion_note)


if __name__ == "__main__":
    unittest.main()
