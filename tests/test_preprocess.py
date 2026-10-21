"""Behavior checks for repository screening over complete GitHub trees."""

import unittest

from src.domain import TreeEntry
from src.preprocess import measure_skill_centricity


def blob(path: str, mode: str = "100644") -> TreeEntry:
    """Build a entry for a tracked file without network or dependencies on file contents."""
    return TreeEntry(path=path, type="blob", mode=mode)


class SkillCentricityTests(unittest.TestCase):
    """Verify counts that could otherwise change repository inclusion."""

    def test_markdown_counts_in_both_numerator_and_denominator(self):
        entries = [blob("README.md"), blob("a/SKILL.md"), blob("a/guide.md")]
        result = measure_skill_centricity(entries, complete=True)
        self.assertEqual((result.skill_files, result.tracked_files), (2, 3))
        self.assertAlmostEqual(result.ratio, 2 / 3)

    def test_nested_packages_and_duplicate_entries_count_files_once(self):
        entries = [
            blob("a/SKILL.md"),
            blob("a/nested/SKILL.md"),
            blob("a/nested/run.py"),
            blob("a/nested/run.py"),
            blob("LICENSE"),
        ]
        result = measure_skill_centricity(entries, complete=True)
        self.assertEqual(result.package_paths, ["a", "a/nested"])
        self.assertEqual((result.skill_files, result.tracked_files), (3, 4))

    def test_directory_prefix_does_not_match_neighboring_package(self):
        entries = [blob("skill/SKILL.md"), blob("skill/run.py"), blob("skills/run.py")]
        result = measure_skill_centricity(entries, complete=True)
        self.assertEqual(result.skill_files, 2)

    def test_root_manifest_makes_all_tracked_files_package_files(self):
        entries = [blob("SKILL.md"), blob("README.md"), blob("tools/run.py")]
        result = measure_skill_centricity(entries, complete=True)
        self.assertEqual(result.package_paths, ["."])
        self.assertEqual(result.ratio, 1.0)

    def test_directories_and_submodules_are_not_counted_as_files(self):
        entries = [
            blob("a/SKILL.md"),
            blob("a/icon.png"),
            blob("a/link", "120000"),
            TreeEntry(path="a", type="tree", mode="040000"),
            TreeEntry(path="vendor", type="commit", mode="160000"),
        ]
        result = measure_skill_centricity(entries, complete=True)
        self.assertEqual((result.skill_files, result.tracked_files), (3, 3))

    def test_symlink_manifest_is_a_file_but_does_not_establish_a_package(self):
        entries = [blob("a/SKILL.md", "120000"), blob("a/run.py")]
        result = measure_skill_centricity(entries, complete=True)
        self.assertEqual(result.package_paths, [])
        self.assertEqual(result.ratio, 0.0)
        self.assertEqual(result.tracked_files, 2)

    def test_executable_manifest_establishes_a_package(self):
        result = measure_skill_centricity([blob("a/SKILL.md", "100755")], complete=True)
        self.assertEqual(result.package_paths, ["a"])
        self.assertEqual(result.ratio, 1.0)

    def test_distinct_paths_are_counted_separately(self):
        entries = [blob("a/SKILL.md"), blob("a/copy-one.md"), blob("a/copy-two.md")]
        result = measure_skill_centricity(entries, complete=True)
        self.assertEqual(result.tracked_files, 3)

    def test_empty_complete_tree_has_undefined_ratio(self):
        result = measure_skill_centricity([], complete=True)
        self.assertEqual((result.skill_files, result.tracked_files), (0, 0))
        self.assertIsNone(result.ratio)

    def test_incomplete_inventory_cannot_produce_a_measurement(self):
        with self.assertRaisesRegex(ValueError, "complete"):
            measure_skill_centricity([blob("a/SKILL.md")], complete=False)

    def test_conflicting_duplicate_paths_are_not_silently_overwritten(self):
        entries = [blob("a/SKILL.md"), blob("a/SKILL.md", "120000")]
        with self.assertRaisesRegex(ValueError, "Conflicting"):
            measure_skill_centricity(entries, complete=True)


if __name__ == "__main__":
    unittest.main()
