"""Validate pattern-labeling output(s) against the schema and the taxonomy.

Checks, on top of the Pydantic field schema (schemas.py):
- every label/assignment name exists in the shared taxonomy,
- ``labels`` matches the set of ``label_assignments[].name`` exactly,
- ``taxonomy_version`` matches the taxonomy file,
- every assignment carries at least one evidence item,
- no high-confidence assignment relies solely on commit_message/branch_name
  evidence (high requires direct patch evidence).

Loads the taxonomy via the local ``taxonomy.json`` symlink, which points at the
iter-taxonomy-build taxonomy — the single source of truth for the label
vocabulary.

Usage:
    python skills/pattern-labeling/scripts/validate.py <record.json>
    python skills/pattern-labeling/scripts/validate.py --dir data/label/outputs
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from pydantic import ValidationError
from schemas import LabelRecord

SKILL_DIR = Path(__file__).resolve().parent.parent
TAXONOMY_PATH = SKILL_DIR / "taxonomy.json"


def load_taxonomy(path: Path) -> tuple[str, set[str]]:
    """Return (taxonomy_version, set of valid pattern names)."""
    tax = json.loads(path.read_text())
    names = {
        pat["name"]
        for fam in tax.get("families", [])
        for pat in fam.get("patterns", [])
    }
    return tax["taxonomy_version"], names


def consistency_errors(
    rec: LabelRecord, version: str, names: set[str]
) -> list[str]:
    """Return human-readable consistency errors, or [] if the record is sound."""
    errors: list[str] = []

    if rec.taxonomy_version != version:
        errors.append(
            f"taxonomy_version {rec.taxonomy_version!r} != taxonomy {version!r}"
        )

    assigned = [a.name for a in rec.label_assignments]
    if set(rec.labels) != set(assigned):
        errors.append("labels do not match label_assignments names")
    if len(set(assigned)) != len(assigned):
        errors.append("duplicate label_assignments name")

    for a in rec.label_assignments:
        if a.name not in names:
            errors.append(f"unknown pattern: {a.name!r}")
        if not a.evidence:
            errors.append(f"no evidence for pattern {a.name!r}")
        if a.confidence == "high" and not any(e.type == "patch" for e in a.evidence):
            errors.append(f"high confidence without patch evidence: {a.name!r}")
    return errors


def validate(path: str | Path, version: str, names: set[str]) -> LabelRecord:
    """Load, schema-validate, and consistency-check one label record.

    Raises ``ValueError`` on consistency failure; ``ValidationError`` (pydantic)
    on a schema/field failure.
    """
    rec = LabelRecord.model_validate_json(Path(path).read_text())
    errors = consistency_errors(rec, version, names)
    if errors:
        raise ValueError("label consistency errors:\n  - " + "\n  - ".join(errors))
    return rec


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("path", nargs="?", help="a single label record JSON")
    parser.add_argument("--dir", help="validate every *.json in this directory")
    args = parser.parse_args()

    if not args.path and not args.dir:
        parser.error("provide a record path or --dir")

    version, names = load_taxonomy(TAXONOMY_PATH)
    targets = sorted(Path(args.dir).glob("*.json")) if args.dir else [Path(args.path)]

    bad = 0
    for t in targets:
        try:
            validate(t, version, names)
        except FileNotFoundError:
            print(f"not found: {t}", file=sys.stderr)
            bad += 1
        except (ValidationError, ValueError) as exc:
            print(f"INVALID {t}: {exc}", file=sys.stderr)
            bad += 1
    if bad:
        sys.exit(1)
    print(f"OK: {len(targets)} record(s) valid against {len(names)} taxonomy patterns")


if __name__ == "__main__":
    main()
