"""Clone upstream repos and build a skill-file index.

For each repo in configs/mine.yaml, do (or update) a bare git clone under
``data/mine/repos/{repo-slug}.git/``, then list every ``SKILL.md`` in
``HEAD`` under the configured prefix and extract its frontmatter +
heading structure into ``data/mine/skills_index.jsonl``.

The bare clone is what lets downstream analyses recover any historical
``base`` file (e.g. by ``merge_base_sha``) without re-hitting the API.
The index file is rewritten from scratch each run — cheap, since it
only reads local objects.

Usage:
    uv run python -m mine.s04_fetch_upstream
"""

import json
import logging
import re
import subprocess
from pathlib import Path

import yaml

from mine.utils import DATA_DIR, load_config

logger = logging.getLogger(__name__)
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

REPOS_DIR = DATA_DIR / "repos"
INDEX_PATH = DATA_DIR / "skills_index.jsonl"
SKILL_FILENAME = "SKILL.md"

FRONTMATTER_RE = re.compile(r"\A---\n(.*?)\n---\s*\n", re.DOTALL)
HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")


def slug(repo: str) -> str:
    return repo.replace("/", "-")


def bare_path(repo: str) -> Path:
    return REPOS_DIR / f"{slug(repo)}.git"


def git(*args: str, cwd: Path | None = None) -> str:
    proc = subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True, text=True, check=True
    )
    return proc.stdout


def clone_or_update(repo: str) -> Path:
    """Bare-clone ``repo`` if missing, otherwise ``git fetch`` in place."""
    target = bare_path(repo)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        logger.info("[%s] fetching updates", repo)
        git("fetch", "--all", "--prune", "--quiet", cwd=target)
    else:
        logger.info("[%s] cloning bare to %s", repo, target)
        url = f"https://github.com/{repo}.git"
        git("clone", "--bare", "--quiet", url, str(target))
    return target


def head_sha(repo_path: Path) -> str:
    return git("rev-parse", "HEAD", cwd=repo_path).strip()


def list_skill_paths(repo_path: Path, prefix: str) -> list[str]:
    """Return paths of every SKILL.md under ``prefix`` in HEAD."""
    out = git("ls-tree", "-r", "--name-only", "HEAD", cwd=repo_path)
    paths = []
    for line in out.splitlines():
        if not (line == SKILL_FILENAME or line.endswith(f"/{SKILL_FILENAME}")):
            continue
        if prefix and not line.startswith(prefix):
            continue
        paths.append(line)
    return paths


def show_file(repo_path: Path, path: str, sha: str) -> str:
    return git("show", f"{sha}:{path}", cwd=repo_path)


def parse_frontmatter(text: str) -> dict:
    """Extract YAML frontmatter as a dict, or {} if absent / malformed."""
    m = FRONTMATTER_RE.match(text)
    if not m:
        return {}
    try:
        data = yaml.safe_load(m.group(1)) or {}
        return data if isinstance(data, dict) else {}
    except yaml.YAMLError as e:
        logger.warning("frontmatter parse failed: %s", e)
        return {}


def parse_headings(text: str) -> list[dict]:
    """Return ``[{level, text, line}, ...]`` for every markdown ATX heading.

    Skips lines inside fenced code blocks so a ``# comment`` in a python
    snippet does not get mistaken for a section header.
    """
    out: list[dict] = []
    in_fence = False
    for i, line in enumerate(text.splitlines(), 1):
        stripped = line.lstrip()
        if stripped.startswith("```") or stripped.startswith("~~~"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        m = HEADING_RE.match(line)
        if m:
            out.append({"level": len(m.group(1)),
                        "text": m.group(2),
                        "line": i})
    return out


def index_one(repo: str, prefix: str) -> list[dict]:
    repo_path = clone_or_update(repo)
    sha = head_sha(repo_path)
    paths = list_skill_paths(repo_path, prefix)
    logger.info("[%s] HEAD=%s, %d SKILL.md under prefix=%r",
                repo, sha[:8], len(paths), prefix)
    rows: list[dict] = []
    for p in paths:
        text = show_file(repo_path, p, sha)
        rows.append({
            "repo": repo,
            "path": p,
            "head_sha": sha,
            "frontmatter": parse_frontmatter(text),
            "n_lines": len(text.splitlines()),
            "headings": parse_headings(text),
        })
    return rows


def fetch_upstream() -> Path:
    """Bare-clone every repo in mine.yaml and rebuild the SKILL.md index."""
    cfg = load_config()
    default_prefix = cfg.get("defaults", {}).get("prefix", "skills/")
    entries = cfg.get("repos", [])
    REPOS_DIR.mkdir(parents=True, exist_ok=True)
    rows: list[dict] = []
    for e in entries:
        prefix = e.get("prefix", default_prefix)
        rows.extend(index_one(e["repo"], prefix))
    with open(INDEX_PATH, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    logger.info("wrote %d skill records to %s", len(rows), INDEX_PATH)
    return INDEX_PATH


def main():
    fetch_upstream()


if __name__ == "__main__":
    main()
