"""Plot the application domains of the cohort repositories as a donut chart.

Reads the purpose review table, counts the retained repositories per
descriptive domain, and writes a CSV and a PNG under eval/tables-and-figures.
The domain column is descriptive only; it plays no part in selection.
"""

import csv
import math
from collections import Counter
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

PROJECT_ROOT = Path(__file__).resolve().parents[2]
REVIEW = PROJECT_ROOT / "docs/repository-review-2026-10-21.csv"
OUTPUT = PROJECT_ROOT / "eval/tables-and-figures"

# Colors come from the project palettes in .agents/spec/academic-palettes.md,
# ordered so that every adjacent pair passed the colour vision deficiency and
# normal vision separation checks of the dataviz validator. The light steps fall
# below its contrast threshold, so every slice also carries a direct label.
COLORS = ["#376795", "#72BCD5", "#E76254", "#F7AA58", "#1E466E", "#EF8A47", "#528FAD"]
INK = "#1E466E"


def domain_counts() -> list[tuple[str, int]]:
    """Count retained repositories per domain, largest first."""
    with REVIEW.open() as stream:
        rows = [row for row in csv.DictReader(stream) if row["decision"] == "include"]
    counts = Counter(row["domain"] for row in rows)
    return sorted(counts.items(), key=lambda item: (-item[1], item[0]))


def main() -> None:
    counts = domain_counts()
    total = sum(count for _, count in counts)
    OUTPUT.mkdir(parents=True, exist_ok=True)
    with (OUTPUT / "corpus-domains.csv").open("w", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["domain", "repositories", "share"])
        for domain, count in counts:
            writer.writerow([domain, count, f"{count / total:.3f}"])

    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10, "text.color": INK})
    figure, axis = plt.subplots(figsize=(6.4, 4.2), dpi=200)
    wedges, _ = axis.pie(
        [count for _, count in counts],
        colors=COLORS[: len(counts)],
        startangle=90,
        counterclock=False,
        wedgeprops={"width": 0.38, "edgecolor": "white", "linewidth": 2},
    )
    for wedge, (domain, count) in zip(wedges, counts):
        angle = (wedge.theta2 + wedge.theta1) / 2
        x, y = math.cos(math.radians(angle)), math.sin(math.radians(angle))
        side = "right" if x < 0 else "left"
        axis.annotate(
            f"{domain}  {count}",
            xy=(x, y),
            xytext=(1.28 * (1 if x >= 0 else -1), 1.18 * y),
            ha=side,
            va="center",
            fontsize=9,
            color=INK,
            arrowprops={"arrowstyle": "-", "color": "#9AA5B1", "lw": 0.8, "shrinkA": 0, "shrinkB": 2},
        )
    axis.text(0, 0.06, str(total), ha="center", va="center", fontsize=22, fontweight="bold", color=INK)
    axis.text(0, -0.16, "repositories", ha="center", va="center", fontsize=9, color="#4A5561")
    axis.set_aspect("equal")
    axis.set_xlim(-2.1, 2.1)
    axis.set_ylim(-1.3, 1.3)
    axis.set_title("Cohort repositories by application domain", fontsize=11, pad=8)
    figure.tight_layout()
    figure.savefig(OUTPUT / "corpus-domains.png", bbox_inches="tight")
    print(OUTPUT / "corpus-domains.png")
    for domain, count in counts:
        print(f"{count:3d}  {domain}")


if __name__ == "__main__":
    main()
