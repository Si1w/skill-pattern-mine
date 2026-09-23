"""Clean commit messages and deduplicate redundant branches.

Takes the in-skill diffs scoped by ``mine.s05_filter_in_skill``
(``data/mine/diff_in_skill.jsonl``) and produces the final modification corpus
(``data/mine/diff_cleaned.jsonl``) in two passes:

1. Commit cleaning. Each row's ``commits`` are reduced to skill-relevant intent
   via :func:`filter_skill_commits` (drops merges/squashes and repo-maintenance
   messages). This is done once here so downstream stages consume an
   already-clean commit set rather than re-filtering it.

2. Branch deduplication. Within one ``(upstream, fork_owner)``, a branch whose
   cleaned commit SHA set is a subset of (or equal to) a sibling branch is
   redundant — the same line of work or an earlier snapshot. We keep only the
   maximal (superset) branches. On equal sets a default branch (``main`` /
   ``master``) is kept over a feature branch; failing that, the earlier-listed
   row is kept. This holds the corpus — and any sample drawn from it — to one
   row per line of work.

File-scope and upstream-sync filtering happen upstream in
``mine.s05_filter_in_skill``, so the input is already limited to in-skill asset
files with sync branches removed. What remains is commit-message maintenance
filtering, kept here on purpose: the full commit set is needed for commit-intent
coverage (eval rq5), so it must not be dropped earlier.

Usage:
    uv run python -m mine.s06_clean
"""

import json
import logging
import re
from collections import defaultdict

from common import filter_commits, trim_message
from mine.utils import DATA_DIR

logger = logging.getLogger(__name__)
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

IN_PATH = DATA_DIR / "diff_in_skill.jsonl"
OUT_PATH = DATA_DIR / "diff_cleaned.jsonl"

MAINTENANCE_MESSAGE_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("upstream_sync", re.compile(r"\b(auto-sync|sync(ed)? with upstream|upstream sync|merge upstream)\b", re.I)),
    ("catalog_index", re.compile(r"\b(catalog|index|skill-index|skill index|badge|count[s]?)\b", re.I)),
    ("ci_workflow", re.compile(r"\b(ci|github actions?|workflow|lint|markdownlint|mdformat)\b", re.I)),
    ("plugin_manifest", re.compile(r"\b(plugin|marketplace|manifest)\b", re.I)),
    ("release_version", re.compile(r"\b(release|version|changelog|bump)\b", re.I)),
    ("repo_docs", re.compile(r"\b(readme|contributing|license|quickstart|migration)\b", re.I)),
    ("dependency_config", re.compile(r"\b(package\.json|pyproject|dependencies?|dependency|npm|pip|uv lock)\b", re.I)),
    ("local_settings", re.compile(r"\b(settings\.local|local permission|allowlist)\b", re.I)),
]


def classify_maintenance_message(message: str) -> str | None:
    """Return a maintenance category for messages outside skill scope."""
    if not message or not message.strip():
        return "empty"
    subject = message.strip().splitlines()[0]
    for name, pattern in MAINTENANCE_MESSAGE_PATTERNS:
        if pattern.search(subject):
            return name
    return None


def is_maintenance_message(message: str) -> bool:
    """True if a commit message is likely repo maintenance noise."""
    return classify_maintenance_message(message) is not None


def filter_skill_commits(commits: list[dict]) -> list[dict]:
    """Drop mechanical and repository-maintenance commits.

    First drops mechanical noise (merges, squashes, ...) via
    :func:`common.filter_commits`, then trims auto-generated footers and drops
    maintenance-message commits, keeping only those with skill-relevant intent.
    """
    out = []
    for commit in filter_commits(commits):
        message = trim_message(commit.get("message", ""))
        if is_maintenance_message(message):
            continue
        if message:
            out.append({**commit, "message": message})
    return out


def _is_default_branch(name: str) -> bool:
    """True if ``name`` is a repository default branch (main/master)."""
    return name in ("main", "master")


def dedup_branch_subsets(rows: list[dict]) -> list[dict]:
    """Drop branches whose fork-own commit set is a subset of a sibling's.

    Compares the (already cleaned) commit SHA sets per ``(upstream, fork_owner)``
    and keeps only the maximal branches. On equal sets a default branch wins;
    failing that, the earlier-listed row is kept. Rows keep their original order.
    """
    groups: dict[tuple[str, str], list[int]] = defaultdict(list)
    for i, r in enumerate(rows):
        groups[(r.get("upstream", ""), r.get("fork_owner", ""))].append(i)

    own = [frozenset(c["sha"] for c in r.get("commits", []) if c.get("sha"))
           for r in rows]

    drop: set[int] = set()
    for idxs in groups.values():
        for a in idxs:
            if a in drop:
                continue
            for b in idxs:
                if a == b or b in drop:
                    continue
                if own[a] < own[b]:
                    drop.add(a)
                    break
                if own[a] == own[b]:
                    # Equal sets: keep the default branch; otherwise keep the
                    # earlier-listed row. Drop a only when b should be kept.
                    a_def = _is_default_branch(rows[a].get("fork_branch", ""))
                    b_def = _is_default_branch(rows[b].get("fork_branch", ""))
                    if b_def and not a_def:
                        drop.add(a)
                        break
                    if a_def and not b_def:
                        continue
                    if b < a:
                        drop.add(a)
                        break
    return [r for i, r in enumerate(rows) if i not in drop]


def run() -> None:
    rows: list[dict] = []
    with open(IN_PATH) as f:
        for line in f:
            if not line.strip():
                continue
            row = json.loads(line)
            # Pass 1: clean commit messages in place.
            row["commits"] = filter_skill_commits(row.get("commits", []))
            rows.append(row)

    # Pass 2: drop branches whose cleaned commit set is a subset of a sibling.
    n_pre = len(rows)
    rows = dedup_branch_subsets(rows)
    n_dup = n_pre - len(rows)

    with open(OUT_PATH, "w") as w:
        for row in rows:
            w.write(json.dumps(row) + "\n")
    logger.info("Cleaned %d diffs (dropped %d branch-subset) -> %s",
                len(rows), n_dup, OUT_PATH)


def main():
    run()


if __name__ == "__main__":
    main()
