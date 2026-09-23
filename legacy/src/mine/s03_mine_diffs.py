"""Fetch diffs between each fork and its upstream via the GitHub Compare API.

Branch-aware: every fork branch is compared independently so feature /
issue / wip branches are not lost. Each row in ``diffs.jsonl`` is keyed
by ``(fork_owner, fork_branch)``; resume is at the same granularity.

Keeps every file change (any status, any extension) under an optional
per-repo ``prefix`` filter, and attaches every commit message from the
compare window as intent signal for labeling. For renames the original
path is preserved as ``previous_filename`` alongside the new ``filename``.

Two-phase pipeline per run:
  1. ``fetch_branches`` lists every branch of every fork (1 call/fork).
  2. ``fetch_compare`` runs one compare per ``(fork, branch)`` pair that
     is not yet in ``load_done``. Branches inherited verbatim from
     upstream are still compared — the ``ahead_by`` and patch content
     reveal whether they carry fork-specific commits.

Two rate-saving measures:
  * Pre-filter forks by ``pushed_at > created_at + 5m``. Forks that never
    got a post-creation push keep ``pushed_at == created_at`` to the
    second, so this drops pure star/backup forks (zero API cost).
  * Rate-limit aware waiting. Every response carries
    ``X-RateLimit-Remaining`` and ``X-RateLimit-Reset``; when the budget
    drops below a threshold, sleep until the reset epoch instead of
    pushing on and hitting 429.

Multi-repo design: ``run_repos`` flattens the fork queues of all target
repos into a single aiohttp session, so the rate-limit budget (which is
account-wide, not session-wide) is honored with a single unified view.

Reads forks from ``data/mine/forks.jsonl`` (filtered by ``upstream``) and
writes every compare record to a single ``data/mine/diffs.jsonl``, one row
per ``(upstream, fork_owner, fork_branch)``. Processes every repo in
configs/mine.yaml by default; pass --repo to limit to one.

Usage:
    uv run python -m mine.s03_mine_diffs
    uv run python -m mine.s03_mine_diffs --repo anthropics/skills
    uv run python -m mine.s03_mine_diffs --num_samples 50 --concurrency 4
"""

import argparse
import asyncio
import json
import logging
import os
import subprocess
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone

import aiohttp
from tqdm import tqdm

from mine.utils import DATA_DIR, load_config

logger = logging.getLogger(__name__)
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

FORKS_PATH = DATA_DIR / "forks.jsonl"
DIFFS_PATH = DATA_DIR / "diffs.jsonl"
GITHUB_API = "https://api.github.com"
RATE_LIMIT_THRESHOLD = 50
PUSH_GRACE = timedelta(minutes=5)


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


async def fetch_default_branch(session: aiohttp.ClientSession, repo: str) -> str:
    """Ask GitHub for the repo's default branch (e.g. main, master, trunk)."""
    async with session.get(f"{GITHUB_API}/repos/{repo}") as resp:
        if resp.status == 200:
            data = await resp.json()
            return data.get("default_branch", "main")
        logger.warning("default_branch lookup failed for %s (HTTP %d), falling back to 'main'",
                       repo, resp.status)
        return "main"


async def fetch_branches(
    session: aiohttp.ClientSession,
    sem: asyncio.Semaphore,
    fork_owner: str,
    fork_name: str,
    max_retries: int = 5,
) -> list[str]:
    """List every branch of a fork; empty list on persistent failure or 404."""
    out: list[str] = []
    page = 1
    while True:
        url = (f"{GITHUB_API}/repos/{fork_owner}/{fork_name}/branches"
               f"?per_page=100&page={page}")
        page_data: list | None = None
        for attempt in range(max_retries):
            async with sem:
                try:
                    async with session.get(url) as resp:
                        if resp.status == 200:
                            await honor_rate_limit(resp)
                            page_data = await resp.json()
                            break
                        if resp.status == 404:
                            await honor_rate_limit(resp)
                            return out
                        if resp.status in (403, 429):
                            reset = resp.headers.get("X-RateLimit-Reset")
                            if reset:
                                wait = max(int(reset) - int(time.time()), 0) + 5
                            else:
                                wait = min(int(resp.headers.get("Retry-After", 2 ** attempt)), 60)
                            logger.warning(
                                "branches HTTP %d for %s/%s — sleeping %ds (attempt %d/%d)",
                                resp.status, fork_owner, fork_name, wait, attempt + 1, max_retries,
                            )
                            await asyncio.sleep(wait)
                        else:
                            await asyncio.sleep(min(2 ** attempt, 8))
                except aiohttp.ClientError as e:
                    logger.warning("branches client error %s/%s: %s",
                                   fork_owner, fork_name, e)
                    await asyncio.sleep(min(2 ** attempt, 8))
        if page_data is None:
            logger.error("branches: giving up on %s/%s page %d",
                         fork_owner, fork_name, page)
            return out
        out.extend(b["name"] for b in page_data)
        if len(page_data) < 100:
            return out
        page += 1


def get_token() -> str:
    tok = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if tok:
        return tok
    return subprocess.run(
        ["gh", "auth", "token"], capture_output=True, text=True, check=True
    ).stdout.strip()


def likely_modified(fork: dict) -> bool:
    """True iff the fork has evidence of at least one post-creation push.

    Uses a 5-minute grace window to absorb GitHub's timestamp jitter;
    any author who actually pushed will exceed this by construction.
    """
    try:
        pushed = datetime.fromisoformat(fork["pushed_at"].replace("Z", "+00:00"))
        created = datetime.fromisoformat(fork["created_at"].replace("Z", "+00:00"))
    except (KeyError, ValueError):
        return True
    return pushed > created + PUSH_GRACE


async def honor_rate_limit(resp: aiohttp.ClientResponse) -> None:
    """Sleep until ``X-RateLimit-Reset`` if remaining budget is low.

    Polls in 60s slices using wall-clock ``time.time()`` rather than one
    long ``asyncio.sleep`` so a system suspend (laptop sleep) cannot
    desynchronize the timer or extend the wait indefinitely.
    """
    remaining = resp.headers.get("X-RateLimit-Remaining")
    reset = resp.headers.get("X-RateLimit-Reset")
    if remaining is None or reset is None:
        return
    if int(remaining) >= RATE_LIMIT_THRESHOLD:
        return
    deadline = int(reset) + 5
    total_wait = max(deadline - int(time.time()), 0)
    logger.info("Rate budget low (remaining=%s), waiting %ds to reset",
                remaining, total_wait)
    while True:
        now = int(time.time())
        if now >= deadline:
            return
        await asyncio.sleep(min(60, deadline - now))


async def fetch_compare(
    session: aiohttp.ClientSession,
    upstream: str,
    base: str,
    fork_owner: str,
    fork_branch: str,
    sem: asyncio.Semaphore,
    prefix: str,
    max_retries: int = 5,
) -> dict | None:
    """GET /repos/{upstream}/compare/{base}...{fork_owner}:{fork_branch}.

    Returns a record with a ``status`` field — ``"ok"`` if the fork has
    diff content under ``prefix``; ``"no_diff"`` if compare succeeded but
    no files matched the prefix filter; ``"not_found"`` if the fork or
    branch is gone (404). Tombstone rows (``no_diff`` / ``not_found``)
    are persisted so resume runs do not re-query them.

    Returns ``None`` only on transient errors after all retries are
    exhausted, so the next run can re-attempt.
    """
    url = f"{GITHUB_API}/repos/{upstream}/compare/{base}...{fork_owner}:{fork_branch}"
    meta = {
        "_repo": upstream,
        "fork_owner": fork_owner,
        "fork_branch": fork_branch,
        "base": base,
        "prefix": prefix,
    }
    for attempt in range(max_retries):
        async with sem:
            try:
                async with session.get(url) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        await honor_rate_limit(resp)
                        files = [
                            {
                                "filename": f["filename"],
                                "previous_filename": f.get("previous_filename"),
                                "status": f["status"],
                                "additions": f["additions"],
                                "deletions": f["deletions"],
                                "patch": f.get("patch", ""),
                            }
                            for f in data.get("files", [])
                            if not prefix or f["filename"].startswith(prefix)
                        ]
                        commits = data.get("commits", [])
                        return {
                            **meta,
                            "status": "ok" if files else "no_diff",
                            "fetched_at": _utcnow_iso(),
                            "ahead_by": data.get("ahead_by", 0),
                            "behind_by": data.get("behind_by", 0),
                            "merge_base_sha": (data.get("merge_base_commit") or {}).get("sha"),
                            "head_sha": commits[-1]["sha"] if commits else None,
                            "commits": [
                                {"sha": c["sha"], "message": c["commit"]["message"]}
                                for c in commits
                            ],
                            "files": files,
                        }
                    if resp.status == 404:
                        await honor_rate_limit(resp)
                        return {
                            **meta,
                            "status": "not_found",
                            "fetched_at": _utcnow_iso(),
                        }
                    if resp.status in (403, 429):
                        reset = resp.headers.get("X-RateLimit-Reset")
                        if reset:
                            wait = max(int(reset) - int(time.time()), 0) + 5
                        else:
                            wait = min(int(resp.headers.get("Retry-After", 2 ** attempt)), 60)
                        logger.warning(
                            "HTTP %d for %s — sleeping %ds (attempt %d/%d)",
                            resp.status, fork_owner, wait, attempt + 1, max_retries,
                        )
                        await asyncio.sleep(wait)
                    else:
                        logger.warning(
                            "HTTP %d for %s (attempt %d/%d)",
                            resp.status, fork_owner, attempt + 1, max_retries,
                        )
                        await asyncio.sleep(min(2 ** attempt, 8))
            except aiohttp.ClientError as e:
                logger.warning("Client error for %s: %s", fork_owner, e)
                await asyncio.sleep(min(2 ** attempt, 8))
    logger.error("Giving up on %s after %d retries", fork_owner, max_retries)
    return None


def load_done() -> set[tuple[str, str, str]]:
    """Return ``{(upstream, fork_owner, fork_branch), ...}`` already in diffs.jsonl."""
    if not DIFFS_PATH.exists():
        return set()
    out: set[tuple[str, str, str]] = set()
    with open(DIFFS_PATH) as f:
        for line in f:
            if not line.strip():
                continue
            row = json.loads(line)
            out.add((row.get("upstream", ""), row["fork_owner"],
                     row.get("fork_branch", "")))
    return out


def load_forks(repo: str, num_samples: int | None) -> list[dict]:
    """Load forks of one upstream from the shared forks.jsonl, pre-filtered.

    Keeps only likely-modified forks (post-creation push) and caps at
    ``num_samples``. Returns an empty list if forks.jsonl is missing.
    """
    if not FORKS_PATH.exists():
        logger.error("missing %s — run s02_mine_forks first", FORKS_PATH)
        return []
    forks = []
    with open(FORKS_PATH) as f:
        for line in f:
            if not line.strip():
                continue
            fk = json.loads(line)
            if fk.get("upstream") == repo:
                forks.append(fk)
    n_total = len(forks)
    forks = [fk for fk in forks if likely_modified(fk)]
    if num_samples:
        forks = forks[:num_samples]
    logger.info("[%s] %d forks -> %d likely-modified", repo, n_total, len(forks))
    return forks


async def _branches_for(
    session: aiohttp.ClientSession,
    sem: asyncio.Semaphore,
    entry: dict,
    fk: dict,
) -> tuple[dict, dict, list[str]]:
    branches = await fetch_branches(session, sem, fk["owner"], fk["name"])
    return entry, fk, branches


async def run_repos(
    entries: list[dict],
    base_override: str | None,
    num_samples: int | None,
    concurrency: int,
) -> None:
    """Process multiple (repo, prefix) entries under a single session.

    Two-phase: first list every fork's branches, then issue one compare
    per ``(upstream, fork_owner, fork_branch)`` triple not already done.
    All records are appended to the shared ``data/mine/diffs.jsonl``.

    If ``base_override`` is ``None`` the base branch for each upstream repo
    is auto-detected from GitHub's ``default_branch`` field (a fixed
    ``"main"`` fails for repos like ``ComposioHQ/awesome-claude-skills``
    whose default is ``master``). Pass a non-empty string to force it.
    """
    plans = [(e, load_forks(e["repo"], num_samples)) for e in entries]
    if all(not forks for _, forks in plans):
        logger.info("Nothing to do.")
        return

    done = load_done()
    logger.info("%d (upstream, owner, branch) triples already done", len(done))

    headers = {"Authorization": f"token {get_token()}",
               "Accept": "application/vnd.github.v3+json"}
    sem = asyncio.Semaphore(concurrency)
    DIFFS_PATH.parent.mkdir(parents=True, exist_ok=True)

    async with aiohttp.ClientSession(headers=headers) as session:
        for entry, _ in plans:
            if base_override:
                entry["base"] = base_override
            else:
                entry["base"] = await fetch_default_branch(session, entry["repo"])
            logger.info("[%s] base branch: %s", entry["repo"], entry["base"])

        # Phase 1: enumerate every fork's branches
        list_tasks = []
        for entry, forks in plans:
            for fk in forks:
                list_tasks.append(asyncio.create_task(
                    _branches_for(session, sem, entry, fk)
                ))
        fork_branches: list[tuple[dict, dict, list[str]]] = []
        for coro in tqdm(asyncio.as_completed(list_tasks),
                         total=len(list_tasks), desc="branches"):
            fork_branches.append(await coro)

        # Phase 2: compare each (upstream, fork, branch) not already done
        compare_tasks = []
        for entry, fk, branches in fork_branches:
            if not branches:
                branches = [fk.get("default_branch", entry["base"])]
            for branch in branches:
                if (entry["repo"], fk["owner"], branch) in done:
                    continue
                compare_tasks.append(asyncio.create_task(fetch_compare(
                    session, entry["repo"], entry["base"],
                    fk["owner"], branch, sem, entry["prefix"],
                )))

        if not compare_tasks:
            logger.info("All (upstream, fork, branch) triples already processed.")
            return

        with open(DIFFS_PATH, "a") as w:
            for coro in tqdm(asyncio.as_completed(compare_tasks),
                             total=len(compare_tasks), desc="compare"):
                rec = await coro
                if rec is None:
                    continue
                rec["upstream"] = rec.pop("_repo")
                w.write(json.dumps(rec) + "\n")
                w.flush()

    drop_shared_pass()


def shared_commit_shas(fork_commits: list[tuple[str, list[dict]]],
                       min_owners: int = 2) -> set[str]:
    """Return commit SHAs shared across forks of one upstream repository.

    A fork-authored commit has a unique SHA owned by a single fork. A SHA seen
    under ``min_owners`` or more distinct fork owners is shared upstream history
    GitHub's compare kept when the upstream rewrote its branch (rebase, squash,
    force-push), so the fork did not author it. ``fork_commits`` is a list of
    ``(fork_owner, commits)`` for one repository.
    """
    owners_by_sha: dict[str, set[str]] = defaultdict(set)
    for owner, commits in fork_commits:
        for commit in commits:
            sha = commit.get("sha")
            if sha:
                owners_by_sha[sha].add(owner)
    return {sha for sha, owners in owners_by_sha.items() if len(owners) >= min_owners}


def drop_shared_commits(commits: list[dict], shared: set[str]) -> list[dict]:
    """Drop commits whose SHA is shared upstream history, keeping fork-own ones."""
    return [c for c in commits if c.get("sha") not in shared]


def drop_shared_pass() -> None:
    """Drop shared upstream history and stale mirrors from diffs.jsonl.

    A commit SHA seen under two or more distinct fork owners of the same
    upstream is shared history GitHub's compare kept after an upstream branch
    rewrite, not fork-authored work. We recompute the shared set per upstream,
    drop those commits from every row, then keep only rows that still describe
    a real fork change: ``status == "ok"`` with at least one fork-own commit
    left. Rows that drop to zero commits are stale upstream mirrors; no_diff /
    not_found tombstones never carried fork-own work. The file is rewritten
    atomically.
    """
    if not DIFFS_PATH.exists():
        return
    rows = [json.loads(line) for line in open(DIFFS_PATH) if line.strip()]
    n_in = len(rows)

    by_upstream: dict[str, list[tuple[str, list[dict]]]] = {}
    for r in rows:
        by_upstream.setdefault(r.get("upstream", ""), []).append(
            (r["fork_owner"], r.get("commits", []))
        )
    shared = {up: shared_commit_shas(fc) for up, fc in by_upstream.items()}

    n_dropped = 0
    kept = []
    for r in rows:
        before = len(r.get("commits", []))
        r["commits"] = drop_shared_commits(r.get("commits", []),
                                           shared.get(r.get("upstream", ""), set()))
        n_dropped += before - len(r["commits"])
        if r.get("status") == "ok" and r["commits"]:
            kept.append(r)

    tmp = DIFFS_PATH.with_suffix(".jsonl.tmp")
    with open(tmp, "w") as f:
        for r in kept:
            f.write(json.dumps(r) + "\n")
    tmp.replace(DIFFS_PATH)
    logger.info("Dropped %d shared-history commits; kept %d/%d rows "
                "(removed stale mirrors + tombstones) in %s",
                n_dropped, len(kept), n_in, DIFFS_PATH)


def main():
    cfg = load_config()
    default_prefix = cfg.get("defaults", {}).get("prefix", "")
    repo_prefix = {e["repo"]: e.get("prefix", default_prefix)
                   for e in cfg.get("repos", [])}

    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", default=None,
                        help="owner/repo; omit to process all repos in mine.yaml")
    parser.add_argument("--base", default=None,
                        help="upstream base branch; omit to auto-detect default_branch")
    parser.add_argument("--prefix", default=None,
                        help="path prefix filter; default per-repo from mine.yaml")
    parser.add_argument("--num_samples", type=int, default=None)
    parser.add_argument("--concurrency", type=int, default=4)
    args = parser.parse_args()

    repos = [args.repo] if args.repo else list(repo_prefix)
    entries = [
        {"repo": r,
         "prefix": args.prefix if args.prefix is not None
                   else repo_prefix.get(r, default_prefix)}
        for r in repos
    ]
    asyncio.run(run_repos(entries, args.base, args.num_samples, args.concurrency))


if __name__ == "__main__":
    main()
