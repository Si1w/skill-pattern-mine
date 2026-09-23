"""Reproduce local rebuttal evidence without changing the submitted artifacts.

Run from the project root with uv run --locked python
legacy/eval/rebuttal/main.py --run_id RUN. A bounded --num_samples pilot is
supported. All inference is descriptive and conditional on the legacy corpus.
"""

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import itertools
import json
import csv
import logging
from pathlib import Path
import random
import statistics
import subprocess
import sys

import yaml

LEGACY = Path(__file__).resolve().parents[2]
ROOT = LEGACY.parent
sys.path.insert(0, str(LEGACY))
from eval.label import utils, rq2, rq3
from eval.audit import metrics
from eval.rebuttal.models import Instance, RunRecord, Settings

logger = logging.getLogger(__name__)


def read_jsonl(path):
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def write_csv(path, rows):
    if not rows:
        return
    with path.open("w") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def owner_root(path, roots):
    parent = path.rsplit("/", 1)[0] if "/" in path else ""
    while parent:
        if parent in roots:
            return parent
        parent = parent.rsplit("/", 1)[0] if "/" in parent else ""
    return "" if "" in roots else None


def relative_path(path, root):
    return path[len(root) + 1:] if root else path


def alpha_binary(left, right, universe):
    """Nominal alpha for two complete coders, with finite rating correction."""
    if len(left) != len(right):
        raise ValueError("Coder lengths differ")
    units = len(left) * len(universe)
    if not units:
        return None
    disagree = sum((lab in a) != (lab in b) for a, b in zip(left, right) for lab in universe)
    positives = sum(lab in labels for labels in left + right for lab in universe)
    ratings = 2 * units
    expected = 2 * positives * (ratings - positives) / (ratings * (ratings - 1))
    return 1 - (disagree / units) / expected if expected else None


def counts_for_groups(rows, keys, item_keys):
    """Retain all branches of each fork together in resampling."""
    groups = defaultdict(lambda: defaultdict(list))
    for row in rows:
        groups[row["upstream"]][row["modification_id"].split("::")[1]].append(item_keys(row))
    return {repo: [(len(items), [sum(key in item for item in items) for key in keys])
                   for items in forks.values()] for repo, forks in sorted(groups.items())}


def quantile(values, probability):
    ordered = sorted(values)
    pos = (len(ordered) - 1) * probability
    lo = int(pos)
    hi = min(lo + 1, len(ordered) - 1)
    return ordered[lo] + (ordered[hi] - ordered[lo]) * (pos - lo)


def bootstrap(rows, families, family_keys, settings):
    groups = counts_for_groups(rows, families, family_keys)
    rng = random.Random(settings.seed)
    estimates = [[] for _ in families]
    for _ in range(settings.bootstrap_repetitions):
        count = 0
        hits = [0] * len(families)
        for forks in groups.values():
            for _ in range(len(forks)):
                size, vector = rng.choice(forks)
                count += size
                for index, value in enumerate(vector):
                    hits[index] += value
        for index in range(len(families)):
            estimates[index].append(hits[index] / count)
    return [{"family": family,
             "prevalence": sum(family in family_keys(r) for r in rows) / len(rows),
             "lower_95": quantile(estimates[i], .025),
             "upper_95": quantile(estimates[i], .975),
             "repetitions": settings.bootstrap_repetitions,
             "scope": "fixed repositories; fork clusters; does not address shared skills"}
            for i, family in enumerate(families)]


def agreement_outputs(out):
    directory = LEGACY / "data/audit"
    files = metrics.find_auditor_files(directory)
    a, b = [metrics.load_verdicts(p) for p in files[:2]]
    consensus = metrics.load_verdicts(directory / "consensus_verdicts.json")
    comparisons = []
    common = sorted(set(a) & set(b))
    comparisons.append(("auditor_a_vs_b", [metrics.final_set(a[r]) for r in common],
                        [metrics.final_set(b[r]) for r in common]))
    for group in ["sample", "low-confidence", "total"]:
        records = sorted(r for r in consensus if group == "total" or consensus[r]["set"] == group)
        comparisons.append((group, [metrics.final_set(consensus[r]) for r in records],
                            [metrics.predicted_set(consensus[r]) for r in records]))
    summaries, detail = [], []
    for name, left, right in comparisons:
        universe = sorted(set.union(set(), *left, *right))
        summary = {"comparison": name, "records": len(left), "observed_labels": len(universe),
                   **metrics.label_set_metrics(left, right),
                   "alpha_finite": alpha_binary(left, right, universe),
                   "exact_set_agreement": sum(a == b for a, b in zip(left, right)) / len(left),
                   "reference": "visible-model audit; not independent gold"}
        summaries.append(summary)
        for label in universe:
            tp = sum(label in a and label in b for a, b in zip(left, right))
            fp = sum(label not in a and label in b for a, b in zip(left, right))
            fn = sum(label in a and label not in b for a, b in zip(left, right))
            detail.append({"comparison": name, "label": label, "tp": tp, "fp": fp, "fn": fn,
                           "precision": tp / (tp + fp) if tp + fp else None,
                           "recall": tp / (tp + fn) if tp + fn else None})
    write_csv(out / "agreement.csv", summaries)
    write_csv(out / "agreement_per_label.csv", detail)
    return summaries


def git_tree(repo, sha):
    git_dir = LEGACY / "data/mine/repos" / (repo.replace("/", "-") + ".git")
    proc = subprocess.run(["git", "--git-dir", str(git_dir), "ls-tree", "-r", "--name-only", sha],
                          capture_output=True, text=True)
    return set(proc.stdout.splitlines()) if proc.returncode == 0 else None


def git_availability(repo, shas):
    git_dir = LEGACY / "data/mine/repos" / (repo.replace("/", "-") + ".git")
    shas = sorted(set(sha for sha in shas if sha))
    proc = subprocess.run(["git", "--git-dir", str(git_dir), "cat-file", "--batch-check=%(objecttype)"],
                          input="\n".join(shas) + "\n", text=True, capture_output=True, check=True)
    return {sha: kind == "commit" for sha, kind in zip(shas, proc.stdout.splitlines())}


def baseline_analysis(rows, inputs, indexed, mining, out):
    """Use complete saved upstream trees; never reconstruct downstream files."""
    trees = {}
    def tree(repo, sha):
        key = (repo, sha)
        if key not in trees:
            trees[key] = git_tree(repo, sha)
        return trees[key]
    package_rows = []
    for entry in indexed:
        repo, sha, skill = entry["repo"], entry["head_sha"], entry["path"]
        root = skill.rsplit("/", 1)[0] if "/" in skill else ""
        paths = tree(repo, sha)
        roots = {p.rsplit("/", 1)[0] if "/" in p else "" for p in paths or [] if p.endswith("/SKILL.md") or p == "SKILL.md"}
        own = [p for p in paths or [] if owner_root(p, roots) == root]
        scripts = [p for p in own if rq2.path_surface(relative_path(p, root)) == "scripts"]
        executable = [p for p in own if Path(p).suffix.lower() in rq2.SCRIPT_SUFFIXES]
        package_rows.append({"upstream": repo, "sha": sha, "skill_root": root,
                             "available": paths is not None and skill in paths,
                             "has_script_surface": bool(scripts), "script_files": len(scripts),
                             "has_script_suffix": bool(executable)})
    write_csv(out / "upstream_script_packages.csv", package_rows)
    opportunities, history, unmapped = [], [], []
    for repo in sorted({r["upstream"] for r in rows}):
        members = [r for r in rows if r["upstream"] == repo]
        heads = git_availability(repo, [mining[r["modification_id"]].get("head_sha") for r in members])
        history.append({"upstream": repo, "instances": len(members), "heads_available": sum(heads.values()),
                        "unique_heads": len(heads)})
        for row in members:
            source = inputs[row["modification_id"]]
            base = mining[row["modification_id"]]["merge_base_sha"]
            paths = tree(repo, base)
            if paths is None:
                continue
            roots = {p.rsplit("/", 1)[0] if "/" in p else "" for p in paths if p.endswith("/SKILL.md") or p == "SKILL.md"}
            changed = defaultdict(list)
            for file in source["files"]:
                root = owner_root(file["filename"], roots)
                if root is not None:
                    changed[root].append(file)
                else:
                    unmapped.append({"instance_id": row["modification_id"], "upstream": repo,
                                     "baseline_sha": base, "path": file["filename"],
                                     "reason": "no ancestor SKILL.md in this baseline tree"})
            for root, files in changed.items():
                scripts = {p for p in paths if owner_root(p, roots) == root and rq2.path_surface(relative_path(p, root)) == "scripts"}
                touched_existing = any(f["filename"] in scripts or f.get("previous_filename") in scripts for f in files)
                new_script = any(f["status"] == "added" and rq2.path_surface(relative_path(f["filename"], root)) == "scripts" for f in files)
                opportunities.append({"instance_id": row["modification_id"], "upstream": repo,
                                      "baseline_sha": base, "skill_root": root,
                                      "has_script_surface": bool(scripts),
                                      "changed_existing_script": touched_existing,
                                      "added_script": new_script})
    write_csv(out / "script_opportunities.csv", opportunities)
    write_csv(out / "history_availability.csv", history)
    write_csv(out / "script_baseline_unmapped.csv", unmapped)
    eligible = [r for r in opportunities if r["has_script_surface"]]
    versions = {(r["upstream"], r["baseline_sha"], r["skill_root"]): r for r in opportunities}
    result = {"indexed_packages": len(package_rows),
              "indexed_packages_available": sum(r["available"] for r in package_rows),
              "indexed_with_scripts": sum(r["has_script_surface"] for r in package_rows),
              "indexed_with_script_suffix": sum(r["has_script_suffix"] for r in package_rows),
              "branch_skill_opportunities": len(opportunities),
              "opportunities_with_scripts": len(eligible),
              "opportunities_changing_existing_scripts": sum(r["changed_existing_script"] for r in eligible),
              "opportunities_adding_scripts": sum(r["added_script"] for r in opportunities),
              "historical_package_versions": len(versions),
              "historical_versions_with_scripts": sum(r["has_script_surface"] for r in versions.values()),
              "local_heads_available": sum(r["heads_available"] for r in history),
              "baseline_trees_available": sum(tree is not None for (repo, sha), tree in trees.items()),
              "baseline_trees_missing": sum(tree is None for tree in trees.values()),
              "instances_mapped_at_baseline": len({r["instance_id"] for r in opportunities})}
    result["unmapped_files"] = len(unmapped)
    result["instances_with_unmapped_files"] = len({r["instance_id"] for r in unmapped})
    write_csv(out / "script_summary_by_repository.csv", [
        {"upstream": repo, "indexed_packages": sum(r["upstream"] == repo for r in package_rows),
         "indexed_with_scripts": sum(r["upstream"] == repo and r["has_script_surface"] for r in package_rows),
         "eligible_opportunities": sum(r["upstream"] == repo for r in eligible),
         "changed_existing_scripts": sum(r["upstream"] == repo and r["changed_existing_script"] for r in eligible)}
        for repo in sorted({r["upstream"] for r in rows})])
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run_id", required=True)
    parser.add_argument("--num_samples", type=int)
    parser.add_argument("--step", choices=["all", "descriptive"], default="all")
    args = parser.parse_args()
    if not args.run_id or Path(args.run_id).name != args.run_id:
        raise ValueError("run_id must be a path component")
    if args.num_samples is not None and args.num_samples < 1:
        raise ValueError("num_samples must be positive")
    settings = Settings.model_validate(yaml.safe_load((LEGACY / "configs/rebuttal.yaml").read_text()))
    out = LEGACY / "data/rebuttal" / args.run_id
    out.mkdir(parents=True, exist_ok=False)
    sources = [LEGACY / "data/analysis/instances.jsonl", LEGACY / "skills/iter-taxonomy-build/taxonomy.json",
               LEGACY / "data/mine/skills_index.jsonl", LEGACY / "data/mine/diff_cleaned.jsonl",
               ROOT / "uv.lock", Path(__file__), LEGACY / "configs/rebuttal.yaml"]
    sources += sorted((LEGACY / "data/audit").glob("*.json"))
    sources += sorted((LEGACY / "data/label/inputs").glob("*.json"))
    sources += sorted((LEGACY / "data/label/outputs").glob("*.json"))
    sources += sorted((LEGACY / "eval/label").glob("*.py"))
    sources += [LEGACY / "eval/audit/metrics.py", LEGACY / "eval/rebuttal/models.py"]
    sources += [LEGACY / "eval/tables-and-figures/rq4-security-matches.csv"]
    record = RunRecord(run_id=args.run_id, started_at=datetime.now(timezone.utc).isoformat(),
                       settings=settings, num_samples=args.num_samples,
                       source_sha256={str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sources})
    (out / "run.json").write_text(record.model_dump_json(indent=2))
    snapshot = out / "source"
    for p in sources:
        if p.suffix == ".py" or p.name in {"rebuttal.yaml", "uv.lock"}:
            target = snapshot / p.relative_to(ROOT)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(p.read_bytes())
    rows = [Instance.model_validate(r).model_dump() for r in read_jsonl(sources[0])]
    if args.num_samples:
        rows = rows[:args.num_samples]
    mapping = utils.load_label_family_map()
    families = sorted(set(mapping.values()))
    family_keys = lambda row: {mapping[label] for label in row["labels"]}
    indexed = read_jsonl(LEGACY / "data/mine/skills_index.jsonl")
    roots = defaultdict(set)
    for item in indexed:
        roots[item["repo"]].add(item["path"].rsplit("/", 1)[0] if "/" in item["path"] else "")
    inputs = {r["modification_id"]: r for p in sorted((LEGACY / "data/label/inputs").glob("*.json")) for r in [json.loads(p.read_text())]}
    mining = {"::".join([r["upstream"], r["fork_owner"], r["fork_branch"]]): r for r in read_jsonl(LEGACY / "data/mine/diff_cleaned.jsonl")}
    aggregation = []
    for row in rows:
        source = inputs[row["modification_id"]]
        skills = {owner_root(f["filename"], roots[row["upstream"]]) for f in source["files"]}
        if None in skills:
            raise ValueError("Unmapped skill path")
        aggregation.append({"instance_id": row["modification_id"], "upstream": row["upstream"],
                            "families": len(family_keys(row)), "skills": len(skills),
                            "retained_commits": len(source["commits"]),
                            "ahead_by_before_cleaning": mining[row["modification_id"]]["ahead_by"]})
    write_csv(out / "aggregation.csv", aggregation)
    by_id = {r["instance_id"]: r for r in aggregation}
    groups = {"all": rows}
    for repo in sorted({r["upstream"] for r in rows}):
        groups["repository:" + repo] = [r for r in rows if r["upstream"] == repo]
        groups["exclude:" + repo] = [r for r in rows if r["upstream"] != repo]
    groups["single_skill"] = [r for r in rows if by_id[r["modification_id"]]["skills"] == 1]
    groups["single_retained_commit"] = [r for r in rows if by_id[r["modification_id"]]["retained_commits"] == 1]
    groups["single_skill_and_retained_commit"] = [r for r in rows if by_id[r["modification_id"]]["skills"] == 1 and by_id[r["modification_id"]]["retained_commits"] == 1]
    all_patterns = sorted(mapping)
    prevalence, surfaces, pairs = [], [], []
    for name, members in groups.items():
        if not members:
            continue
        for kind, keys, function in [("family", families, family_keys), ("pattern", all_patterns, lambda r: set(r["labels"]))]:
            counts = Counter(key for row in members for key in function(row))
            for key in keys:
                prevalence.append({"group": name, "level": kind, "label": key, "count": counts[key],
                                   "n": len(members), "prevalence": counts[key] / len(members)})
        counts = Counter(key for row in members for key in rq2.surface_keys(row))
        for surface in rq2.SURFACE_ORDER:
            surfaces.append({"group": name, "surface": surface, "count": counts[surface],
                             "n": len(members), "prevalence": counts[surface] / len(members)})
        for a, b in itertools.combinations(families, 2):
            hits_a = sum(a in family_keys(r) for r in members)
            hits_b = sum(b in family_keys(r) for r in members)
            joint = sum({a, b} <= family_keys(r) for r in members)
            pairs.append({"group": name, "family_a": a, "family_b": b, "count": joint,
                          "n": len(members), "prevalence": joint / len(members),
                          "lift": joint * len(members) / (hits_a * hits_b) if hits_a * hits_b else None})
    write_csv(out / "prevalence.csv", prevalence)
    write_csv(out / "surfaces.csv", surfaces)
    write_csv(out / "pairs.csv", pairs)
    logger.info("Descriptive results complete; computing conditional fork intervals")
    intervals = bootstrap(rows, families, family_keys, settings)
    write_csv(out / "family_fork_intervals.csv", intervals)
    agreement = agreement_outputs(out)
    original = {}
    for path in sorted((LEGACY / "data/label/outputs").glob("*.json")):
        data = json.loads(path.read_text())
        raw_input = json.loads((LEGACY / "data/label/inputs" / path.name).read_text())
        original[raw_input["modification_id"]] = data["labels"]
    write_csv(out / "consensus_sensitivity.csv", [{"family": family,
        "analysis_hits": sum(family in family_keys(row) for row in rows),
        "original_hits_same_1126": sum(family in {mapping[l] for l in original[row["modification_id"]]} for row in rows),
        "original_hits_all_candidates": sum(family in {mapping[l] for l in labels} for labels in original.values()),
        "analysis_n": len(rows), "candidate_n": len(original)} for family in families])
    with (LEGACY / "eval/tables-and-figures/rq4-security-matches.csv").open() as f:
        matches = list(csv.DictReader(f))
    selected_ids = {r["modification_id"] for r in rows}
    matches = [r for r in matches if r["instance_id"] in selected_ids]
    write_csv(out / "security_by_rule.csv", [{"rule": rule, "matches": len(ms),
        "distinct_lines": len({(r["instance_id"], r["path"], r["patch_line"]) for r in ms}),
        "instances": len({r["instance_id"] for r in ms}), "human_precision": None}
        for rule in sorted({r["rule_id"] for r in matches}) for ms in [[r for r in matches if r["rule_id"] == rule]]])
    positive_ids = {r["instance_id"] for r in matches}
    write_csv(out / "security_by_repository.csv", [{"upstream": repo, "instances": len(rs),
        "positive": sum(r["modification_id"] in positive_ids for r in rs),
        "prevalence": sum(r["modification_id"] in positive_ids for r in rs) / len(rs)}
        for repo in sorted({r["upstream"] for r in rows}) for rs in [[r for r in rows if r["upstream"] == repo]]])
    logger.info("Reading frozen upstream trees for script availability")
    baseline = baseline_analysis(rows, inputs, indexed, mining, out) if args.step == "all" else {}
    summary = {"instances": len(rows), "candidates": len(inputs),
               "single_family": sum(r["families"] == 1 for r in aggregation),
               "multiple_skills": sum(r["skills"] > 1 for r in aggregation),
               "multiple_retained_commits": sum(r["retained_commits"] > 1 for r in aggregation),
               "unique_forks": len({tuple(r["modification_id"].split("::")[:2]) for r in rows}),
               "subset_sizes": {g: len(rs) for g, rs in groups.items()}, "script_baseline": baseline,
               "security_instances": len(positive_ids), "security_rule_matches": len(matches),
               "security_lines": len({(r["instance_id"], r["path"], r["patch_line"]) for r in matches}),
               "agreement": agreement}
    (out / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    record.status = "completed"
    (out / "run.json").write_text(record.model_dump_json(indent=2))
    logger.info("Completed %s", out)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    main()
