"""Run repository discovery, fork mining, verification and monthly extraction."""

import argparse
import logging
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from src.config import load_config
from src.extract import extract_monthly, frozen_references, load_extraction_inputs
from src.forks import retrieve_forks
from src.git_history import GitSource
from src.github import ApiError, GitHubClient
from src.repositories import import_confirmed_repositories, retrieve_repositories
from src.review import export_repository_review
from src.run import RunRecord, prepare_run
from src.storage import read_jsonl, write_json
from src.verify import verify_run

logger = logging.getLogger(__name__)

RUNS_ROOT = "data/skill-pattern-mine/runs"
SIMPLE_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]*")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=PROJECT_ROOT / "configs/skill-pattern-mine.yaml")
    parser.add_argument(
        "--step", choices=["all", "repositories", "forks", "verify", "extract", "review"], default="all"
    )
    parser.add_argument("--run_id", help="Reuse an existing ID to resume its saved API snapshot.")
    parser.add_argument("--source_run", help="Candidate run whose frozen evidence supplies the approved repositories.")
    parser.add_argument(
        "--num_samples",
        type=int,
        help="Maximum hits per query, repositories, forks per upstream and commits per comparison; "
        "extract bounds monthly candidates per fork instead of history.",
    )
    parser.add_argument(
        "--pilot", action="store_true", default=None,
        help="Allow pending screening candidates for engineering validation only.",
    )
    parser.add_argument("--offline", action="store_true", help="Replay saved responses without network requests.")
    parser.add_argument("--month", help="Extract one UTC month (YYYY-MM); omit to process all observed months.")
    parser.add_argument(
        "--allow_partial", action="store_true",
        help="Allow partial acquisition inputs only inside a bounded pilot run.",
    )
    args = parser.parse_args()
    if args.num_samples is not None and args.num_samples < 1:
        parser.error("--num_samples must be positive")
    if args.month and not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", args.month):
        parser.error("--month must be YYYY-MM")
    if (args.month or args.allow_partial) and args.step != "extract":
        parser.error("--month and --allow_partial are extraction options")
    if (args.offline or args.step in {"forks", "verify", "review", "extract"}) and not args.run_id:
        parser.error("This operation requires --run_id")
    args.run_id = args.run_id or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    for option in ("run_id", "source_run"):
        value = getattr(args, option)
        if value and not SIMPLE_NAME.fullmatch(value):
            parser.error(f"--{option} must be a simple directory name")
    return args


def github_client(root: Path, run: RunRecord, offline: bool) -> GitHubClient:
    return GitHubClient(
        root,
        api_version=run.config.github.api_version,
        max_attempts=run.config.github.max_attempts,
        timeout_seconds=run.config.github.timeout_seconds,
        offline=offline,
        wait_for_rate_limit=not run.pilot,
    )


def run_acquisition(args: argparse.Namespace, root: Path, run: RunRecord) -> int:
    """Run the repositories, forks and verify steps that the step argument selects."""
    config = run.config
    client = github_client(root, run, args.offline)
    if args.step in {"all", "repositories"}:
        if run.source_run_id:
            import_confirmed_repositories(root.parent / run.source_run_id, root, config)
        else:
            retrieve_repositories(client, config, root, limit=run.num_samples)
    if args.step in {"all", "forks"}:
        retrieve_forks(client, config, root, limit=run.num_samples, pilot=run.pilot)
    passed = True
    if args.step in {"all", "verify"}:
        report = verify_run(root)
        passed = report["status"] == "passed"
        logger.info(
            "Acceptance %s: %d repositories, %d forks, %d source commits",
            report["status"], report["repositories"], report["forks"], report["source_commits"],
        )
    errors = read_jsonl(root / "repository_errors.jsonl") + read_jsonl(root / "fork_errors.jsonl")
    write_json(
        root / "last_execution.json",
        {
            "step": args.step,
            "offline": args.offline,
            "network_requests": client.requests,
            "cache_hits": client.cache_hits,
            "errors": len(errors),
        },
    )
    logger.info("Requests=%d; cache hits=%d; errors=%d", client.requests, client.cache_hits, len(errors))
    return 0 if passed and not errors else 1


def run_extraction(args: argparse.Namespace, root: Path, run: RunRecord) -> int:
    """Extract monthly records from local Git history of the accepted acquisition."""
    if args.allow_partial and not run.pilot:
        raise ValueError("--allow_partial requires a bounded pilot run.")
    inputs = load_extraction_inputs(root, run, allow_partial=args.allow_partial)
    with GitSource(
        root / "git_evidence",
        frozen_references(inputs),
        timeout_seconds=run.config.extraction.git_timeout_seconds,
        maximum_blob_bytes=run.config.extraction.maximum_blob_bytes,
        offline=args.offline,
    ) as source:
        report = extract_monthly(
            source, run.config, root, inputs, run.cutoff_utc,
            month=args.month, limit=run.num_samples, partial_acquisition=args.allow_partial,
        )
        workspace = source.workspace_path
    write_json(
        root / "last_execution.json",
        {
            "step": "extract",
            "offline": args.offline,
            "git_fetches": report["git_fetches"],
            "git_cache_hits": report["git_cache_hits"],
            "temporary_git_removed": workspace is None or not workspace.exists(),
            "errors": report["errors"],
        },
    )
    logger.info(
        "Monthly acceptance %s: %d records, %d candidates, %d excluded, %d errors",
        report["status"], report["records"], report["customization_candidates"],
        report["excluded_unresolved_upstream"], report["errors"],
    )
    return 0 if report["status"] == "passed" else 1


def main() -> int:
    args = parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    logging.getLogger("pydriller").setLevel(logging.WARNING)
    root = PROJECT_ROOT / RUNS_ROOT / args.run_id
    try:
        if args.step == "review":
            logger.info("Repository review exported: %s", export_repository_review(root))
            return 0
        if args.step in {"forks", "verify", "extract"} and not (root / "run.json").exists():
            raise ValueError("This step requires an existing acquisition run.")
        run = prepare_run(
            root, load_config(args.config),
            pilot=args.pilot, limit=args.num_samples, offline=args.offline, source_run_id=args.source_run,
        )
        logger.info("Run %s; cutoff %s; pilot=%s; limit=%s", root, run.cutoff_utc, run.pilot, run.num_samples)
        if args.step == "extract":
            return run_extraction(args, root, run)
        return run_acquisition(args, root, run)
    except (ApiError, ValueError, OSError, KeyError) as error:
        logger.error("Stopped: %s", error)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
