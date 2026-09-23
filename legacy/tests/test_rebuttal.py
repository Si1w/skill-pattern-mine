"""Behavioral checks for supplementary measurement semantics."""

import importlib.util
from pathlib import Path
import sys
import unittest

LEGACY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(LEGACY))
from eval.rebuttal.main import alpha_binary, owner_root, counts_for_groups
from eval.rebuttal.audit_materials import select_blind_records


class RebuttalTests(unittest.TestCase):
    def test_blind_sample_excludes_audit_bootstrap_and_nonfinal_records(self):
        records = {"a.json": "a", "b.json": "b", "c.json": "c", "d.json": "d", "e.json": "e"}
        selected, frame = select_blind_records(records, {"a", "b", "c", "d"},
                                               {"a.json", "b.json"}, {"b.json"}, 2, 42)
        self.assertEqual(set(selected), {"c.json", "d.json"})
        self.assertEqual(frame.excluded_union, 2)
        self.assertEqual(frame.excluded_in_both, 1)
        self.assertEqual(frame.analyzed_count, 4)
        self.assertEqual(frame.eligible_count, 2)

    def test_blind_sample_rejects_insufficient_unseen_records(self):
        with self.assertRaises(ValueError):
            select_blind_records({"a.json": "a"}, {"a"}, {"a.json"}, set(), 1, 42)

    def test_blind_frame_requires_complete_identity_mapping(self):
        with self.assertRaises(ValueError):
            select_blind_records({"a.json": "a"}, {"a", "missing"}, set(), set(), 1, 42)

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
