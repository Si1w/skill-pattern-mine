"""Filter diffs down to in-skill modifications only.

The unit of analysis is a change *inside an existing skill directory*, not
changes to the repository's skill set as a whole. For every file in each
diff, keep it only if it lives inside a skill directory that already exists
upstream (per ``skills_index.jsonl``) and that the diff does not add or
remove. This drops:

  - add-skill / remove-skill files: a skill whose ``SKILL.md`` is added or
    removed in this diff (the whole skill is created or deleted, not edited).
  - non-skill files: anything not under an existing skill directory
    (repo-root README, .github/, top-level config, ...).
  - non-skill-asset files: binaries (png/pdf/zip) and repo-maintenance files,
    via ``filter_skill_files``.

Whole rows that are merely an upstream sync (``is_likely_upstream_sync``) are
dropped too. Commit-message cleaning and branch-level deduplication happen next,
in ``mine.s06_clean``; this step only scopes diffs to in-skill files.

A skill directory is the parent of a ``SKILL.md``. File ownership is decided
by longest-prefix match so a file in a nested subdir maps to its skill.

Reads ``data/mine/diffs.jsonl`` + ``data/mine/skills_index.jsonl`` and writes
the surviving rows (those with at least one in-skill file) to
``data/mine/diff_in_skill.jsonl``. Commit cleaning and branch dedup follow in
``mine.s06_clean``, which produces the final ``diff_cleaned.jsonl`` corpus.

Usage:
    uv run python -m mine.s05_filter_in_skill
"""

import json
import logging
import re
from collections import defaultdict
from pathlib import Path, PurePosixPath

from mine.utils import DATA_DIR

logger = logging.getLogger(__name__)
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

DIFFS_PATH = DATA_DIR / "diffs.jsonl"
INDEX_PATH = DATA_DIR / "skills_index.jsonl"
OUT_PATH = DATA_DIR / "diff_in_skill.jsonl"

# --- Skill-file scope (drop binaries, repo-maintenance, non-skill files) ---

SKILL_DEFINITION_NAMES = {"skill.md"}
SKILL_ASSET_DIRS = {
    "assets", "artifacts", "config", "configs", "examples",
    "references", "schemas", "scripts", "templates",
}
SKILL_ASSET_SUFFIXES = {
    ".css", ".env.example", ".go", ".html", ".js", ".json", ".jsx", ".md",
    ".mdx", ".py", ".rb", ".rs", ".sh", ".toml", ".ts", ".tsx", ".txt",
    ".yaml", ".yml",
}
EXCLUDED_BINARY_SUFFIXES = {
    ".gif", ".jpeg", ".jpg", ".pdf", ".png", ".tgz", ".webp", ".zip",
}
REPO_MAINTENANCE_ROOTS = {
    ".claude", ".claude-plugin", ".github", ".opencode", ".vscode",
    "docs", "eval", "scripts", "src", "tests",
}
REPO_MAINTENANCE_FILES = {
    ".gitignore", "changelog.md", "contributing.md", "license", "license.md",
    "marketplace.json", "package-lock.json", "package.json", "plugin.json",
    "pyproject.toml", "readme.md", "security.md", "uv.lock",
}


def normalize_path(filename: str) -> PurePosixPath:
    """Return a normalized POSIX path for GitHub API filenames."""
    return PurePosixPath(filename.strip("/"))


def is_skill_definition_path(filename: str) -> bool:
    """True for primary skill instruction files."""
    return normalize_path(filename).name.lower() in SKILL_DEFINITION_NAMES


def load_upstream_skill_roots(index_path: Path = INDEX_PATH) -> dict[str, set[str]]:
    """Load known upstream skill root directories from ``skills_index.jsonl``."""
    if not index_path.exists():
        return {}
    roots: dict[str, set[str]] = {}
    for line in index_path.read_text().splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        roots.setdefault(row["repo"], set()).add(str(normalize_path(row["path"]).parent))
    return roots


def infer_skill_roots(files: list[dict]) -> set[str]:
    """Infer skill roots from definition files present in one diff row."""
    roots: set[str] = set()
    for file in files:
        if is_skill_definition_path(file.get("filename", "")):
            roots.add(str(normalize_path(file["filename"]).parent))
    return roots


def is_under_root(path: PurePosixPath, root: str) -> bool:
    """Return true if ``path`` equals or is contained by ``root``."""
    root_path = normalize_path(root)
    return path == root_path or path.is_relative_to(root_path)


def is_repo_maintenance_path(filename: str) -> bool:
    """True for repository-level files that are outside the skill scope."""
    path = normalize_path(filename)
    if not path.parts:
        return True
    first = path.parts[0].lower()
    name = path.name.lower()
    if first in REPO_MAINTENANCE_ROOTS:
        return True
    return len(path.parts) == 1 and name in REPO_MAINTENANCE_FILES


def is_skill_asset_path(filename: str, roots: set[str]) -> bool:
    """True for files that belong to a skill package or skill directory."""
    path = normalize_path(filename)
    if is_repo_maintenance_path(filename):
        return False
    if path.name.lower() in SKILL_DEFINITION_NAMES:
        return True
    if path.suffix.lower() in EXCLUDED_BINARY_SUFFIXES:
        return False

    under_known_root = any(is_under_root(path, root) for root in roots)
    under_skills_prefix = len(path.parts) >= 3 and path.parts[0].lower() == "skills"
    if not under_known_root and not under_skills_prefix:
        return False

    if {part.lower() for part in path.parts} & SKILL_ASSET_DIRS:
        return True
    return any(str(path).lower().endswith(suffix) for suffix in SKILL_ASSET_SUFFIXES)


def filter_skill_files(
    files: list[dict],
    repo: str | None = None,
    upstream_roots: dict[str, set[str]] | None = None,
) -> list[dict]:
    """Keep only files that are relevant to skill modifications."""
    roots = infer_skill_roots(files)
    if repo and upstream_roots:
        roots |= upstream_roots.get(repo, set())
    return [f for f in files if is_skill_asset_path(f.get("filename", ""), roots)]


def is_likely_upstream_sync(row: dict) -> bool:
    """Detect compare rows dominated by upstream sync branch naming."""
    branch = row.get("fork_branch", "")
    if re.search(r"\b(auto-sync|sync/upstream|upstream-\d|merge-upstream)\b", branch, re.I):
        return True
    return any(
        re.search(r"\b(auto-sync|sync(ed)? with upstream|upstream sync|merge upstream)\b",
                  c.get("message", ""), re.I)
        for c in row.get("commits", [])
    )


# --- In-skill membership (drop add/remove-skill and non-skill files) ---


def load_skill_dirs() -> dict[str, set[str]]:
    """Map each upstream repo to its set of skill directories (SKILL.md parents)."""
    dirs: dict[str, set[str]] = defaultdict(set)
    with open(INDEX_PATH) as f:
        for line in f:
            if not line.strip():
                continue
            r = json.loads(line)
            dirs[r["repo"]].add(str(PurePosixPath(r["path"]).parent))
    return dirs


def owning_skill(path: str, dirs: set[str]) -> str | None:
    """Return the existing skill directory containing ``path`` (longest match)."""
    best = None
    for d in dirs:
        if path == d or path.startswith(d + "/"):
            if best is None or len(d) > len(best):
                best = d
    return best


def in_added_removed_skill(path: str, added_removed: set[str]) -> bool:
    """True if ``path`` is inside a skill dir whose SKILL.md is added/removed.

    Uses prefix match so a newly created nested sub-skill (e.g.
    ``skills/foo/bar/SKILL.md`` added under an existing ``skills/foo``) and
    everything under it is treated as add-skill, not as an edit to the parent.
    """
    return any(path == d or path.startswith(d + "/") for d in added_removed)


def filter_files(files: list[dict], dirs: set[str]) -> list[dict]:
    """Keep only files inside an existing skill dir not added/removed here."""
    added_removed = {
        str(PurePosixPath(fl["filename"]).parent)
        for fl in files
        if PurePosixPath(fl["filename"]).name == "SKILL.md"
        and fl["status"] in ("added", "removed")
    }
    kept = []
    for fl in files:
        skill = owning_skill(fl["filename"], dirs)
        if skill is not None and not in_added_removed_skill(fl["filename"], added_removed):
            kept.append(fl)
    return kept


def run() -> None:
    skill_dirs = load_skill_dirs()
    upstream_roots = load_upstream_skill_roots()
    n_in = n_sync = n_out = 0
    with open(DIFFS_PATH) as f, open(OUT_PATH, "w") as w:
        for line in f:
            if not line.strip():
                continue
            n_in += 1
            row = json.loads(line)
            if is_likely_upstream_sync(row):
                n_sync += 1
                continue
            upstream = row.get("upstream", "")
            # In-skill directory membership, then skill-file scope (drop
            # binaries / repo-maintenance files).
            kept = filter_files(row.get("files", []), skill_dirs.get(upstream, set()))
            kept = filter_skill_files(kept, upstream, upstream_roots)
            if not kept:
                continue
            row["files"] = kept
            w.write(json.dumps(row) + "\n")
            n_out += 1
    logger.info("Kept %d/%d diffs (dropped %d upstream-sync) -> %s",
                n_out, n_in, n_sync, OUT_PATH)


def main():
    run()


if __name__ == "__main__":
    main()
