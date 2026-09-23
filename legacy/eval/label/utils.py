"""Shared helpers for the RQ1-RQ5 result scripts.

Centralises corpus loading, the label-to-family taxonomy map, skill-root
recovery from instance patches, the prevalence/breadth/coverage metric, and the
academic colour palette. The current ``data/analysis/instances.jsonl`` stores
flat ``labels`` per instance; family membership comes from the pattern-labeling
taxonomy (13 families, 46 patterns), and per-skill granularity is recovered by
parsing skill roots out of each instance's unified-diff ``patch``.
"""

import collections
import json
import math
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INSTANCES = ROOT / "data" / "analysis" / "instances.jsonl"
TAXONOMY_PATH = ROOT / "skills" / "pattern-labeling" / "taxonomy.json"

# Diff headers are emitted as ``diff --git PATH PATH  [status +a/-d]`` (no a/ b/
# prefixes), so capture the second path and stop before the status bracket.
DIFF_HEADER_RE = re.compile(r"^diff --git (.+?) (.+?)(?:  \[|$)")

# Display order for families, coarsest/most structural first. Families absent
# from this list fall to the end in alphabetical order.
FAMILY_ORDER = [
    "lifecycle", "retarget", "procedure", "decision", "policy", "guardrail",
    "spec", "style", "polish", "resource", "personalize", "script", "fix",
]

# Warm-cool diverging academic palette (see .claude/rules/academic-palettes.md).
PALETTE = [
    "#E76254", "#EF8A47", "#F7AA58", "#FFD06F", "#FFE6B7", "#AADCE0",
    "#72BCD5", "#528FAD", "#376795", "#1E466E",
]
PATTERN_COLOR = "#376795"
ADJUSTED_COLOR = "#E47159"


def load_instances(path: Path = DEFAULT_INSTANCES) -> list[dict]:
    """Read the analysis corpus as a list of instance records."""
    with Path(path).open() as f:
        return [json.loads(line) for line in f if line.strip()]


def load_label_family_map(path: Path = TAXONOMY_PATH) -> dict[str, str]:
    """Map each pattern label to its family name from the pattern taxonomy."""
    taxonomy = json.loads(Path(path).read_text())
    mapping = {}
    for family in taxonomy["families"]:
        for pattern in family["patterns"]:
            mapping[pattern["name"]] = family["name"]
    return mapping


def family_order(families: list[str]) -> list[str]:
    """Sort families by the canonical display order, unknowns alphabetised."""
    rank = {name: i for i, name in enumerate(FAMILY_ORDER)}
    return sorted(families, key=lambda f: (rank.get(f, len(rank)), f))


def family_colors(families: list[str]) -> dict[str, str]:
    """Assign a palette colour to each family in display order, cycling."""
    ordered = family_order(families)
    return {f: PALETTE[i % len(PALETTE)] for i, f in enumerate(ordered)}


def upstream_key(instance: dict) -> str:
    """Upstream repository for an instance (flat string in the current schema)."""
    return instance.get("upstream", "")


def file_paths(patch: str) -> list[str]:
    """Extract the changed file paths from an instance's unified-diff patch."""
    paths = []
    for line in patch.splitlines():
        match = DIFF_HEADER_RE.match(line)
        if match:
            paths.append(match.group(2).strip())
    return paths


def split_patch(patch: str) -> list[dict]:
    """Split a concatenated patch string into per-file ``{path, status, diff}``.

    Each file block starts with ``diff --git PATH PATH  [status +a/-d]``; the
    status word inside the bracket (modified / added / removed / renamed) is the
    file status and the remaining lines until the next header are the file's
    unified diff body. This reconstructs the per-file shape that the legacy
    instances carried as ``instance.patch[]``.
    """
    files = []
    current = None
    for line in patch.splitlines():
        header = DIFF_HEADER_RE.match(line)
        if header:
            if current is not None:
                files.append(current)
            status = ""
            bracket = re.search(r"\[(\w+)", line)
            if bracket:
                status = bracket.group(1)
            current = {"path": header.group(2).strip(), "status": status,
                       "diff": ""}
        elif current is not None:
            current["diff"] += line + "\n"
    if current is not None:
        files.append(current)
    return files


def skill_roots(patch: str) -> set[str]:
    """Recover the set of skill roots touched by an instance.

    A skill root is the directory containing a ``SKILL.md``. Every changed file
    is attributed to the longest ``SKILL.md`` directory that prefixes it. When
    an instance touches no ``SKILL.md`` (e.g. a README-only translation), each
    changed file's parent directory is used as a proxy root so the instance
    still contributes to breadth.
    """
    paths = file_paths(patch)
    skill_dirs = {
        "/".join(p.split("/")[:-1])
        for p in paths
        if p.split("/")[-1] == "SKILL.md"
    }
    roots = set()
    if skill_dirs:
        for p in paths:
            best = None
            for d in skill_dirs:
                prefix = d + "/" if d else ""
                if p.startswith(prefix) and (best is None or len(d) > len(best)):
                    best = d
            roots.add(best if best is not None else "/".join(p.split("/")[:-1]))
    else:
        for p in paths:
            roots.add("/".join(p.split("/")[:-1]) or "(root)")
    roots.discard("")
    return roots


def skill_keys(instance: dict) -> set[tuple[str, str]]:
    """Distinct (upstream, skill_root) pairs an instance contributes."""
    upstream = upstream_key(instance)
    return {(upstream, root) for root in skill_roots(instance.get("patch", ""))}


def file_skill_relative(patch: str) -> list[tuple[str, str]]:
    """Pair each changed file with its path relative to its skill root.

    Mirrors ``skill_roots``: every file is attributed to the longest SKILL.md
    directory that prefixes it, then made relative to that root. Files in an
    instance that touches no SKILL.md are attributed to their parent directory,
    leaving the basename as the relative path.
    """
    paths = file_paths(patch)
    skill_dirs = {
        "/".join(p.split("/")[:-1])
        for p in paths
        if p.split("/")[-1] == "SKILL.md"
    }
    result = []
    for p in paths:
        root = None
        if skill_dirs:
            for d in skill_dirs:
                prefix = d + "/" if d else ""
                if p.startswith(prefix) and (root is None or len(d) > len(root)):
                    root = d
        if root is None:
            root = "/".join(p.split("/")[:-1])
        relative = p[len(root) + 1:] if root and p.startswith(root + "/") else p
        result.append((root, relative))
    return result


FRONTMATTER_FENCE = "---"
# A frontmatter key line (top-level, no indent). The optional ``_\w+`` suffix
# lets ``description`` also match localised variants like ``description_cn``.
TOP_KEY_RE = re.compile(r"^\S+\s*:")


def touches_frontmatter_field(diff: str, field: str) -> bool:
    """Whether a SKILL.md file diff has a +/- line on a frontmatter field.

    Replays the unified diff against frontmatter state: the first ``---`` opens
    the frontmatter block, the next ``---`` closes it. Inside the block we track
    whether the current line belongs to the target ``field:`` key or its
    indented/block value continuation (YAML ``|``/``>`` or wrapped value), and
    return True if any added/removed line lands there. ``field`` matches the bare
    key and localised variants (e.g. ``description`` also matches
    ``description_cn``).
    """
    field_re = re.compile(rf"^\s*{re.escape(field)}(_\w+)?\s*:", re.IGNORECASE)
    in_fm = None  # None=before frontmatter, True=inside, False=after
    in_field = False
    for raw in diff.splitlines():
        if not raw:
            continue
        sign = raw[0] if raw[0] in "+- " else " "
        text = raw[1:] if raw[0] in "+- " else raw
        if text.strip() == FRONTMATTER_FENCE:
            in_fm = True if in_fm is None else False
            in_field = False
            continue
        if in_fm is not True:
            continue
        indent = len(text) - len(text.lstrip())
        if field_re.match(text):
            in_field = True
        elif indent == 0 and TOP_KEY_RE.match(text.lstrip()):
            in_field = False
        # else: an indented/blank line continues the current field's value.
        if in_field and sign in "+-":
            return True
    return False


def upstream_sizes(instances: list[dict]) -> dict[str, int]:
    """Instance count per upstream, used to down-weight dominant repos."""
    return collections.Counter(upstream_key(i) for i in instances)


def prevalence_summary(
    instances: list[dict],
    item_keys,
    instance_sizes: dict[str, int],
) -> dict[str, dict]:
    """Branch-level prevalence, adjusted prevalence, breadth and coverage.

    ``item_keys(instance)`` returns the set of categories (families, patterns,
    surfaces, ...) the instance exhibits. For each category we count:

    - prevalence: instances exhibiting it / analysed instances.
    - adjusted_prevalence: sqrt-of-upstream-size weighting so a single large
      upstream (here obra/superpowers at ~63%) cannot dominate; each instance
      contributes weight ``1/sqrt(size[upstream])`` to numerator and denominator.
    - skill_breadth: distinct (upstream, skill_root) pairs exhibiting it /
      distinct pairs observed.
    - upstream_coverage: distinct upstreams exhibiting it / upstreams observed.
    """
    n = len(instances)
    weights = {u: 1 / math.sqrt(size) for u, size in instance_sizes.items()}
    total_weight = sum(weights[upstream_key(i)] for i in instances)

    all_skills = set()
    for inst in instances:
        all_skills |= skill_keys(inst)
    all_upstreams = {upstream_key(i) for i in instances}

    hits = collections.Counter()
    weighted = collections.defaultdict(float)
    skills_with = collections.defaultdict(set)
    upstreams_with = collections.defaultdict(set)
    for inst in instances:
        cats = item_keys(inst)
        w = weights[upstream_key(inst)]
        sk = skill_keys(inst)
        up = upstream_key(inst)
        for cat in cats:
            hits[cat] += 1
            weighted[cat] += w
            skills_with[cat] |= sk
            upstreams_with[cat].add(up)

    summary = {}
    for cat in hits:
        summary[cat] = {
            "instances": hits[cat],
            "analyzed_instances": n,
            "prevalence": hits[cat] / n if n else 0.0,
            "adjusted_prevalence": (
                weighted[cat] / total_weight if total_weight else 0.0
            ),
            "skills_with": len(skills_with[cat]),
            "observed_skills": len(all_skills),
            "skill_breadth": (
                len(skills_with[cat]) / len(all_skills) if all_skills else 0.0
            ),
            "upstreams_with": len(upstreams_with[cat]),
            "observed_upstreams": len(all_upstreams),
            "upstream_coverage": (
                len(upstreams_with[cat]) / len(all_upstreams)
                if all_upstreams else 0.0
            ),
        }
    return summary
