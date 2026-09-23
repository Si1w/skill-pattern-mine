"""Compare the production Git reader with frozen API observations."""

import importlib.metadata
import json
import logging
import platform
import subprocess
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode

from git import Actor, Repo

from src.config import load_saved_config
from src.domain import Fork, MonthlyRecord
from src.extract import (
    PackageStore,
    build_record,
    classify_origin,
    fetch_history,
    file_changes,
    first_parent_lineage,
    upstream_fingerprints,
)
from src.github import GitHubClient, collect_pages, utcnow, write_json
from src.git_objects import LocalObjects

logger = logging.getLogger(__name__)


def monthly_record(store, head, cutoff, root, month) -> dict:
    """Derive monthly boundaries from complete states on the first parent path."""
    lineage = first_parent_lineage(store.history, head, cutoff)
    indexes = [
        i
        for i, c in enumerate(lineage)
        if c.parent_shas
        and c.committer_date.astimezone(timezone.utc).strftime("%Y-%m") == month
        and store.state(c.parent_shas[0], root) != store.state(c.sha, root)
    ]
    if not indexes:
        raise ValueError(f"No package changes in {month}.")
    first, last = indexes[0], indexes[-1]
    return {
        "before_sha": lineage[first].parent_shas[0],
        "after_sha": lineage[last].sha,
        "changed_commits": [lineage[i].sha for i in indexes],
        "source_commits": [c.sha for c in lineage[first : last + 1]],
    }


def fixture_repository(path: Path) -> tuple[Repo, dict]:
    """Create known monthly outcomes, including a side change integrated later."""
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


def direct_changes(store, commits, boundaries, root) -> list[dict]:
    """Check direct modifications against full states for each source transition."""
    results = []
    for sha in boundaries["changed_commits"]:
        source = commits[sha]
        parent = store.history[sha].parent_shas[0]
        expected = file_changes(store.snapshot(parent, root), store.snapshot(sha, root))
        modifications = source.modified_files
        observed = {
            p
            for m in modifications
            for p in (m.old_path, m.new_path)
            if p and (root == "." or p.startswith(root + "/"))
        }
        expected_paths = {c.path for c in expected}
        results.append(
            {
                "sha": sha,
                "parents": source.parents,
                "expected_paths": sorted(expected_paths),
                "reported_paths": sorted(observed),
                "missing_paths": sorted(expected_paths - observed),
                "extra_paths": sorted(observed - expected_paths),
            }
        )
    return results


def fixture_comparison(work: Path) -> dict:
    """Record expected edge outcomes before consulting PyDriller modifications."""
    repo, expected = fixture_repository(work)
    try:
        client = LocalObjects(repo)
        history, commits = client.history(repo.head.commit.hexsha, retain_commits=True)
        store = PackageStore(client, "fixture/repo", history, 10485760)
        cutoff = datetime(2026, 6, 1, tzinfo=timezone.utc)
        cases = []
        for month, ends in expected.items():
            boundaries = monthly_record(
                store, repo.head.commit.hexsha, cutoff, "skills/demo", month
            )
            changes = file_changes(
                store.snapshot(ends[0], "skills/demo"),
                store.snapshot(ends[1], "skills/demo"),
            )
            checks = {
                "endpoints_match": (boundaries["before_sha"], boundaries["after_sha"])
                == ends
            }
            if month == "2026-04":
                checks.update(
                    {
                        "deletion_preserved": any(
                            c.status == "removed" for c in changes
                        ),
                        "binary_preserved": any(
                            c.encoding_after == "base64" and c.content_after == "AP8="
                            for c in changes
                        ),
                        "mode_preserved": any(
                            c.mode_before == "100644" and c.mode_after == "100755"
                            for c in changes
                        ),
                    }
                )
            if month == "2026-05":
                checks["cancellation_preserved"] = (
                    not changes and len(boundaries["changed_commits"]) == 2
                )
            cases.append(
                {
                    "month": month,
                    "checks": checks,
                    "boundaries": boundaries,
                    "direct": direct_changes(store, commits, boundaries, "skills/demo"),
                }
            )
        return {"cases": cases, "passed": all(all(c["checks"].values()) for c in cases)}
    finally:
        repo.close()


def real_comparison(
    settings: dict, source_path: Path, work: Path, limit: int | None
) -> dict:
    """Compare frozen real histories and observations with fresh API evidence."""
    source = json.loads(source_path.read_text())
    config = load_saved_config(source["extraction"]["settings"])
    inputs = source["extraction"]["inputs"][0]
    fork = Fork.model_validate(inputs["fork"])
    cutoff = datetime.fromisoformat(source["extraction"]["cutoff_utc"])
    references = {
        fork.full_name: fork.default_branch_sha,
        fork.upstream: inputs["upstream_sha"],
    }
    selected = settings["sample_keys"][:limit]
    if not selected:
        raise ValueError("The pilot needs at least one saved observation.")
    api = GitHubClient(
        work / "api",
        api_version=config.github.api_version,
        max_attempts=config.github.max_attempts,
        timeout_seconds=config.github.timeout_seconds,
    )
    repo = Repo.init(work / "objects.git", bare=True)
    report = {
        "references": references,
        "histories": {},
        "cases": [],
        "path_histories": {},
        "timing_scope": "Fetch is separate; first API read uses an empty response cache, later reads reuse it. Local reads follow fetch. OS disk caches are not cleared. One network only; no population speedup estimate.",
    }
    try:
        for name, head in references.items():
            logger.info("Fetching frozen Git ancestry: %s %s", name, head[:12])
            start = time.perf_counter()
            subprocess.run(
                [
                    "git",
                    "-C",
                    str(repo.git_dir),
                    "fetch",
                    "--no-tags",
                    "--quiet",
                    f"https://github.com/{name}.git",
                    head,
                ],
                check=True,
                capture_output=True,
                timeout=settings["git_timeout_seconds"],
            )
            report["histories"][name] = {"fetch_seconds": time.perf_counter() - start}
        local = LocalObjects(repo)
        api_histories, local_histories, pydriller_commits = {}, {}, {}
        for name, head in references.items():
            timings = {"api": [], "local": []}
            for repetition in range(settings["repetitions"]):
                for backend in (
                    ["api", "local"] if repetition % 2 == 0 else ["local", "api"]
                ):
                    start = time.perf_counter()
                    if backend == "api":
                        api_histories[name] = fetch_history(
                            api, name, head, config.github.per_page
                        )
                    else:
                        local_histories[name], pydriller_commits[name] = local.history(
                            head, retain_commits=True
                        )
                    timings[backend].append(time.perf_counter() - start)
            remote, nearby = api_histories[name], local_histories[name]
            core = ["sha", "tree_sha", "parent_shas", "author_date", "committer_date"]
            differences = [
                {
                    "sha": sha,
                    "fields": [
                        field
                        for field in core
                        if getattr(remote[sha], field) != getattr(nearby[sha], field)
                    ],
                }
                for sha in sorted(remote.keys() & nearby.keys())
            ]
            differences = [d for d in differences if d["fields"]]
            report["histories"][name].update(
                {
                    "api_commits": len(remote),
                    "local_commits": len(nearby),
                    "missing_local": sorted(remote.keys() - nearby.keys()),
                    "extra_local": sorted(nearby.keys() - remote.keys()),
                    "core_differences": differences,
                    "message_differences": [
                        sha
                        for sha in sorted(remote.keys() & nearby.keys())
                        if remote[sha].message != nearby[sha].message
                    ],
                    "github_login_only_available_from_api": sum(
                        c.author_login is not None for c in remote.values()
                    ),
                    "seconds": timings,
                }
            )
        local_stores = {
            name: PackageStore(local, name, rows, config.extraction.maximum_blob_bytes)
            for name, rows in local_histories.items()
        }
        api_store = PackageStore(
            api,
            fork.full_name,
            api_histories[fork.full_name],
            config.extraction.maximum_blob_bytes,
        )
        store, upstream = local_stores[fork.full_name], local_stores[fork.upstream]
        signatures = {}
        for key in selected:
            expected = MonthlyRecord.model_validate(source[key])
            instance = expected.instance
            root = instance.skill_package_path
            if instance.fork != fork.full_name:
                raise ValueError("Review record does not match the frozen fork.")
            logger.info("Comparing %s %s", instance.month, root)
            start = time.perf_counter()
            boundaries = monthly_record(
                store, fork.default_branch_sha, cutoff, root, instance.month
            )
            if root not in signatures:
                endpoint = f"repos/{fork.upstream}/commits?" + urlencode(
                    {
                        "sha": inputs["upstream_sha"],
                        "path": root,
                        "per_page": config.github.per_page,
                    }
                )
                api_rows, coverage = collect_pages(api, endpoint)
                local_rows = local.get(endpoint).body
                api_shas, local_shas = (
                    {r["sha"] for r in api_rows},
                    {r["sha"] for r in local_rows},
                )
                report["path_histories"][root] = {
                    "api_complete": coverage["complete"],
                    "api_commits": len(api_shas),
                    "local_commits": len(local_shas),
                    "missing_local": sorted(api_shas - local_shas),
                    "extra_local": sorted(local_shas - api_shas),
                }
                signatures[root] = upstream_fingerprints(
                    upstream, inputs["upstream_sha"], root, config.github.per_page
                )
            evidence = [
                classify_origin(
                    store.history[sha], root, store, upstream, signatures[root]
                )
                for sha in boundaries["changed_commits"]
            ]
            before = store.snapshot(boundaries["before_sha"], root)
            after = store.snapshot(boundaries["after_sha"], root)
            observed = build_record(
                fork,
                root,
                instance.month,
                boundaries["before_sha"],
                boundaries["after_sha"],
                boundaries["source_commits"],
                evidence,
                before,
                after,
                cutoff,
            )
            local_seconds = time.perf_counter() - start
            start = time.perf_counter()
            before_api = api_store.snapshot(instance.before.commit_sha, root)
            after_api = api_store.snapshot(instance.after.commit_sha, root)
            checks = {
                "before_matches_fresh_api": before == before_api,
                "after_matches_fresh_api": after == after_api,
                "complete_record_matches_saved_api": observed == expected,
                "changed_commits_match_saved_api": boundaries["changed_commits"]
                == [e.commit_sha for e in expected.origin_evidence],
            }
            report["cases"].append(
                {
                    "key": key,
                    "month": instance.month,
                    "root": root,
                    "checks": checks,
                    "boundaries": boundaries,
                    "files_before": len(before),
                    "files_after": len(after),
                    "local_record_seconds_including_path_evidence_api": local_seconds,
                    "api_endpoint_seconds": time.perf_counter() - start,
                    "direct": direct_changes(
                        store, pydriller_commits[fork.full_name], boundaries, root
                    ),
                    "observed_origin_kinds": [e.kind for e in observed.origin_evidence],
                    "expected_origin_kinds": [e.kind for e in expected.origin_evidence],
                    "exclusion_reason": observed.instance.exclusion_reason,
                }
            )
        report["api_requests"] = api.requests
        report["api_cache_hits"] = api.cache_hits
        report["git_bytes"] = sum(
            p.stat().st_size for p in Path(repo.git_dir).rglob("*") if p.is_file()
        )
        report["api_cache_bytes"] = sum(
            p.stat().st_size for p in (work / "api").rglob("*") if p.is_file()
        )
        report["passed"] = (
            all(
                not any(
                    h[k] for k in ["missing_local", "extra_local", "core_differences"]
                )
                for h in report["histories"].values()
            )
            and all(
                p["api_complete"] and not p["missing_local"] and not p["extra_local"]
                for p in report["path_histories"].values()
            )
            and all(all(c["checks"].values()) for c in report["cases"])
        )
        return report
    finally:
        repo.close()


def run_pilot(
    settings: dict, *, source_path: Path, output: Path, limit: int | None, step: str
) -> dict:
    """Write compact evidence and remove all temporary objects on every exit."""
    if output.exists():
        raise ValueError("Pilot result already exists; choose a new --output path.")
    if settings["repetitions"] < 1 or (limit is not None and limit < 1):
        raise ValueError("Repetitions and sample bounds must be positive.")
    report = {
        "created_at": utcnow(),
        "settings": settings,
        "input": str(source_path.resolve()),
        "output": str(output.resolve()),
        "num_samples": limit,
        "step": step,
        "python": platform.python_version(),
        "platform": platform.platform(),
        "versions": {
            name: importlib.metadata.version(name)
            for name in [
                "pydriller",
                "gitpython",
                "gitdb",
                "smmap",
                "lizard",
                "pytz",
                "types-pytz",
                "pygments",
                "pathspec",
                "pydantic",
                "pyyaml",
            ]
        },
        "git_version": subprocess.check_output(["git", "--version"], text=True).strip(),
    }
    try:
        with tempfile.TemporaryDirectory(
            prefix="skill-pattern-mine-pydriller-"
        ) as directory:
            work = Path(directory)
            if step in {"all", "fixtures"}:
                report["fixtures"] = fixture_comparison(work / "fixture")
            if step in {"all", "real"}:
                report["real"] = real_comparison(settings, source_path, work, limit)
            components = [report[k] for k in ["fixtures", "real"] if k in report]
            direct = [
                d for result in components for c in result["cases"] for d in c["direct"]
            ]
            report["direct_transitions"] = len(direct)
            report["direct_transitions_with_missing_paths"] = sum(
                bool(d["missing_paths"]) for d in direct
            )
            report["adapted_checks_passed"] = all(r["passed"] for r in components)
            report["direct_replacement_rejected"] = any(
                d["missing_paths"] or d["extra_paths"] for d in direct
            )
        report["temporary_data_removed"] = not work.exists()
    except Exception as error:
        report["error"] = f"{type(error).__name__}: {error}"
        write_json(output, report)
        raise
    write_json(output, report)
    return report
