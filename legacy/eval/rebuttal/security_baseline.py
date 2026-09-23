"""Check whether a matched rule already occurs in the corresponding baseline file.

This is a file-context check, not paired package prevalence or risk validation.
"""

import argparse
import csv
import json
from pathlib import Path
import subprocess
import sys

LEGACY = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(LEGACY))
from eval.label import rq4
from eval.rebuttal.main import read_jsonl, write_csv


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run_id", required=True)
    args = parser.parse_args()
    out = LEGACY / "data/rebuttal" / args.run_id / "security_baseline"
    out.mkdir(parents=True, exist_ok=False)
    mining = {"::".join([r["upstream"], r["fork_owner"], r["fork_branch"]]): r for r in read_jsonl(LEGACY / "data/mine/diff_cleaned.jsonl")}
    rules = {r["id"]: r for r in rq4.load_security_rules()}
    cache, rows = {}, []
    with (LEGACY / "eval/tables-and-figures/rq4-security-matches.csv").open() as f:
        matches = list(csv.DictReader(f))
    for match in matches:
        record = mining[match["instance_id"]]
        file = next(f for f in record["files"] if f["filename"] == match["path"])
        path = file.get("previous_filename") or file["filename"]
        key = (record["upstream"], record["merge_base_sha"], path)
        if key not in cache:
            gitdir = LEGACY / "data/mine/repos" / (record["upstream"].replace("/", "-") + ".git")
            proc = subprocess.run(["git", "--git-dir", str(gitdir), "show", record["merge_base_sha"] + ":" + path],
                                  capture_output=True, text=True, errors="replace")
            cache[key] = (proc.returncode == 0, proc.stdout if proc.returncode == 0 else "")
        available, content = cache[key]
        hit_count = sum(rq4.rule_matches_line(line, rules[match["rule_id"]]) for line in content.splitlines()) if available else None
        rows.append({"instance_id": match["instance_id"], "path": match["path"],
                     "patch_line": match["patch_line"], "rule": match["rule_id"],
                     "file_status": file["status"], "baseline_sha": record["merge_base_sha"],
                     "baseline_file_available": available, "same_rule_baseline_lines": hit_count})
    write_csv(out / "matches.csv", rows)
    summary = {"rule_matches": len(rows), "matches_with_baseline_file": sum(r["baseline_file_available"] for r in rows),
               "matches_with_same_rule_already_in_file": sum(bool(r["same_rule_baseline_lines"]) for r in rows),
               "instances_with_same_rule_already_in_file": len({r["instance_id"] for r in rows if r["same_rule_baseline_lines"]}),
               "unavailable_matches_added_files": sum(not r["baseline_file_available"] and r["file_status"] == "added" for r in rows),
               "unavailable_matches_other_files": sum(not r["baseline_file_available"] and r["file_status"] != "added" for r in rows),
               "limitation": "matched file context only; does not establish new risk, same semantic instruction, or paired full-package prevalence"}
    (out / "summary.json").write_text(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
