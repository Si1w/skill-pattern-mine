"""Behavioral checks for API pagination, caching and error handling."""

import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.github import ApiError, GitHubClient, NoCommonAncestor, Page, collect_pages


class Pages:
    """Serve prescribed API pages without network access."""

    def __init__(self, pages):
        self.pages = pages
        self.calls = []

    def get(self, endpoint):
        self.calls.append(endpoint)
        return self.pages[endpoint]


def page(body, next_url=None):
    """Construct a response with optional pagination."""
    headers = {"link": f'<{next_url}>; rel="next"'} if next_url else {}
    return Page(body=body, headers=headers, retrieved_at="2026-09-16T00:00:00Z")


class PaginationTests(unittest.TestCase):
    """Coverage must reflect links, search limits and explicit sample bounds."""

    def test_empty_page_with_next_does_not_end_enumeration(self):
        client = Pages({"a": page([], "https://api.github.com/b"), "b": page([1])})
        rows, coverage = collect_pages(client, "a")
        self.assertEqual(rows, [1])
        self.assertTrue(coverage["complete"])

    def test_limit_applies_before_rows_are_written(self):
        rows, coverage = collect_pages(Pages({"a": page([1, 2, 3])}), "a", limit=2)
        self.assertEqual(rows, [1, 2])
        self.assertFalse(coverage["complete"])
        self.assertEqual(coverage["stop_reason"], "sample_limit")

    def test_incomplete_search_cannot_claim_coverage(self):
        rows, coverage = collect_pages(
            Pages(
                {
                    "a": page(
                        {"items": [1], "total_count": 1, "incomplete_results": True}
                    )
                }
            ),
            "a",
            key="items",
        )
        self.assertEqual(rows, [1])
        self.assertFalse(coverage["complete"])

    def test_search_cap_is_recorded_even_without_next_link(self):
        _, coverage = collect_pages(
            Pages(
                {
                    "a": page(
                        {"items": [1], "total_count": 1500, "incomplete_results": False}
                    )
                }
            ),
            "a",
            key="items",
        )
        self.assertFalse(coverage["complete"])
        self.assertEqual(coverage["stop_reason"], "search_limit")

    def test_foreign_next_link_is_rejected(self):
        with self.assertRaises(ApiError):
            collect_pages(Pages({"a": page([], "https://elsewhere.test/b")}), "a")

    def test_repeated_next_link_is_rejected(self):
        with self.assertRaises(ApiError):
            collect_pages(Pages({"a": page([], "https://api.github.com/a")}), "a")


class ClientTests(unittest.TestCase):
    """Cached reads remain stable and missing or failed reads remain failures."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def client(self, **kwargs):
        return GitHubClient(self.root, api_version="2026-03-10", **kwargs)

    def response(self, status, body, headers=""):
        return subprocess.CompletedProcess(
            [],
            0 if status == 200 else 1,
            f"HTTP/2.0 {status} Status\n{headers}\n{json.dumps(body)}",
            "",
        )

    @patch("src.github.subprocess.run")
    def test_success_is_cached_and_replayed_without_cli(self, run):
        run.return_value = self.response(200, {"value": 7})
        first = self.client().get("repos/a/b")
        replay = self.client(offline=True).get("repos/a/b")
        self.assertEqual(first, replay)
        self.assertEqual(run.call_count, 1)

    def test_offline_cache_miss_is_an_error(self):
        with self.assertRaises(ApiError):
            self.client(offline=True).get("repos/missing/repo")

    @patch("src.github.time.sleep")
    @patch("src.github.subprocess.run")
    def test_transient_error_is_retried(self, run, sleep):
        run.side_effect = [
            self.response(503, {"message": "unavailable"}),
            self.response(200, []),
        ]
        self.assertEqual(self.client().get("repos/a/b").body, [])
        self.assertEqual(run.call_count, 2)

    @patch("src.github.subprocess.run")
    def test_not_found_is_preserved_as_an_error_for_offline_skip_replay(self, run):
        run.return_value = self.response(404, {"message": "Not Found"})
        with self.assertRaises(ApiError) as error:
            self.client().get("repos/a/b")
        self.assertEqual(error.exception.status, 404)
        with self.assertRaises(ApiError) as replay:
            self.client(offline=True).get("repos/a/b")
        self.assertEqual(replay.exception.status, 404)
        self.assertEqual(run.call_count, 1)
        saved = json.loads(next((self.root / "raw").glob("*.json")).read_text())
        self.assertEqual(saved["body"], {"message": "Not Found"})

    @patch("src.github.subprocess.run")
    def test_sensitive_response_fields_are_not_saved(self, run):
        run.return_value = self.response(
            200, {"temp_clone_token": "secret", "owner": {"login": "test"}}
        )
        response = self.client().get("repos/a/b")
        self.assertNotIn("temp_clone_token", response.body)
        self.assertNotIn("secret", next((self.root / "raw").glob("*.json")).read_text())

    @patch("src.github.subprocess.run")
    def test_explicit_unrelated_comparison_is_preserved_and_replayed(self, run):
        base, head = "a" * 40, "b" * 40
        endpoint = f"repos/a/b/compare/{base}...{head}?per_page=100"
        message = f"No common ancestor between {base} and {head}."
        run.return_value = self.response(404, {"message": message})
        with self.assertRaises(NoCommonAncestor) as first:
            self.client().get(endpoint)
        with self.assertRaises(NoCommonAncestor) as replay:
            self.client(offline=True).get(endpoint)
        self.assertEqual(str(first.exception), message)
        self.assertEqual(first.exception.retrieved_at, replay.exception.retrieved_at)
        self.assertEqual(run.call_count, 1)
        saved = json.loads(next((self.root / "raw").glob("*.json")).read_text())
        self.assertEqual(saved["status"], 404)
        self.assertEqual(saved["body"]["message"], message)

    @patch("src.github.subprocess.run")
    def test_wrong_pair_or_endpoint_is_not_a_study_exclusion(self, run):
        base, head = "a" * 40, "b" * 40
        run.return_value = self.response(404, {
            "message": f"No common ancestor between {base} and {head}."
        })
        for endpoint in ("repos/a/b", f"repos/a/b/compare/{base}...{'c' * 40}"):
            with self.subTest(endpoint=endpoint):
                with self.assertRaises(ApiError) as error:
                    self.client().get(endpoint)
                self.assertNotIsInstance(error.exception, NoCommonAncestor)
        self.assertEqual(len(list((self.root / "raw").glob("*.json"))), 2)

    @patch("src.github.time.sleep")
    @patch("src.github.subprocess.run")
    def test_full_collection_waits_for_quota_without_losing_the_request(self, run, sleep):
        run.side_effect = [
            self.response(429, {}, "Retry-After: 125\n"),
            self.response(200, {"value": "resumed"}),
        ]
        client = self.client(wait_for_rate_limit=True, max_attempts=1)
        self.assertEqual(client.get("repos/a/b").body, {"value": "resumed"})
        self.assertEqual([call.args[0] for call in sleep.call_args_list], [60, 60, 5])

    @patch("src.github.time.sleep")
    @patch("src.github.subprocess.run")
    def test_long_rate_wait_fails_for_later_resume(self, run, sleep):
        run.return_value = self.response(429, {}, "Retry-After: 3600\n")
        with self.assertRaises(ApiError):
            self.client().get("repos/a/b")
        sleep.assert_not_called()


if __name__ == "__main__":
    unittest.main()
