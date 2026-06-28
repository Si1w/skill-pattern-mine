"""Search GitHub for candidate upstream skill repositories — the MSR search policy.

The policy runs in two stages:
  1. Search gate — keyword + popularity. Repositories whose name or
     description matches a keyword and whose popularity clears a star and fork
     threshold. Defaults — keyword "skill", >=20000 stars, >=2000 forks — live
     in `configs/mine.yaml` under `search` and are overridable via CLI. A
     bare keyword is noisy ("skill" matches many unrelated repos), so a second
     stage filters on content.
  2. Content filter — the inclusion criterion. A repository is kept only if its
     default-branch tree contains a `SKILL.md` file, the ground-truth marker of
     a Claude skill repo. Toggle with `require_skill_md` / `--no_skill_filter`.

Candidates are printed to stdout (full_name, stars, forks, has_skill_md) for
manual audit. Repositories that pass are not written anywhere automatically:
review the list and add the ones you want to the `repos` list in
`configs/mine.yaml` by hand before running the downstream steps.

Usage:
    uv run python -m mine.s01_search_repos
    uv run python -m mine.s01_search_repos --keyword skill --min_stars 20000 --min_forks 2000
    uv run python -m mine.s01_search_repos --keyword skill "agent skill"
"""

import argparse
import json
import logging
import subprocess
import time

from mine.utils import load_config

logger = logging.getLogger(__name__)
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

# GitHub's Search API serves only the first 1000 matches (10 pages of 100).
PER_PAGE = 100
SEARCH_CAP = 1000

FIELDS = [
    "full_name",
    "stargazers_count",
    "forks_count",
    "default_branch",
    "html_url",
    "description",
    "created_at",
    "pushed_at",
]


def build_query(keyword: str, min_stars: int, min_forks: int) -> str:
    """Compose the GitHub search query encoding the selection criteria."""
    return f"{keyword} stars:>={min_stars} forks:>={min_forks}"


def _gh_api(args: list[str], max_retries: int = 5) -> dict:
    """Run ``gh api`` with backoff and return the parsed JSON response.

    Deterministic client errors (404 missing repo/branch, 422 bad ref) are
    raised immediately rather than retried — backing off cannot fix them.
    """
    for attempt in range(max_retries):
        proc = subprocess.run(["gh", "api", *args], capture_output=True, text=True)
        if proc.returncode == 0:
            return json.loads(proc.stdout)
        err = (proc.stderr or "").strip()
        first = err.splitlines()[0][:200] if err else ""
        if "(HTTP 404)" in err or "(HTTP 422)" in err:
            raise RuntimeError(f"gh api {first}: {args}")
        wait = min(2 ** attempt, 60)
        logger.warning(
            "gh api failed (rc=%d, attempt %d/%d): %s — sleeping %ds",
            proc.returncode, attempt + 1, max_retries, first, wait,
        )
        time.sleep(wait)
    raise RuntimeError(f"gh api failed after {max_retries} attempts: {args}")


def _gh_search(query: str, sort: str, order: str, page: int) -> dict:
    """Fetch one page of repository search results."""
    return _gh_api([
        "-X", "GET", "search/repositories",
        "-f", f"q={query}",
        "-f", f"sort={sort}",
        "-f", f"order={order}",
        "-f", f"per_page={PER_PAGE}",
        "-f", f"page={page}",
    ])


def _tree_has_skill_md(tree: list[dict]) -> bool:
    """True if any blob in a git-tree listing is named ``SKILL.md``."""
    return any(
        e.get("type") == "blob" and e.get("path", "").rsplit("/", 1)[-1] == "SKILL.md"
        for e in tree
    )


def _codesearch_skill_md(full_name: str) -> bool:
    """Existence check via the code-search API; fallback for truncated trees."""
    try:
        result = _gh_api(["-X", "GET", "search/code",
                          "-f", f"q=repo:{full_name} filename:SKILL.md"])
    except RuntimeError as exc:
        logger.warning("[%s] code-search fallback failed; dropping despite a "
                       "possible SKILL.md: %s", full_name, exc)
        return False
    return result.get("total_count", 0) > 0


def has_skill_md(full_name: str, branch: str) -> bool:
    """Whether the repo's default-branch tree contains a ``SKILL.md`` file.

    Uses one recursive git-tree call. A repo that errors out (empty, branch
    gone, transient failure after retries) is treated as not containing the
    file and logged, so one bad repo never aborts the whole policy run. The
    recursive tree is capped by GitHub (~100k entries / 7MB); on truncation we
    fall back to the code-search API rather than silently excluding the repo.
    """
    try:
        result = _gh_api([f"repos/{full_name}/git/trees/{branch}?recursive=1"])
    except RuntimeError as exc:
        logger.warning("[%s] tree fetch failed; treating as no SKILL.md: %s",
                       full_name, exc)
        return False
    if _tree_has_skill_md(result.get("tree", [])):
        return True
    if result.get("truncated"):
        logger.warning("[%s] tree truncated at %d entries; falling back to "
                       "code search for SKILL.md",
                       full_name, len(result.get("tree", [])))
        return _codesearch_skill_md(full_name)
    return False


def search(query: str, sort: str, order: str,
           max_items: int | None = None) -> list[dict]:
    """Page through repository search results up to GitHub's 1000-result cap."""
    cap = min(max_items, SEARCH_CAP) if max_items else SEARCH_CAP
    rows: list[dict] = []
    page = 1
    while len(rows) < cap:
        logger.info("searching page %d (q=%r)", page, query)
        result = _gh_search(query, sort, order, page)
        if page == 1:
            logger.info("total_count=%d (serving first %d)",
                        result.get("total_count", 0), SEARCH_CAP)
        items = result.get("items", [])
        for it in items:
            rows.append({f: it.get(f) for f in FIELDS})
            if len(rows) >= cap:
                break
        if len(items) < PER_PAGE:
            break
        page += 1
    return rows


def search_keywords(keywords: list[str], min_stars: int, min_forks: int,
                    sort: str, order: str,
                    max_items: int | None = None) -> list[dict]:
    """Search each keyword separately and merge results, deduped by full_name.

    A bare keyword AND-matches its terms, so distinct keywords surface
    different repos; the shared 1000-result cap also applies per keyword.
    Running them separately and merging keeps each keyword's full reach.
    """
    merged: dict[str, dict] = {}
    for kw in keywords:
        query = build_query(kw, min_stars, min_forks)
        for r in search(query, sort, order, max_items):
            merged.setdefault(r["full_name"], r)
    return list(merged.values())


def print_results(rows: list[dict]) -> None:
    """Print one repo per line (full_name, stars, forks, has_skill_md) for audit."""
    for r in rows:
        mark = "yes" if r["has_skill_md"] else "no"
        print(f"{r['full_name']:<45} stars={r['stargazers_count']:<8} "
              f"forks={r['forks_count']:<8} skill_md={mark}")


def run(keywords: list[str], min_stars: int, min_forks: int, sort: str, order: str,
        require_skill_md: bool = True, num_samples: int | None = None) -> list[dict]:
    """Run the search policy and print candidates for manual audit.

    Queries GitHub for each keyword (results merged, deduped by full_name),
    tags each repo with a ``has_skill_md`` flag, and prints the candidates
    (those passing the content filter, when ``require_skill_md``). Nothing is
    written to disk; add the repos you want to configs/mine.yaml by hand.
    """
    rows = search_keywords(keywords, min_stars, min_forks, sort, order, num_samples)
    for r in rows:
        r["has_skill_md"] = has_skill_md(r["full_name"], r["default_branch"])
    logger.info("%d/%d searched repos contain SKILL.md",
                sum(r["has_skill_md"] for r in rows), len(rows))
    kept = [r for r in rows if r["has_skill_md"]] if require_skill_md else rows
    print_results(kept)
    return kept


def main():
    cfg = load_config().get("search", {})
    cfg_keyword = cfg.get("keyword", "skill")
    default_keywords = [cfg_keyword] if isinstance(cfg_keyword, str) else cfg_keyword
    parser = argparse.ArgumentParser()
    parser.add_argument("--keyword", nargs="+", default=default_keywords,
                        help="one or more keywords; each is searched separately "
                             "and the results are merged, deduped by full_name")
    parser.add_argument("--min_stars", type=int, default=cfg.get("min_stars", 20000))
    parser.add_argument("--min_forks", type=int, default=cfg.get("min_forks", 2000))
    parser.add_argument("--sort", default=cfg.get("sort", "stars"),
                        choices=["stars", "forks", "help-wanted-issues", "updated"])
    parser.add_argument("--order", default=cfg.get("order", "desc"),
                        choices=["desc", "asc"])
    parser.add_argument("--no_skill_filter", action="store_true",
                        help="keep all searched repos, do not require a SKILL.md file")
    parser.add_argument("--num_samples", type=int, default=None)
    args = parser.parse_args()
    require = cfg.get("require_skill_md", True) and not args.no_skill_filter
    run(args.keyword, args.min_stars, args.min_forks, args.sort, args.order,
        require_skill_md=require, num_samples=args.num_samples)


if __name__ == "__main__":
    main()
