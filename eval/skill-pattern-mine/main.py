"""Run repository discovery and fork mining from the project root."""

import argparse
import json
import logging
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from src.acquisition import import_confirmed_repositories, import_recovery_cache, load_extraction_inputs, prepare_run, verify_run
from src.config import load_config
from src.domain import Fork, RepositorySnapshot
from src.extract import extract_monthly
from src.github import ApiError, GitHubClient, read_jsonl, write_json
from src.retrieve import retrieve_forks, retrieve_repositories
from src.review import export_repository_review

logger = logging.getLogger(__name__)


def main() -> int:
    """Execute separate acquisition stages with the same frozen run settings."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config", type=Path, default=PROJECT_ROOT / "configs/skill-pattern-mine.yaml"
    )
    parser.add_argument(
        "--step",
        choices=["all", "repositories", "forks", "verify", "extract", "review"],
        default="all",
    )
    parser.add_argument(
        "--run_id", help="Reuse an existing ID to resume its saved API snapshot."
    )
    parser.add_argument(
        "--source_run",
        help="Candidate run whose frozen evidence supplies the approved repositories.",
    )
    parser.add_argument(
        "--recover_run",
        help="Recover cached fork evidence into a new run, preserving the source cutoff and sample bounds.",
    )
    parser.add_argument(
        "--num_samples",
        type=int,
        help="Maximum hits per query, repositories, forks per upstream and commits per comparison; extract bounds monthly candidates per fork instead of history.",
    )
    parser.add_argument(
        "--pilot",
        action="store_true",
        default=None,
        help="Allow pending screening candidates for engineering validation only.",
    )
    parser.add_argument(
        "--offline",
        action="store_true",
        help="Replay saved responses without network requests.",
    )
    parser.add_argument(
        "--input",
        type=Path,
        help="A saved acquisition review JSON, for an extraction pilot.",
    )
    parser.add_argument(
        "--month",
        help="Extract one UTC month (YYYY-MM); omit to process all observed months.",
    )
    parser.add_argument(
        "--allow_partial", action="store_true",
        help="Allow partial acquisition inputs only inside a bounded pilot run.",
    )
    args = parser.parse_args()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    logging.getLogger("pydriller").setLevel(logging.WARNING)
    if args.num_samples is not None and args.num_samples < 1:
        parser.error("--num_samples must be positive")
    if args.month and not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", args.month):
        parser.error("--month must be YYYY-MM")
    if (args.input or args.month or args.allow_partial) and args.step != "extract":
        parser.error("--input, --month and --allow_partial are extraction options")
    if (args.offline or args.step in {"forks", "verify", "review"}) and not args.run_id:
        parser.error("This operation requires --run_id")
    run_id = args.run_id or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", run_id):
        parser.error("--run_id must be a simple directory name")
    if args.source_run and not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", args.source_run):
        parser.error("--source_run must be a simple directory name")
    if args.recover_run and not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", args.recover_run):
        parser.error("--recover_run must be a simple directory name")
    try:
        config = load_config(args.config)
        root = PROJECT_ROOT / "data/skill-pattern-mine/runs" / run_id
        if args.step == "review":
            report = export_repository_review(root)
            logger.info("Repository review exported: %s", report)
            return 0
        if args.step in {"forks", "verify"} and not (root / "run.json").exists():
            raise ValueError("This step requires an existing acquisition run.")
        run = prepare_run(
            root, config, pilot=args.pilot, limit=args.num_samples, offline=args.offline,
            source_run_id=args.source_run,
            recovery_run_id=args.recover_run,
        )
        logger.info(
            "Run %s; cutoff %s; pilot=%s; limit=%s",
            root,
            run["cutoff_utc"],
            run["pilot"],
            run["num_samples"],
        )
        client = GitHubClient(
            root,
            api_version=config.github.api_version,
            max_attempts=config.github.max_attempts,
            timeout_seconds=config.github.timeout_seconds,
            offline=args.offline,
            wait_for_rate_limit=not run["pilot"],
        )
        if args.step == "extract":
            if args.allow_partial and not run["pilot"]:
                raise ValueError("--allow_partial requires a bounded pilot run.")
            cutoff = datetime.fromisoformat(run["cutoff_utc"])
            excluded = {
                (row["fork"]["upstream"], row["fork"]["full_name"], row["fork"]["default_branch_sha"])
                for row in read_jsonl(root / "fork_exclusions.jsonl")
            }
            if args.input:
                if not run["pilot"]:
                    raise ValueError("A review sample requires --pilot.")
                source = json.loads(args.input.read_text())
                repository = RepositorySnapshot.model_validate(source["repository"])
                fork = Fork.model_validate(source["comparison"]["fork"])
                if (fork.upstream, fork.full_name, fork.default_branch_sha) in excluded:
                    raise ValueError("Review input references an excluded fork history.")
                if (
                    not repository.tree_complete
                    or repository.repository.excluded_by
                    or fork.upstream != repository.repository.full_name
                    or source["comparison"]["upstream_sha"]
                    != repository.default_branch_sha
                ):
                    raise ValueError(
                        "Review sample references or repository eligibility are inconsistent."
                    )
                inputs = [(fork, repository.default_branch_sha)]
                cutoff = min(
                    cutoff, datetime.fromisoformat(source["run"]["cutoff_utc"])
                )
            else:
                inputs = load_extraction_inputs(root, run, allow_partial=args.allow_partial)
            report = extract_monthly(
                client,
                config,
                root,
                inputs,
                cutoff,
                month=args.month,
                limit=run["num_samples"],
                partial_acquisition=bool(args.allow_partial or args.input),
            )
            write_json(
                root / "last_execution.json",
                {
                    "step": "extract",
                    "offline": args.offline,
                    "network_requests": client.requests,
                    "cache_hits": client.cache_hits,
                    "history_backend": report["history_backend"],
                    "git_fetches": report["git_fetches"],
                    "git_cache_hits": report["git_cache_hits"],
                    "errors": report["errors"],
                },
            )
            logger.info(
                "Monthly acceptance %s: %d records, %d candidates, %d excluded, %d errors",
                report["status"],
                report["records"],
                report["customization_candidates"],
                report["excluded_unresolved_upstream"],
                report["errors"],
            )
            return 0 if report["status"] == "passed" else 1
        if (
            args.step in {"all", "forks"}
            and not run["pilot"]
            and config.screening.selection_mode == "calibrated_ratio"
            and config.screening.skill_centricity_threshold is None
        ):
            raise ValueError(
                "Formal fork mining requires a calibrated screening threshold. "
                "Use the repositories step for calibration inputs or --pilot for "
                "bounded engineering validation."
            )
        if args.step in {"all", "repositories"}:
            if config.screening.selection_mode == "confirmed_reviews":
                if not run.get("source_run_id"):
                    raise ValueError("Confirmed selection requires --source_run on a new run.")
                import_confirmed_repositories(
                    root.parent / run["source_run_id"], root, config
                )
            else:
                retrieve_repositories(client, config, root, limit=run["num_samples"])
        if args.step in {"all", "forks"}:
            if run.get("recovery_run_id"):
                import_recovery_cache(root.parent / run["recovery_run_id"], root)
            retrieve_forks(
                client, config, root, limit=run["num_samples"], pilot=run["pilot"]
            )
        passed = True
        if args.step in {"all", "verify"}:
            report = verify_run(root)
            passed = report["status"] == "passed"
            logger.info(
                "Acceptance %s: %d repositories, %d forks, %d source commits",
                report["status"],
                report["repositories"],
                report["forks"],
                report["source_commits"],
            )
        errors = read_jsonl(root / "repository_errors.jsonl") + read_jsonl(
            root / "fork_errors.jsonl"
        )
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
        logger.info(
            "Requests=%d; cache hits=%d; errors=%d",
            client.requests,
            client.cache_hits,
            len(errors),
        )
        return 0 if passed and not errors else 1
    except (ApiError, ValueError, OSError, KeyError) as error:
        logger.error("Acquisition stopped: %s", error)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
