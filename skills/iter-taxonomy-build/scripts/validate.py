"""Validate a taxonomy.json against the schema and cross-field consistency.

Checks, on top of the Pydantic field schema (schemas.py):
- pattern names are unique across the whole taxonomy,
- family names are unique.

Usage:
    python skills/iter-taxonomy-build/scripts/validate.py
    python skills/iter-taxonomy-build/scripts/validate.py --path <taxonomy.json>
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from pydantic import ValidationError
from schemas import Taxonomy

DEFAULT_PATH = Path("skills/iter-taxonomy-build/taxonomy.json")


def consistency_errors(tax: Taxonomy) -> list[str]:
    """Return human-readable consistency errors, or [] if the taxonomy is sound."""
    errors: list[str] = []

    fam_names = [f.name for f in tax.families]
    if len(set(fam_names)) != len(fam_names):
        errors.append("duplicate family name")

    seen: set[str] = set()
    for fam in tax.families:
        for pat in fam.patterns:
            if pat.name in seen:
                errors.append(f"duplicate pattern name {pat.name!r}")
            seen.add(pat.name)
    return errors


def validate(path: str | Path) -> Taxonomy:
    """Load, schema-validate, and consistency-check a taxonomy file.

    Raises ``ValueError`` on consistency failure; ``ValidationError`` (pydantic)
    on a schema/field failure.
    """
    tax = Taxonomy.model_validate_json(Path(path).read_text())
    errors = consistency_errors(tax)
    if errors:
        raise ValueError("taxonomy consistency errors:\n  - "
                         + "\n  - ".join(errors))
    return tax


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--path", default=DEFAULT_PATH,
                        help=f"taxonomy.json path (default: {DEFAULT_PATH})")
    args = parser.parse_args()
    try:
        tax = validate(args.path)
    except FileNotFoundError:
        print(f"not found: {args.path}", file=sys.stderr)
        sys.exit(1)
    except (ValidationError, ValueError) as exc:
        print(f"INVALID: {exc}", file=sys.stderr)
        sys.exit(1)
    n_pat = sum(len(f.patterns) for f in tax.families)
    print(f"OK: {tax.taxonomy_version} — {len(tax.families)} families, "
          f"{n_pat} patterns")


if __name__ == "__main__":
    main()
