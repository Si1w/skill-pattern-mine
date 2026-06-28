"""Draw a representative sample of label inputs for analysis.

Draws a fixed-size sample (default 300) over the full in-skill candidate set,
either stratified by upstream repo (quota proportional to its share, with every
repo guaranteed at least one item, largest-remainder allocation) or by simple
random sampling. Reproducible via ``--seed``.

Writes one input JSON per sampled candidate, tagged with its
``sample_stratum``, to ``data/label/sample/`` by default.

Usage:
    uv run python -m label.sample
    uv run python -m label.sample --method random
    uv run python -m label.sample --n 300 --seed 1104
"""

import argparse
import logging
import random
from collections import defaultdict
from pathlib import Path

from label.instance import load_candidates, write_instances

logger = logging.getLogger(__name__)
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

DEFAULT_OUT_DIR = Path("data/label/sample")
DEFAULT_SEED = 1104
DEFAULT_N = 300


def stratified_quotas(by_stratum: dict[str, list], n: int,
                      min_per: int = 1) -> dict[str, int]:
    """Allocate ``n`` across strata proportional to size (largest remainder).

    Every non-empty stratum is first guaranteed ``min_per`` items (capped by its
    size) so small repos are not dropped entirely — taxonomy construction needs
    coverage of every upstream. The remaining budget is then distributed
    proportionally over the strata that still have headroom, using the
    largest-remainder method. ``min_per`` is dropped if the floor alone would
    exceed ``n``.
    """
    sizes = {k: len(v) for k, v in by_stratum.items()}
    floor = min_per if sum(min(min_per, s) for s in sizes.values()) <= n else 0
    quotas = {k: min(floor, s) for k, s in sizes.items()}
    remaining = n - sum(quotas.values())
    if remaining <= 0:
        return quotas

    # Proportional share of the remaining budget over leftover headroom.
    headroom = {k: sizes[k] - quotas[k] for k in sizes}
    pool = sum(headroom.values())
    raw = {k: headroom[k] / pool * remaining for k in sizes} if pool else {}
    add = {k: min(headroom[k], int(raw.get(k, 0))) for k in sizes}
    leftover = remaining - sum(add.values())
    # Hand out the leftover by largest fractional remainder, capped by headroom.
    order = sorted(sizes, key=lambda k: raw.get(k, 0) - int(raw.get(k, 0)),
                   reverse=True)
    for k in order:
        if leftover <= 0:
            break
        if add[k] < headroom[k]:
            add[k] += 1
            leftover -= 1
    return {k: quotas[k] + add[k] for k in sizes}


def sample_stratified(pairs: list[tuple[dict, dict]], n: int,
                      rng: random.Random) -> list[tuple[dict, dict]]:
    """Draw ``n`` pairs stratified by upstream repo."""
    by_upstream: dict[str, list] = defaultdict(list)
    for c, row in pairs:
        by_upstream[c["upstream"]].append((c, row))
    quotas = stratified_quotas(by_upstream, n)
    out = []
    for upstream, group in by_upstream.items():
        picked = rng.sample(group, quotas[upstream])
        for c, row in picked:
            out.append((dict(c, sample_stratum=f"repo:{upstream}"), row))
    return out


def sample_random(pairs: list[tuple[dict, dict]], n: int,
                  rng: random.Random) -> list[tuple[dict, dict]]:
    """Draw ``n`` pairs by simple random sampling."""
    picked = rng.sample(pairs, min(n, len(pairs)))
    return [(dict(c, sample_stratum="random"), row) for c, row in picked]


def draw_sample(method: str = "stratified", n: int | None = None,
                seed: int = DEFAULT_SEED, out_dir: str | None = None) -> Path:
    pairs = load_candidates()
    if n is None:
        n = DEFAULT_N
    rng = random.Random(seed)
    logger.info("population=%d, target sample n=%d, method=%s, seed=%d",
                len(pairs), n, method, seed)
    if method == "stratified":
        sampled = sample_stratified(pairs, n, rng)
    else:
        sampled = sample_random(pairs, n, rng)
    logger.info("drew %d sampled label inputs", len(sampled))
    return write_instances(sampled, out_dir or DEFAULT_OUT_DIR)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--method", default="stratified",
                        choices=["stratified", "random"],
                        help="stratified by upstream (default) or simple random")
    parser.add_argument("--n", type=int, default=None,
                        help=f"sample size (default {DEFAULT_N})")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--out_dir", default=None,
                        help="output directory (default: data/label/sample)")
    args = parser.parse_args()
    draw_sample(args.method, args.n, args.seed, args.out_dir)


if __name__ == "__main__":
    main()
