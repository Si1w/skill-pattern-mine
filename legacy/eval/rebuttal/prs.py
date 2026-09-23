"""Collect public PR associations without equating branch names with snapshots."""

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys

LEGACY = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(LEGACY))
from eval.rebuttal.main import read_jsonl, write_csv


def fetch(repo, output):
    query = '[.[] | {number,created_at,merged_at,closed_at,state,head:{sha:.head.sha,ref:.head.ref,repo:.head.repo.full_name},base:{repo:.base.repo.full_name}}]'
    proc = subprocess.run(["gh", "api", f"repos/{repo}/pulls?state=all&per_page=100", "--paginate", "--jq", query],
                          text=True, capture_output=True, timeout=240)
    if proc.returncode:
        return repo, [], proc.stderr.strip()
    decoder = json.JSONDecoder()
    text, pages = proc.stdout.strip(), []
    while text:
        page, end = decoder.raw_decode(text)
        pages.extend(page)
        text = text[end:].lstrip()
    (output / (repo.replace("/", "-") + ".json")).write_text(json.dumps(pages))
    return repo, pages, None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run_id", required=True)
    parser.add_argument("--offline", action="store_true")
    args = parser.parse_args()
    output = LEGACY / "data/rebuttal" / args.run_id / "prs"
    output.mkdir(parents=True, exist_ok=args.offline)
    rows = read_jsonl(LEGACY / "data/analysis/instances.jsonl")
    mining = {"::".join([r['upstream'], r['fork_owner'], r['fork_branch']]): r for r in read_jsonl(LEGACY / "data/mine/diff_cleaned.jsonl")}
    repos = sorted({r["upstream"] for r in rows})
    if args.offline:
        fetched = [(repo, json.loads((output / (repo.replace("/", "-") + ".json")).read_text()), None) for repo in repos]
    else:
        with ThreadPoolExecutor(max_workers=3) as executor:
            fetched = list(executor.map(lambda repo: fetch(repo, output), repos))
    matches, coverage = [], []
    for repo, prs, error in fetched:
        coverage.append({"upstream": repo, "fetched_prs": len(prs), "error": error})
        for row in [r for r in rows if r["upstream"] == repo]:
            original = mining[row["modification_id"]]
            cutoff = original["fetched_at"]
            cut = datetime.fromisoformat(cutoff)
            owner = original["fork_owner"]
            associated = [pr for pr in prs if pr["head"]["repo"] and
                pr["head"]["repo"].split("/")[0].lower() == owner.lower() and
                pr["head"]["ref"] == original["fork_branch"] and
                datetime.fromisoformat(pr["created_at"].replace("Z", "+00:00")) <= cut]
            exact = [p for p in associated if p["head"]["sha"] == original["head_sha"]]
            merged = [p for p in associated if p["merged_at"] and datetime.fromisoformat(p["merged_at"].replace("Z", "+00:00")) <= cut]
            matches.append({"instance_id": row["modification_id"], "upstream": repo,
                "cutoff": cutoff, "query_succeeded": error is None,
                "branch_associated_prs": len(associated), "exact_head_prs": len(exact),
                "branch_merged_before_cutoff": len(merged),
                "exact_head_merged_before_cutoff": sum(pr in merged for pr in exact),
                "pr_numbers": ";".join(str(p["number"]) for p in associated),
                "limitation": "current PR metadata; branch reuse/deleted heads can obscure historical association"})
    write_csv(output / "associations.csv", matches)
    write_csv(output / "coverage.csv", coverage)
    summary = {"retrieved_at": datetime.now(timezone.utc).isoformat(), "instances": len(rows),
        "repositories_succeeded": sum(r["error"] is None for r in coverage),
        "with_branch_pr_evidence": sum(r["branch_associated_prs"] > 0 for r in matches),
        "with_exact_head_pr": sum(r["exact_head_prs"] > 0 for r in matches),
        "with_branch_merge_evidence": sum(r["branch_merged_before_cutoff"] > 0 for r in matches),
        "with_exact_head_merge_evidence": sum(r["exact_head_merged_before_cutoff"] > 0 for r in matches),
        "inference": "branch-name associations are candidates; exact-head matches are stronger evidence; missing evidence is unresolved"}
    (output / "summary.json").write_text(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
