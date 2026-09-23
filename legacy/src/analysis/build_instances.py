"""Build the analysis instance set from label outputs and consensus verdicts.

Iterates over every label output (``data/label/outputs/<record>``) and assigns
each record its final labels:

- For the audited records covered by the consensus verdicts
  (``data/audit/consensus_verdicts.json``), the model prediction is replaced
  with the consensus *final* labels::

      final = predicted - removed + added

- For the remaining (un-audited) records, the model's original ``labels`` are
  used as-is.

Each record is joined back to its label input (``data/label/inputs/<record>``)
to recover the commit messages and unified diff that the label was derived from.
Commit messages are filtered with the same ``mine.s06_clean.filter_skill_commits``
used at labeling time, so they match what was actually shown to the labeler.

Instances whose final label set is empty are dropped: a zero-label modification
carries no pattern signal for downstream analysis.

One JSON object per line is written to ``data/analysis/instances.jsonl`` with
fields::

    modification_id   stable id, e.g. "affaan-m/everything-claude-code::OnlyYC::lyb_config"
    upstream          source repository
    commit_messages   filtered fork commit messages (skill-relevant intent only)
    patch             concatenated unified diff across changed files
    labels            final labels (consensus where audited, else model output)

A second step writes ``data/analysis/msg_instances.jsonl``: the consensus-audited
subset (277 records with non-empty labels), each row keyed by ``modification_id``
and carrying only ``msg`` (commit messages) and ``gt_labels`` (consensus labels),
for the commit-message-only classification experiment.

Usage:
    uv run python -m analysis.build_instances                 # all steps
    uv run python -m analysis.build_instances --step instances
    uv run python -m analysis.build_instances --step msgs
    uv run python -m analysis.build_instances --step msg-preds  # RQ5 input
"""

import argparse
import json
import logging
from pathlib import Path

from mine.s06_clean import filter_skill_commits

logger = logging.getLogger(__name__)
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

DEFAULT_CONSENSUS = Path("data/audit/consensus_verdicts.json")
DEFAULT_OUTPUTS = Path("data/label/outputs")
DEFAULT_INPUTS = Path("data/label/inputs")
DEFAULT_OUT = Path("data/analysis/instances.jsonl")
DEFAULT_MSG_OUT = Path("data/analysis/msg_instances.jsonl")
DEFAULT_MSG_CONSENSUS = Path("data/msg/consensus_verdicts.json")
DEFAULT_MSG_PRED = Path("data/msg/predictions.jsonl")
DEFAULT_MSG_PRED_OUT = Path("data/analysis/msg_predictions.jsonl")


def split_predicted(field: str) -> list[str]:
    """Parse the comma-joined ``predicted_labels`` string into a list."""
    if not field or field == "(none)":
        return []
    return [s.strip() for s in field.split(",") if s.strip()]


def final_labels(verdict: dict) -> list[str]:
    """Consensus final labels: predicted minus removed plus added.

    Preserves the predicted order, then appends added labels in their given
    order, so the result is deterministic rather than set-ordered.
    """
    predicted = split_predicted(verdict.get("predicted_labels", ""))
    # The patch-audit verdicts use ``remove_labels``/``add_labels``; the
    # message-audit (RQ5) verdicts use the axis-scoped ``*_pred_labels`` names.
    removed = set(verdict.get("remove_labels") or verdict.get("remove_pred_labels") or [])
    added = verdict.get("add_labels") or verdict.get("add_pred_labels") or []
    kept = [p for p in predicted if p not in removed]
    for a in added:
        if a not in kept:
            kept.append(a)
    return kept


def build_patch(files: list[dict]) -> str:
    """Concatenate per-file unified diffs into one patch blob.

    Each file is prefixed with a ``diff --git``-style header carrying its status
    and add/del counts; files with an empty patch body (pure renames/deletions
    with no hunk) still contribute a header so the change is visible.
    """
    blocks = []
    for f in files:
        name = f.get("filename", "")
        prev = f.get("previous_filename")
        status = f.get("status", "")
        adds, dels = f.get("additions", 0), f.get("deletions", 0)
        header = f"diff --git {prev or name} {name}  [{status} +{adds}/-{dels}]"
        body = f.get("patch") or ""
        blocks.append(header + ("\n" + body if body else ""))
    return "\n".join(blocks)


def build(consensus_path: Path, outputs_dir: Path, inputs_dir: Path, out_path: Path) -> None:
    verdicts = json.loads(consensus_path.read_text())["verdicts"]
    consensus = {v["record"]: final_labels(v) for v in verdicts}
    logger.info("loaded %d consensus verdicts from %s", len(consensus), consensus_path)

    out_files = sorted(outputs_dir.glob("*.json"))
    logger.info("found %d label outputs in %s", len(out_files), outputs_dir)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    dropped_zero = missing = 0

    # Branch dedup already happened in mine.s06_clean, so every label output here
    # is one row per line of work; this only joins labels back to inputs.
    instances: list[dict] = []
    for out_file in out_files:
        record = out_file.name
        # Consensus labels override the model output where the record was
        # audited; otherwise keep the model's original labels.
        if record in consensus:
            labels = consensus[record]
        else:
            labels = json.loads(out_file.read_text()).get("labels") or []
        if not labels:
            dropped_zero += 1
            continue

        in_file = inputs_dir / record
        if not in_file.exists():
            logger.warning("no input file for record %s; skipping", record)
            missing += 1
            continue
        row = json.loads(in_file.read_text())

        commits = filter_skill_commits(row.get("commits", []))
        instances.append({
            "modification_id": row["modification_id"],
            "upstream": row["upstream"],
            "commit_messages": [c.get("message", "") for c in commits],
            "patch": build_patch(row.get("files", [])),
            "labels": labels,
        })

    with out_path.open("w") as fh:
        for inst in instances:
            fh.write(json.dumps(inst, ensure_ascii=False) + "\n")

    logger.info(
        "wrote %d instances to %s (dropped %d zero-label, %d missing input)",
        len(instances), out_path, dropped_zero, missing,
    )


def build_msgs(consensus_path: Path, inputs_dir: Path, instances_path: Path, out_path: Path) -> None:
    """Build the commit-message-only evaluation set for the audited subset.

    For every consensus-audited record with a non-empty final label set, emit one
    row keyed by ``modification_id`` carrying only the commit messages and the
    consensus labels as ground truth. This is the input for the message-only
    classification experiment: an agent predicts taxonomy labels from ``msg``
    alone and is scored against ``gt_labels`` (the patch-derived consensus).

    Messages are taken from ``instances.jsonl`` so they stay identical to the
    full instance set (same ``filter_skill_commits`` filtering, single source of
    truth). The consensus record filename is mapped to its ``modification_id``
    via the matching input file. Run the ``instances`` step first.
    """
    by_id = {json.loads(l)["modification_id"]: json.loads(l)
             for l in instances_path.read_text().splitlines() if l.strip()}

    verdicts = json.loads(consensus_path.read_text())["verdicts"]
    out_path.parent.mkdir(parents=True, exist_ok=True)
    written = dropped_zero = missing = 0

    with out_path.open("w") as fh:
        for v in verdicts:
            labels = final_labels(v)
            if not labels:
                dropped_zero += 1
                continue
            mod_id = json.loads((inputs_dir / v["record"]).read_text())["modification_id"]
            inst = by_id.get(mod_id)
            if inst is None:
                missing += 1
                logger.warning("no instance row for %s; run the instances step first", mod_id)
                continue
            fh.write(json.dumps({
                "modification_id": mod_id,
                "msg": inst["commit_messages"],
                "gt_labels": labels,
            }, ensure_ascii=False) + "\n")
            written += 1

    logger.info(
        "wrote %d msg-instances to %s (dropped %d zero-label, %d missing)",
        written, out_path, dropped_zero, missing,
    )


def build_msg_preds(pred_path: Path, msg_consensus_path: Path,
                    instances_path: Path, out_path: Path) -> None:
    """Build the RQ5 message-prediction set scored against patch ground truth.

    Joins three per-record sources keyed by ``modification_id``:

    - ``predictions.jsonl``: the message-only coding (What/Why expression
      categories, families) the agent derived from ``msg`` alone.
    - ``msg/consensus_verdicts.json``: the two-auditor consensus, whose final
      label set (predicted minus removed plus added) is the audited
      ``pred_labels``.
    - ``msg_instances.jsonl``: the patch-derived consensus ``gt_labels`` that
      RQ5 scores against.

    Emits one row per prediction with ``pred_labels`` (audited),
    ``message_what_families``, ``what_expression_categories``,
    ``why_expression_categories`` and ``gt_labels``. Run the ``msgs`` step first
    so ``gt_labels`` are available.
    """
    preds = {json.loads(l)["modification_id"]: json.loads(l)
             for l in pred_path.read_text().splitlines() if l.strip()}
    audited = {v["record"]: final_labels(v)
               for v in json.loads(msg_consensus_path.read_text())["verdicts"]}
    gt = {json.loads(l)["modification_id"]: json.loads(l)["gt_labels"]
          for l in instances_path.read_text().splitlines() if l.strip()}

    out_path.parent.mkdir(parents=True, exist_ok=True)
    written = missing = 0
    with out_path.open("w") as fh:
        for mid, pred in preds.items():
            if mid not in gt:
                missing += 1
                logger.warning("no gt_labels for %s; run the msgs step first", mid)
                continue
            fh.write(json.dumps({
                "modification_id": mid,
                "pred_labels": audited.get(mid, pred.get("pred_labels", [])),
                "message_what_families": pred.get("message_what_families", []),
                "what_expression_categories": pred.get("what_expression_categories", []),
                "why_expression_categories": pred.get("why_expression_categories", []),
                "gt_labels": gt[mid],
            }, ensure_ascii=False) + "\n")
            written += 1

    logger.info("wrote %d msg-predictions to %s (%d missing gt)",
                written, out_path, missing)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--step", choices=["all", "instances", "msgs", "msg-preds"], default="all")
    parser.add_argument("--consensus", type=Path, default=DEFAULT_CONSENSUS)
    parser.add_argument("--outputs", type=Path, default=DEFAULT_OUTPUTS)
    parser.add_argument("--inputs", type=Path, default=DEFAULT_INPUTS)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--msg-out", type=Path, default=DEFAULT_MSG_OUT)
    parser.add_argument("--msg-consensus", type=Path, default=DEFAULT_MSG_CONSENSUS)
    parser.add_argument("--msg-pred", type=Path, default=DEFAULT_MSG_PRED)
    parser.add_argument("--msg-pred-out", type=Path, default=DEFAULT_MSG_PRED_OUT)
    args = parser.parse_args()

    if args.step in ("all", "instances"):
        build(args.consensus, args.outputs, args.inputs, args.out)
    if args.step in ("all", "msgs"):
        build_msgs(args.consensus, args.inputs, args.out, args.msg_out)
    if args.step in ("all", "msg-preds"):
        build_msg_preds(args.msg_pred, args.msg_consensus, args.msg_out,
                        args.msg_pred_out)


if __name__ == "__main__":
    main()
