"""Draw a human-audit sample from the full label outputs.

Sizes the sample with Cochran's formula (95% confidence, 5% margin of error,
worst-case proportion p=0.5) and applies the finite-population correction for
the audited population N, then draws that many records by simple random
sampling. Reproducible via ``--seed`` (default 1104).

For the full label outputs (N=1220) this yields n=293.

Writes the picked label-output JSONs to ``data/audit/sample/`` together with a
``manifest.json`` recording the sizing parameters and the picked file list, so a
human auditor can review exactly this set.

Usage:
    uv run python -m audit.cochran
    uv run python -m audit.cochran --confidence 0.95 --margin 0.05
    uv run python -m audit.cochran --seed 1104
"""

import argparse
import json
import logging
import math
import random
from pathlib import Path

logger = logging.getLogger(__name__)
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

DEFAULT_POP_DIR = Path("data/label/outputs")
DEFAULT_OUT_DIR = Path("data/audit/sample")
DEFAULT_SEED = 1104
DEFAULT_CONFIDENCE = 0.95
DEFAULT_MARGIN = 0.05
DEFAULT_P = 0.5

# z-scores for common two-sided confidence levels; avoids a scipy dependency.
Z_SCORES = {0.90: 1.645, 0.95: 1.96, 0.98: 2.326, 0.99: 2.576}


def z_score(confidence: float) -> float:
    """Return the two-sided z-score for ``confidence`` (e.g. 0.95 -> 1.96)."""
    if confidence not in Z_SCORES:
        raise ValueError(
            f"confidence {confidence} not supported; choose one of "
            f"{sorted(Z_SCORES)}"
        )
    return Z_SCORES[confidence]


def cochran_sample_size(population: int, confidence: float = DEFAULT_CONFIDENCE,
                        margin: float = DEFAULT_MARGIN,
                        p: float = DEFAULT_P) -> int:
    """Cochran sample size with finite-population correction, rounded up.

    ``n0 = z^2 * p * (1 - p) / margin^2`` is the infinite-population size; the
    finite-population correction ``n = n0 * N / (n0 + N - 1)`` adjusts it for the
    finite audited population ``N``. ``p=0.5`` maximises the variance, giving the
    most conservative (largest) sample for a worst-case label-error proportion.
    """
    z = z_score(confidence)
    n0 = z ** 2 * p * (1 - p) / margin ** 2
    n = n0 * population / (n0 + population - 1)
    return min(population, math.ceil(n))


def draw_audit_sample(pop_dir: str | None = None, out_dir: str | None = None,
                      confidence: float = DEFAULT_CONFIDENCE,
                      margin: float = DEFAULT_MARGIN, p: float = DEFAULT_P,
                      seed: int = DEFAULT_SEED) -> Path:
    """Size and draw the audit sample, writing the picks plus a manifest."""
    pop_path = Path(pop_dir or DEFAULT_POP_DIR)
    files = sorted(pop_path.glob("*.json"))
    if not files:
        raise FileNotFoundError(f"no label outputs found under {pop_path}")

    population = len(files)
    n = cochran_sample_size(population, confidence, margin, p)
    logger.info(
        "population=%d, audit sample n=%d (confidence=%.2f, margin=%.2f, p=%.2f, "
        "seed=%d)", population, n, confidence, margin, p, seed
    )

    rng = random.Random(seed)
    picked = sorted(rng.sample(files, n), key=lambda f: f.name)

    out_path = Path(out_dir or DEFAULT_OUT_DIR)
    out_path.mkdir(parents=True, exist_ok=True)
    for f in picked:
        (out_path / f.name).write_text(f.read_text(), encoding="utf-8")

    manifest = {
        "population_dir": str(pop_path),
        "population": population,
        "sample_size": n,
        "sizing": {
            "method": "cochran",
            "confidence": confidence,
            "margin_of_error": margin,
            "p": p,
            "z": z_score(confidence),
            "finite_population_correction": True,
        },
        "seed": seed,
        "files": [f.name for f in picked],
    }
    (out_path / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    logger.info("wrote %d audit-sample files + manifest.json to %s", n, out_path)
    return out_path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pop_dir", default=None,
                        help="population directory (default: data/label/outputs)")
    parser.add_argument("--out_dir", default=None,
                        help="output directory (default: data/audit/sample)")
    parser.add_argument("--confidence", type=float, default=DEFAULT_CONFIDENCE,
                        choices=sorted(Z_SCORES),
                        help=f"confidence level (default {DEFAULT_CONFIDENCE})")
    parser.add_argument("--margin", type=float, default=DEFAULT_MARGIN,
                        help=f"margin of error (default {DEFAULT_MARGIN})")
    parser.add_argument("--p", type=float, default=DEFAULT_P,
                        help=f"assumed proportion (default {DEFAULT_P})")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    args = parser.parse_args()
    draw_audit_sample(args.pop_dir, args.out_dir, args.confidence, args.margin,
                      args.p, args.seed)


if __name__ == "__main__":
    main()
