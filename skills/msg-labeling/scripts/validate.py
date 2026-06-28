"""Validate message-only coded records against the taxonomies and the gt set.

The message-labeling experiment codes each instance from its commit messages
alone, on two axes (What / Why), and writes one record per instance to a single
JSONL file. Each row carries:

What axis:
- ``modification_id``: the instance index, present in the gt set.
- ``pred_labels``: skill-modification pattern names inferred from the messages;
  may be empty (no recoverable pattern signal).
- ``message_what_families``: the taxonomy families of ``pred_labels``.
- ``what_expression_categories``: subset of the What expression categories.

Why axis:
- ``why_expression_categories``: subset of the Why expression categories.
- ``why_intentions``: short free-text intentions; empty iff Why is only missing.

Shared:
- ``evidence``: short message quotes supporting the coding.

The ground truth (``gt_labels``) lives in ``msg_instances.jsonl``, which the
labeler never reads, so predictions carry no ``gt_labels`` field; the scorer
joins gt back by ``modification_id``.

Checks:
- every ``pred_labels`` name exists in the shared skill-modification taxonomy;
  no duplicates,
- ``message_what_families`` equals the families derived from ``pred_labels``,
- ``what_expression_categories`` / ``why_expression_categories`` are non-empty,
  drawn from the quality taxonomy, and use the ``missing-*`` sentinel alone (a
  missing sentinel must not co-occur with a real category),
- ``why_intentions`` is empty iff ``why_expression_categories`` is only
  ``missing-why``,
- ``modification_id`` is unique and matches the gt set exactly.

Loads both vocabularies from the local symlinked/sibling taxonomy files.

Usage:
    uv run python skills/msg-labeling/scripts/validate.py \\
        --pred data/msg/predictions.jsonl \\
        --gt data/analysis/msg_instances.jsonl
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
TAXONOMY_PATH = SKILL_DIR / "taxonomy.json"
QUALITY_PATH = SKILL_DIR / "msg_taxonomy.json"


def load_taxonomy(path: Path) -> dict[str, str]:
    """Return a pattern-name -> family-name map from the shared taxonomy."""
    tax = json.loads(path.read_text())
    return {
        pat["name"]: fam["name"]
        for fam in tax.get("families", [])
        for pat in fam.get("patterns", [])
    }


def load_quality(path: Path) -> tuple[set[str], str, set[str], str]:
    """Return (what_labels, what_missing, why_labels, why_missing)."""
    q = json.loads(path.read_text())
    what = {c["label"] for c in q["what_expression_categories"]["allowed"]}
    why = {c["label"] for c in q["why_expression_categories"]["allowed"]}
    return what, "missing-what", why, "missing-why"


def load_jsonl(path: Path) -> list[dict]:
    return [json.loads(l) for l in path.read_text().splitlines() if l.strip()]


def _check_axis(mid, field, values, allowed, missing, errors):
    """Validate one expression-category list against its vocabulary."""
    if not isinstance(values, list) or not values:
        errors.append(f"{mid}: {field} must be a non-empty list")
        return
    for v in values:
        if v not in allowed:
            errors.append(f"{mid}: unknown {field} {v!r}")
    if missing in values and len(values) > 1:
        errors.append(f"{mid}: {missing} must stand alone in {field}")


def validate(pred_path: Path, gt_path: Path, p2f: dict[str, str],
             what_allowed, what_missing, why_allowed, why_missing) -> list[str]:
    """Return human-readable errors, or [] if the file is sound."""
    errors: list[str] = []
    preds = load_jsonl(pred_path)
    gt = {r["modification_id"]: r["gt_labels"] for r in load_jsonl(gt_path)}
    names = set(p2f)

    seen: set[str] = set()
    for i, r in enumerate(preds):
        mid = r.get("modification_id")
        if mid is None:
            errors.append(f"row {i}: missing modification_id")
            continue
        if mid in seen:
            errors.append(f"duplicate modification_id: {mid}")
        seen.add(mid)
        if mid not in gt:
            errors.append(f"unknown modification_id (not in gt): {mid}")
            continue

        # What: pattern labels.
        pred = r.get("pred_labels", [])
        if not isinstance(pred, list):
            errors.append(f"{mid}: pred_labels is not a list")
            pred = []
        for name in pred:
            if name not in names:
                errors.append(f"{mid}: unknown pattern {name!r}")
        if len(set(pred)) != len(pred):
            errors.append(f"{mid}: duplicate pred_labels")

        # What: families derived from the predicted patterns.
        want_fams = {p2f[p] for p in pred if p in names}
        got_fams = r.get("message_what_families", [])
        if not isinstance(got_fams, list) or set(got_fams) != want_fams:
            errors.append(
                f"{mid}: message_what_families {sorted(got_fams) if isinstance(got_fams, list) else got_fams} "
                f"!= derived {sorted(want_fams)}"
            )

        # What / Why expression categories.
        _check_axis(mid, "what_expression_categories",
                    r.get("what_expression_categories"), what_allowed, what_missing, errors)
        _check_axis(mid, "why_expression_categories",
                    r.get("why_expression_categories"), why_allowed, why_missing, errors)

        # why_intentions empty iff Why is only missing-why.
        why_cats = r.get("why_expression_categories") or []
        intentions = r.get("why_intentions")
        if not isinstance(intentions, list):
            errors.append(f"{mid}: why_intentions is not a list")
        else:
            only_missing = why_cats == [why_missing]
            if only_missing and intentions:
                errors.append(f"{mid}: why_intentions must be empty when Why is only {why_missing}")
            if not only_missing and not intentions:
                errors.append(f"{mid}: why_intentions empty but Why is not only {why_missing}")

    missing = set(gt) - seen
    if missing:
        errors.append(f"{len(missing)} gt instances have no prediction, e.g. {sorted(missing)[:3]}")
    return errors


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pred", type=Path, default=Path("data/msg/predictions.jsonl"))
    parser.add_argument("--gt", type=Path, default=Path("data/analysis/msg_instances.jsonl"))
    args = parser.parse_args()

    p2f = load_taxonomy(TAXONOMY_PATH)
    what_allowed, what_missing, why_allowed, why_missing = load_quality(QUALITY_PATH)
    errors = validate(args.pred, args.gt, p2f, what_allowed, what_missing, why_allowed, why_missing)
    if errors:
        print("INVALID:\n  - " + "\n  - ".join(errors), file=sys.stderr)
        sys.exit(1)
    n = len(load_jsonl(args.pred))
    print(f"OK: {n} record(s) valid against {len(p2f)} patterns "
          f"+ {len(what_allowed)} What / {len(why_allowed)} Why categories")


if __name__ == "__main__":
    main()
