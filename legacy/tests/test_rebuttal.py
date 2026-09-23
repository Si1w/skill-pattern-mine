"""Behavioral checks for supplementary measurement semantics."""

import importlib.util
from pathlib import Path
import sys
import unittest

LEGACY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(LEGACY))
from eval.rebuttal.main import alpha_binary, owner_root, counts_for_groups


class RebuttalTests(unittest.TestCase):
    def test_alpha_uses_finite_rating_population(self):
        # Four ratings: three positives and one negative; Do=1/2, De=1/2.
        self.assertAlmostEqual(alpha_binary([{"a"}, {"a"}], [{"a"}, set()], ["a"]), 0)

    def test_constant_alpha_is_undefined(self):
        self.assertIsNone(alpha_binary([{"a"}], [{"a"}], ["a"]))

    def test_root_mapping_uses_path_boundary_and_longest_root(self):
        roots = {"skills/a", "skills/a/nested", "skills/ab"}
        self.assertEqual(owner_root("skills/a/nested/code.py", roots), "skills/a/nested")
        self.assertIsNone(owner_root("skills/abc/code.py", roots))

    def test_fork_counts_preserve_multiple_branches(self):
        records = [{"upstream": "u", "modification_id": "u::x::one", "labels": ["a"]},
                   {"upstream": "u", "modification_id": "u::x::two", "labels": []}]
        groups = counts_for_groups(records, ["a"], lambda r: set(r["labels"]))
        self.assertEqual(groups["u"], [(2, [1])])


if __name__ == "__main__":
    unittest.main()
