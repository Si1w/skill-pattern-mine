"""Build label inputs for every in-scope candidate (no sampling).

Iterates the full ``(candidate, diff_row)`` set from
``label.instance.load_candidates`` and writes one input JSON per candidate,
each tagged ``sample_stratum="full"``. Writes to ``data/label/inputs/`` by
default; the labelling skill and hooks read this full set directly.

Usage:
    uv run python -m label.build
    uv run python -m label.build --out_dir data/label/inputs
"""

import argparse
import logging

from label.instance import INPUTS_DIR, load_candidates, write_instances

logger = logging.getLogger(__name__)
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)


def build_all(out_dir: str | None = None):
    pairs = load_candidates()
    tagged = [(dict(c, sample_stratum="full"), row) for c, row in pairs]
    logger.info("building %d full-sweep label inputs", len(tagged))
    return write_instances(tagged, out_dir or INPUTS_DIR)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out_dir", default=None,
                        help="label input output directory (default: data/label/inputs)")
    args = parser.parse_args()
    build_all(args.out_dir)


if __name__ == "__main__":
    main()
