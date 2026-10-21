"""A small Git repository with known monthly outcomes for extraction tests."""

from pathlib import Path

from git import Actor, Repo


def fixture_repository(path: Path) -> tuple[Repo, dict]:
    """Create known monthly outcomes, including a side change integrated later.

    Returns the repository and, per month, the expected before and after SHAs
    of the package skills/demo.
    """
    repo = Repo.init(path, initial_branch="main")
    actor = Actor("Fixture", "fixture@example.invalid")
    package = path / "skills/demo"
    package.mkdir(parents=True)
    skill = package / "SKILL.md"
    skill.write_text("---\nname: demo\ndescription: fixture\n---\noriginal\n")
    (package / "reference.txt").write_text("remove in April\n")
    (package / "run.sh").write_text("exit 0\n")

    def commit(message, date, parents=None):
        repo.git.add("-A")
        return repo.index.commit(
            "test: " + message,
            author=actor,
            committer=actor,
            author_date=date,
            commit_date=date,
            parent_commits=parents,
        )

    initial = commit("initial package", "2026-01-01T00:00:00+0000")
    skill.write_text("ordinary\n")
    ordinary = commit("ordinary edit", "2026-02-03T00:00:00+0000")
    repo.git.checkout("-b", "feature")
    skill.write_text("feature\n")
    side = commit("side edit", "2026-02-28T00:00:00+0000")
    repo.git.checkout("main")
    (path / "README.md").write_text("unrelated main change\n")
    main = commit("main edit", "2026-03-02T00:00:00+0000")
    skill.write_text("feature\n")
    merge = commit("merge feature", "2026-03-05T00:00:00+0000", [main, side])
    (package / "reference.txt").unlink()
    commit("delete reference", "2026-04-02T00:00:00+0000")
    (package / "data.bin").write_bytes(b"\x00\xff")
    (package / "run.sh").chmod(0o755)
    april = commit("binary and mode change", "2026-04-03T00:00:00+0000")
    skill.write_text("temporary\n")
    commit("temporary edit", "2026-05-02T00:00:00+0000")
    skill.write_text("feature\n")
    cancelled = commit("cancel temporary edit", "2026-05-03T00:00:00+0000")
    return repo, {
        "2026-02": (initial.hexsha, ordinary.hexsha),
        "2026-03": (main.hexsha, merge.hexsha),
        "2026-04": (merge.hexsha, april.hexsha),
        "2026-05": (april.hexsha, cancelled.hexsha),
    }
