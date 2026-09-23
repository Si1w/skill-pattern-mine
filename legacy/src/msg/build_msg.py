"""Build the self-contained data file for the message-only audit UI.

The audit population is every record in ``data/analysis/msg_predictions.jsonl``
(the message-only coding produced by the ``msg-labeling`` skill). Each task
joins the prediction with its matching labeler input in ``data/msg/inputs/`` by
``modification_id``, so the auditor sees the model's What/Why coding next to the
actual commit messages. Inputs are read (not ``msg_instances.jsonl``) so this
path, like the labeler, never touches ``gt_labels``.

This is a *message-only* audit: the left pane shows only the commit messages,
never the diff. The whole point of the experiment is to judge how much signal
the messages carry on their own, so the auditor is blind to the patch exactly
as the coder was. The patch-derived ``gt_labels`` are shown on the right for
reference, since they are already part of the prediction record.

Emits one ``tasks.js`` that ``msg.html`` loads directly via a script tag.

Usage:
    uv run python -m msg.build_msg
"""

import argparse
import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

DEFAULT_PRED = Path("data/analysis/msg_predictions.jsonl")
DEFAULT_INPUTS_DIR = Path("data/msg/inputs")
DEFAULT_TAXONOMY = Path("skills/msg-labeling/taxonomy.json")
DEFAULT_MSG_TAXONOMY = Path("skills/msg-labeling/msg_taxonomy.json")
DEFAULT_OUT = Path("src/msg/tasks.js")


def load_vocabs(taxonomy: Path, msg_taxonomy: Path) -> dict[str, list[str]]:
    """Read the closed vocabularies the auditor can add/remove labels from.

    ``pred_labels`` draw from the skill-modification taxonomy (46 patterns);
    the What/Why expression categories draw from ``msg_taxonomy.json``. Reading
    them here keeps the vocabularies single-sourced — the UI never hardcodes
    them, so they cannot drift from the coding vocabulary.
    """
    tax = json.loads(taxonomy.read_text(encoding="utf-8"))
    patterns = [p["name"] for fam in tax["families"] for p in fam["patterns"]]
    mtax = json.loads(msg_taxonomy.read_text(encoding="utf-8"))
    what = [c["label"] for c in mtax["what_expression_categories"]["allowed"]]
    why = [c["label"] for c in mtax["why_expression_categories"]["allowed"]]
    return {"patterns": patterns, "what": what, "why": why}


def load_jsonl(path: Path) -> list[dict]:
    """Read a JSONL file into a list of records."""
    with path.open(encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def load_inputs(inputs_dir: Path) -> dict[str, dict]:
    """Read every isolated input file, keyed by ``modification_id``."""
    inputs = {}
    for f in inputs_dir.glob("*.json"):
        rec = json.loads(f.read_text(encoding="utf-8"))
        inputs[rec["modification_id"]] = rec
    return inputs


def render_messages(instance_rec: dict) -> str:
    """Render the fork commit messages as one markdown blob.

    Message-only: no diff is included by design.
    """
    parts = ["## Commit messages\n"]
    msgs = instance_rec.get("msg", [])
    if not msgs:
        parts.append("_(no commit messages captured)_")
    for m in msgs:
        parts.append(f"```\n{(m or '').strip()}\n```")
    return "\n\n".join(parts)


def render_pred(pred_rec: dict) -> str:
    """Render the model's What/Why coding as a markdown blob."""
    parts = ["## What axis\n"]

    labels = pred_rec.get("pred_labels", [])
    parts.append("**pred_labels:** " + (", ".join(f"`{x}`" for x in labels) or "_(none)_"))
    fams = pred_rec.get("message_what_families", [])
    parts.append("**families:** " + (", ".join(f"`{x}`" for x in fams) or "_(none)_"))
    what_cats = pred_rec.get("what_expression_categories", [])
    parts.append("**what_expression:** " + (", ".join(f"`{x}`" for x in what_cats) or "_(none)_"))

    parts.append("\n## Why axis\n")
    why_cats = pred_rec.get("why_expression_categories", [])
    parts.append("**why_expression:** " + (", ".join(f"`{x}`" for x in why_cats) or "_(none)_"))
    intentions = pred_rec.get("why_intentions", [])
    if intentions:
        parts.append("**why_intentions:**")
        for it in intentions:
            parts.append(f"- {it}")
    else:
        parts.append("**why_intentions:** _(none)_")

    evidence = (pred_rec.get("evidence") or "").strip()
    if evidence:
        parts.append(f"\n## Evidence\n\n{evidence}")

    # gt_labels (patch-derived consensus) are deliberately NOT rendered: the
    # audit asks the human to judge the message-only coding independently, so
    # showing the patch ground truth would anchor that judgement.
    return "\n\n".join(parts)


def build_tasks(pred_path: Path, inputs_dir: Path) -> list[dict]:
    """Build one task per prediction record, joined to its input by id.

    Ordering follows the prediction file order (same as the input instances).
    """
    inputs = load_inputs(inputs_dir)
    preds = load_jsonl(pred_path)

    tasks = []
    for pred in preds:
        mid = pred["modification_id"]
        inp = inputs.get(mid)
        if inp is None:
            logger.warning("no input for %s — skipping", mid)
            continue
        tasks.append({
            "id": 0,
            "data": {
                "record": mid,
                "pred_labels": ", ".join(pred.get("pred_labels", [])) or "(none)",
                "messages": render_messages(inp),
                "pred": render_pred(pred),
                # Predicted sets per axis, so the audit chips can mark what was
                # predicted and offer the rest of each vocabulary to add.
                "predicted": {
                    "patterns": pred.get("pred_labels", []),
                    "what": pred.get("what_expression_categories", []),
                    "why": pred.get("why_expression_categories", []),
                },
            },
        })
    for i, t in enumerate(tasks, 1):
        t["id"] = i
    return tasks


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pred", default=str(DEFAULT_PRED))
    parser.add_argument("--inputs_dir", default=str(DEFAULT_INPUTS_DIR))
    parser.add_argument("--taxonomy", default=str(DEFAULT_TAXONOMY))
    parser.add_argument("--msg_taxonomy", default=str(DEFAULT_MSG_TAXONOMY))
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    args = parser.parse_args()

    tasks = build_tasks(Path(args.pred), Path(args.inputs_dir))
    vocabs = load_vocabs(Path(args.taxonomy), Path(args.msg_taxonomy))

    # Emit a dictionary keyed by record id for readability, plus an explicit
    # ``order`` list that drives traversal, and the closed vocabularies the
    # audit chips offer, in msg.html.
    payload = {
        "order": [t["data"]["record"] for t in tasks],
        "records": {t["data"]["record"]: t for t in tasks},
        "vocabs": vocabs,
    }
    out_path = Path(args.out)
    out_path.write_text(
        "// Generated by msg.build_msg — do not edit by hand.\n"
        "window.MSG_TASKS = " + json.dumps(payload, ensure_ascii=False, indent=2) + ";\n",
        encoding="utf-8",
    )
    logger.info("wrote %d tasks to %s", len(tasks), out_path)


if __name__ == "__main__":
    main()
