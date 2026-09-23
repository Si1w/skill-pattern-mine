"""Enumerate forks of upstream GitHub repositories via the `gh` CLI.

Processes every repo in configs/mine.yaml by default (pass --repo to limit to
one) and writes all forks to a single ``data/mine/forks.jsonl``, one fork per
line tagged with its ``upstream`` repo. Resume-safe at repo granularity: a
``(upstream, full_name)`` pair already in the file is skipped on re-run.

Usage:
    uv run python -m mine.s02_mine_forks
    uv run python -m mine.s02_mine_forks --repo anthropics/skills
    uv run python -m mine.s02_mine_forks --num_samples 50
"""

import argparse
import json
import logging
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

from mine.utils import DATA_DIR, load_config

logger = logging.getLogger(__name__)
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

FORKS_PATH = DATA_DIR / "forks.jsonl"
REPO_METADATA_PATH = DATA_DIR / "repo_metadata.jsonl"
FIELDS = [
    "owner",
    "name",
    "full_name",
    "clone_url",
    "created_at",
    "pushed_at",
    "size",
    "stargazers_count",
    "default_branch",
]


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _gh_json(url: str, jq: str, max_retries: int = 5) -> dict:
    """Run ``gh api`` with retry and parse a single JSON object."""
    for attempt in range(max_retries):
        proc = subprocess.run(
            ["gh", "api", url, "-q", jq], capture_output=True, text=True
        )
        if proc.returncode == 0:
            return json.loads(proc.stdout)
        wait = min(2 ** attempt, 60)
        logger.warning(
            "gh api failed (rc=%d, attempt %d/%d): %s — sleeping %ds",
            proc.returncode, attempt + 1, max_retries,
            (proc.stderr or "").strip().splitlines()[0][:200] if proc.stderr else "",
            wait,
        )
        time.sleep(wait)
    raise RuntimeError(f"gh api failed after {max_retries} attempts: {url}")


def fetch_repo_metadata(repo: str, captured_at: str) -> dict:
    """Fetch upstream repo-level GitHub metadata for this fork snapshot."""
    row = _gh_json(
        f"repos/{repo}",
        "{repo_name:.full_name,stars:.stargazers_count,"
        "forks:.forks_count,default_branch:.default_branch}",
    )
    return {**row, "captured_at": captured_at}


def save_repo_metadata(record: dict) -> Path:
    """Upsert one upstream repo metadata record into repo_metadata.jsonl."""
    REPO_METADATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    rows: list[dict] = []
    seen = False
    if REPO_METADATA_PATH.exists():
        with open(REPO_METADATA_PATH) as f:
            for line in f:
                if not line.strip():
                    continue
                row = json.loads(line)
                if row.get("repo_name") == record["repo_name"]:
                    rows.append({**row, **record})
                    seen = True
                else:
                    rows.append(row)
    if not seen:
        rows.append(record)

    tmp_path = REPO_METADATA_PATH.with_suffix(".jsonl.tmp")
    with open(tmp_path, "w") as f:
        for row in rows:
            f.write(json.dumps(row) + "\n")
    tmp_path.replace(REPO_METADATA_PATH)
    logger.info("Saved upstream repo metadata to %s", REPO_METADATA_PATH)
    return REPO_METADATA_PATH


def _gh_page(url: str, jq: str, max_retries: int = 5) -> tuple[list[dict], bool]:
    """Run ``gh api -i`` with backoff; return (batch, has_next).

    The ``has_next`` flag comes from the ``Link`` response header
    (``rel="next"``), so callers can distinguish "real end of pagination"
    from "transient empty page" — past runs that broke on empty batches
    silently truncated to ~85 pages on a 147-page repo.
    """
    for attempt in range(max_retries):
        proc = subprocess.run(
            ["gh", "api", "-i", url, "-q", jq], capture_output=True, text=True
        )
        if proc.returncode == 0:
            head, _, body = proc.stdout.partition("\n\n")
            link_lines = [l for l in head.splitlines() if l.lower().startswith("link:")]
            link = link_lines[0] if link_lines else ""
            has_next = 'rel="next"' in link
            batch = [json.loads(line) for line in body.splitlines() if line.strip()]
            return batch, has_next
        wait = min(2 ** attempt, 60)
        logger.warning(
            "gh api failed (rc=%d, attempt %d/%d): %s — sleeping %ds",
            proc.returncode, attempt + 1, max_retries,
            (proc.stderr or "").strip().splitlines()[0][:200] if proc.stderr else "",
            wait,
        )
        time.sleep(wait)
    raise RuntimeError(f"gh api failed after {max_retries} attempts: {url}")


def load_done() -> set[tuple[str, str]]:
    """Return ``{(upstream, full_name), ...}`` already written to forks.jsonl."""
    if not FORKS_PATH.exists():
        return set()
    done: set[tuple[str, str]] = set()
    with open(FORKS_PATH) as f:
        for line in f:
            if not line.strip():
                continue
            row = json.loads(line)
            done.add((row.get("upstream", ""), row["full_name"]))
    return done


def fetch_forks(repo: str, sort: str, max_items: int | None,
                done: set[tuple[str, str]]) -> list[dict]:
    """Page through GitHub's fork list, skipping forks already done for this repo.

    Each new fork is tagged with its ``upstream`` repo and appended to the
    shared ``forks.jsonl`` immediately, so an interrupted run resumes by
    skipping the ``(upstream, full_name)`` pairs already on disk.
    """
    jq = (
        ".[] | {"
        + ", ".join(f"{f}: .owner.login" if f == "owner" else f"{f}: .{f}" for f in FIELDS)
        + "}"
    )
    FORKS_PATH.parent.mkdir(parents=True, exist_ok=True)
    items: list[dict] = []
    page = 1
    with open(FORKS_PATH, "a") as out_f:
        while True:
            url = f"repos/{repo}/forks?per_page=100&sort={sort}&page={page}"
            logger.info("[%s] fetching page %d", repo, page)
            batch, has_next = _gh_page(url, jq)
            for item in batch:
                key = (repo, item["full_name"])
                if key in done:
                    continue
                done.add(key)
                row = {"upstream": repo, **item}
                items.append(row)
                out_f.write(json.dumps(row) + "\n")
            out_f.flush()
            if max_items and len(items) >= max_items:
                return items[:max_items]
            if not has_next:
                break
            page += 1
    return items


def mine_one(repo: str, sort: str, num_samples: int | None,
             done: set[tuple[str, str]]) -> int:
    """Fetch one repo's forks into the shared forks.jsonl; return count added."""
    captured_at = _utcnow_iso()
    repo_metadata = fetch_repo_metadata(repo, captured_at)
    forks = fetch_forks(repo, sort, num_samples, done)
    save_repo_metadata(repo_metadata)
    logger.info("[%s] added %d new forks", repo, len(forks))
    return len(forks)


def mine_all(repos: list[str], sort: str, num_samples: int | None) -> None:
    """Fetch forks for every repo into the shared forks.jsonl (resume-safe)."""
    done = load_done()
    logger.info("Resuming with %d (upstream, fork) pairs already on disk", len(done))
    for repo in repos:
        mine_one(repo, sort, num_samples, done)


def main():
    cfg = load_config()
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", default=None,
                        help="owner/repo; omit to process all repos in mine.yaml")
    parser.add_argument("--sort", default="stargazers",
                        choices=["stargazers", "newest", "oldest", "watchers"])
    parser.add_argument("--num_samples", type=int, default=None)
    args = parser.parse_args()
    repos = [args.repo] if args.repo else [e["repo"] for e in cfg.get("repos", [])]
    mine_all(repos, args.sort, args.num_samples)


if __name__ == "__main__":
    main()
