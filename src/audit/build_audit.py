"""Build the self-contained data file for the human-audit UI.

The audit set is the union of the random Cochran sample (``data/audit/sample/``)
and every record whose label output currently carries a label with
``confidence == "low"`` in ``data/label/outputs/``. The two sets overlap, so
records are deduplicated by name.

Each task joins the label output under ``data/label/outputs/`` with its matching
label input (``data/label/inputs/``), so the auditor sees the predicted labels
and rationale next to the actual commit messages and raw diff. Emits one
``tasks.js`` that ``audit.html`` loads directly via a script tag.

Records carrying a low-confidence label are flagged (``has_low``) and sorted
first so the auditor reviews the highest-risk predictions up front.

Usage:
    uv run python -m audit.build_audit
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

DEFAULT_SAMPLE_DIR = Path("data/audit/sample")
DEFAULT_OUTPUTS_DIR = Path("data/label/outputs")
DEFAULT_INPUTS_DIR = Path("data/label/inputs")
DEFAULT_OUT = Path("src/audit/tasks.js")


def render_diff(input_rec: dict) -> str:
    """Render commit messages + per-file patches as one markdown blob."""
    parts = []
    commits = input_rec.get("commits", [])
    if commits:
        parts.append("## Commit messages\n")
        for c in commits:
            msg = (c.get("message") or "").strip()
            parts.append(f"```\n{msg}\n```")
    parts.append("\n## Files\n")
    for f in input_rec.get("files", []):
        head = (f"### `{f.get('filename')}`  "
                f"({f.get('status')}, +{f.get('additions', 0)}/-{f.get('deletions', 0)})")
        parts.append(head)
        if f.get("previous_filename"):
            parts.append(f"_renamed from `{f['previous_filename']}`_")
        patch = f.get("patch") or ""
        if patch.strip():
            parts.append(f"```diff\n{patch}\n```")
        else:
            parts.append("_(empty patch — no diff content captured)_")
    return "\n\n".join(parts)


def render_labels(output_rec: dict) -> tuple[str, bool]:
    """Render the model's labels + rationale as markdown; flag low-confidence."""
    has_low = False
    parts = ["## Model prediction\n"]
    assigns = output_rec.get("label_assignments", [])
    if not assigns:
        parts.append("_(no labels assigned)_")
    for a in assigns:
        conf = a.get("confidence", "?")
        if conf == "low":
            has_low = True
        marker = " ⚠️ LOW" if conf == "low" else ""
        parts.append(f"### `{a.get('name')}` — confidence: **{conf}**{marker}")
        for ev in a.get("evidence", []):
            summ = (ev.get("summary") or "").strip()
            file = ev.get("file")
            parts.append(f"- {summ}" + (f"\n  ↳ `{file}`" if file else ""))
    rationale = (output_rec.get("rationale") or "").strip()
    if rationale:
        parts.append(f"\n## Rationale\n\n{rationale}")
    meta = (f"\n---\n_patch_sufficiency: {output_rec.get('patch_sufficiency')} · "
            f"uninformative_commit_messages: "
            f"{output_rec.get('uninformative_commit_messages')}_")
    parts.append(meta)
    return "\n\n".join(parts), has_low


def audit_record_names(sample_dir: Path, outputs_dir: Path) -> dict[str, str]:
    """Return ``{record_name: set_tag}`` for the union audit population.

    The population is the ``sample`` (all Cochran-drawn records) plus the
    ``low-confidence`` records — those whose label output currently carries at
    least one label assignment with ``confidence == "low"``.

    Tag precedence: a record in the sample is always tagged ``sample``; a
    low-confidence record outside the sample is ``low-confidence``.
    """
    sample_names = {f.name for f in sample_dir.glob("*.json")
                    if f.name != "manifest.json"}

    # Records whose output still carries a low-confidence label assignment.
    low_names = set()
    for f in outputs_dir.glob("*.json"):
        if f.name == "manifest.json":
            continue
        assigns = json.loads(f.read_text()).get("label_assignments", [])
        if any(a.get("confidence") == "low" for a in assigns):
            low_names.add(f.name)

    tags: dict[str, str] = {}
    for name in sample_names:
        tags[name] = "sample"
    for name in low_names - sample_names:
        tags[name] = "low-confidence"
    return tags


def build_tasks(sample_dir: Path, outputs_dir: Path,
                inputs_dir: Path) -> list[dict]:
    """Build one task per record in the union population.

    Ordering: ``low-confidence`` first (highest audit priority), then
    ``sample``; ties broken by name.
    """
    tags = audit_record_names(sample_dir, outputs_dir)
    rank = {"low-confidence": 0, "sample": 1}
    tasks = []
    for name, set_tag in tags.items():
        output_path = outputs_dir / name
        input_path = inputs_dir / name
        if not output_path.exists() or not input_path.exists():
            logger.warning("missing output/input for %s — skipping", name)
            continue
        output_rec = json.loads(output_path.read_text())
        input_rec = json.loads(input_path.read_text())
        labels_md, _ = render_labels(output_rec)
        predicted = [a.get("name") for a in output_rec.get("label_assignments", [])]
        tasks.append({
            "id": 0,
            "data": {
                "record": name,
                "set": set_tag,
                "has_low": set_tag == "low-confidence",
                "upstream": output_rec.get("upstream", ""),
                "fork_owner": output_rec.get("fork_owner", ""),
                "fork_branch": output_rec.get("fork_branch", ""),
                "predicted_labels": ", ".join(predicted) or "(none)",
                "diff": render_diff(input_rec),
                "labels": labels_md,
            },
        })
    tasks.sort(key=lambda t: (rank[t["data"]["set"]], t["data"]["record"]))
    for i, t in enumerate(tasks, 1):
        t["id"] = i
    return tasks


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--sample_dir", default=str(DEFAULT_SAMPLE_DIR))
    parser.add_argument("--outputs_dir", default=str(DEFAULT_OUTPUTS_DIR))
    parser.add_argument("--inputs_dir", default=str(DEFAULT_INPUTS_DIR))
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    args = parser.parse_args()

    tasks = build_tasks(Path(args.sample_dir), Path(args.outputs_dir),
                        Path(args.inputs_dir))
    counts: dict[str, int] = {}
    for t in tasks:
        counts[t["data"]["set"]] = counts.get(t["data"]["set"], 0) + 1

    # Emit a dictionary keyed by record name for readability, plus an explicit
    # ``order`` list (low-confidence first, then sample) that drives traversal
    # in audit.html.
    payload = {
        "order": [t["data"]["record"] for t in tasks],
        "records": {t["data"]["record"]: t for t in tasks},
    }
    out_path = Path(args.out)
    out_path.write_text(
        "// Generated by audit.build_audit — do not edit by hand.\n"
        "window.AUDIT_TASKS = " + json.dumps(payload, ensure_ascii=False, indent=2) + ";\n",
        encoding="utf-8",
    )
    logger.info("wrote %d tasks to %s — sets: %s", len(tasks), out_path, counts)


if __name__ == "__main__":
    main()
