"""Behavioral checks for complete trees, screening and frozen fork histories."""

import unittest
from datetime import datetime, timezone

from src.config import RepositoryReview, ScreeningSettings
from src.domain import Repository, RetrievalChannel
from src.retrieve import complete_tree, compare_fork, screen_repository
from src.github import ApiError
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
    """Human review and calibration cannot be replaced with engineering defaults."""

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
            skill_centricity_metric="tracked_package_blobs_over_all_tracked_blobs",
            skill_centricity_threshold=None,
        )
        self.entries = [entry("skills/one/SKILL.md"), entry("README.md")]

    def screen(self):
        from src.domain import TreeEntry

        return screen_repository(
            self.repo,
            [TreeEntry.model_validate(item) for item in self.entries],
            self.config,
        )

    def test_uncalibrated_candidate_remains_pending(self):
        result = self.screen()
        self.assertFalse(result.screening_complete)
        self.assertIsNone(result.excluded_by)
        self.assertEqual(result.skill_centricity.ratio, 0.5)

    def test_keyword_hit_alone_does_not_exclude_aggregator(self):
        self.repo.aggregator_keyword_hit = True
        self.assertIsNone(self.screen().excluded_by)

    def test_retention_requires_threshold_and_manual_review(self):
        self.config.skill_centricity_threshold = 0.4
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

    def test_confirmed_review_keeps_ratio_descriptive_and_unreviewed_pending(self):
        self.config.selection_mode = "confirmed_reviews"
        self.config.skill_centricity_threshold = 0.9
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
        self.config.skill_centricity_threshold = 0.4
        self.config.reviews["a/b"] = RepositoryReview(
            is_aggregator=True, reason="Contains pointers to external repositories."
        )
        result = self.screen()
        self.assertEqual(result.excluded_by, "aggregator")
        self.assertIn("pointers", result.exclusion_note)


class ComparisonTests(unittest.TestCase):
    """Comparisons use immutable SHAs and preserve dates and parent order."""

    def test_comparison_preserves_source_metadata(self):
        from src.domain import Fork

        fork = Fork(
            upstream="a/b",
            full_name="c/b",
            owner="c",
            created_at="2026-08-01T00:00:00Z",
            pushed_at="2026-09-01T00:00:00Z",
            retrieved_at="2026-09-16T00:00:00Z",
            default_branch="main",
            default_branch_sha="head",
        )
        commit = {
            "sha": "new",
            "parents": [{"sha": "first"}, {"sha": "second"}],
            "author": None,
            "commit": {
                "tree": {"sha": "tree"},
                "author": {"date": "2026-08-31T23:00:00Z"},
                "committer": {"date": "2026-09-01T00:00:00Z"},
                "message": "A change",
            },
        }
        client = Pages(
            {
                "repos/c/b/compare/base...head?per_page=100": page(
                    {
                        "status": "ahead",
                        "ahead_by": 1,
                        "behind_by": 0,
                        "merge_base_commit": {"sha": "base"},
                        "commits": [commit],
                    }
                )
            }
        )
        result = compare_fork(client, fork, 3, "base", per_page=100, limit=None)
        self.assertTrue(result.commits_complete)
        self.assertEqual(result.commits[0].parent_shas, ["first", "second"])
        self.assertNotEqual(
            result.commits[0].author_date, result.commits[0].committer_date
        )
        self.assertIsNone(result.commits[0].author_login)

    def test_comparison_follows_next_link_and_checks_total(self):
        from src.domain import Fork

        fork = Fork(
            upstream="a/b",
            full_name="c/b",
            owner="c",
            created_at="2026-08-01T00:00:00Z",
            pushed_at="2026-09-01T00:00:00Z",
            retrieved_at="2026-09-16T00:00:00Z",
            default_branch="main",
            default_branch_sha="head",
        )
        commit = {
            "sha": "one",
            "parents": [],
            "author": None,
            "commit": {
                "tree": {"sha": "tree"},
                "author": {"date": "2026-08-31T23:00:00Z"},
                "committer": {"date": "2026-09-01T00:00:00Z"},
                "message": "A change",
            },
        }
        first = "repos/c/b/compare/base...head?per_page=1"
        second = first + "&page=2"
        metadata = {
            "status": "ahead",
            "ahead_by": 2,
            "behind_by": 0,
            "merge_base_commit": {"sha": "base"},
        }
        client = Pages(
            {
                first: page(
                    {**metadata, "commits": [commit]},
                    "https://api.github.com/" + second,
                ),
                second: page({**metadata, "commits": [{**commit, "sha": "two"}]}),
            }
        )
        result = compare_fork(client, fork, 3, "base", per_page=1, limit=None)
        self.assertTrue(result.commits_complete)
        self.assertEqual([item.sha for item in result.commits], ["one", "two"])
        self.assertIn(second, client.calls)

    def test_missing_comparison_commits_are_an_error(self):
        from src.domain import Fork

        fork = Fork(
            upstream="a/b",
            full_name="c/b",
            owner="c",
            created_at="2026-08-01T00:00:00Z",
            pushed_at="2026-09-01T00:00:00Z",
            retrieved_at="2026-09-16T00:00:00Z",
            default_branch="main",
            default_branch_sha="head",
        )
        client = Pages(
            {
                "repos/c/b/compare/base...head?per_page=100": page(
                    {
                        "status": "ahead",
                        "ahead_by": 1,
                        "behind_by": 0,
                        "merge_base_commit": {"sha": "base"},
                        "commits": [],
                    }
                )
            }
        )
        with self.assertRaises(ApiError):
            compare_fork(client, fork, 3, "base", per_page=100, limit=None)


if __name__ == "__main__":
    unittest.main()
