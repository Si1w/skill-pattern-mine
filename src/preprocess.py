"""Deterministic screening measurements from complete GitHub tree inventories."""

from collections.abc import Iterable
from pathlib import PurePosixPath

from src.domain import SkillCentricity, TreeEntry


def measure_skill_centricity(
    entries: Iterable[TreeEntry], *, complete: bool
) -> SkillCentricity:
    """Count tracked files inside the union of SKILL.md package directories.

    The caller must establish inventory completeness before measurement.
    Entries use GitHub tree paths relative to one frozen repository root.
    This function measures a ratio; it does not select an inclusion threshold.
    """
    if not complete:
        raise ValueError(
            "A complete tree inventory is required for package file ratio."
        )

    unique: dict[str, TreeEntry] = {}
    for entry in entries:
        if entry.path in unique and unique[entry.path] != entry:
            raise ValueError(f"Conflicting tree entries at {entry.path!r}.")
        unique[entry.path] = entry

    files = [entry for entry in unique.values() if entry.type == "blob"]
    roots = sorted(
        {
            str(PurePosixPath(entry.path).parent)
            for entry in files
            if entry.mode in {"100644", "100755"}
            and PurePosixPath(entry.path).name == "SKILL.md"
        }
    )
    skill_files = sum(
        any(root == "." or entry.path.startswith(f"{root}/") for root in roots)
        for entry in files
    )
    total = len(files)
    return SkillCentricity(
        tracked_files=total,
        skill_files=skill_files,
        package_paths=roots,
        ratio=skill_files / total if total else None,
    )
