"""Run the optional PyDriller compatibility experiment from the project root."""

import argparse
import logging
import sys
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from src.pydriller_pilot import run_pilot


def main() -> int:
    """Keep fixture checks and real repository acquisition separately runnable."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config", type=Path, default=PROJECT_ROOT / "configs/pydriller-pilot.yaml"
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=PROJECT_ROOT / "data/skill-pattern-mine/monthly-review-example.json",
        help="Saved monthly observations for the real comparison.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=PROJECT_ROOT / "data/skill-pattern-mine/pydriller-pilot.json",
        help="Result JSON file; must not already exist.",
    )
    parser.add_argument("--step", choices=["all", "fixtures", "real"], default="all")
    parser.add_argument(
        "--num_samples",
        type=int,
        help="Bound saved monthly cases, never commit history.",
    )
    args = parser.parse_args()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    logging.getLogger("pydriller").setLevel(logging.WARNING)
    report = run_pilot(
        yaml.safe_load(args.config.read_text()),
        source_path=args.input,
        output=args.output,
        limit=args.num_samples,
        step=args.step,
    )
    logging.info(
        "Adapted checks passed=%s; direct replacement rejected=%s",
        report["adapted_checks_passed"],
        report["direct_replacement_rejected"],
    )
    return 0 if report["adapted_checks_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
