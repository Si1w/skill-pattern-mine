"""Pydantic models for pattern-labeling outputs (one record per instance).

Pure data models only — field types and shape. Cross-field and cross-taxonomy
consistency checks (pattern names must exist in the taxonomy, ``labels`` must
match ``label_assignments``) live in ``validate.py``.

Labels are flat pattern names from the shared taxonomy (``taxonomy.json``, a
symlink to the iter-taxonomy-build taxonomy). Family is not recorded per label;
it is derived from the taxonomy at aggregation time.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

Confidence = Literal["high", "medium", "low"]
PatchSufficiency = Literal["sufficient", "truncated", "empty", "ambiguous"]
EvidenceType = Literal["patch", "file_status", "commit_message", "branch_name"]


class Evidence(BaseModel):
    type: EvidenceType
    summary: str
    file: str | None = None


class LabelAssignment(BaseModel):
    name: str  # pattern name, exactly as in taxonomy.json
    confidence: Confidence
    evidence: list[Evidence]


class TaxonomyUpdate(BaseModel):
    """A proposed new pattern/family surfaced while labelling.

    Recorded here, not written to the taxonomy directly. Taxonomy edits go
    through iter-taxonomy-build.
    """

    name: str
    rationale: str


class LabelRecord(BaseModel):
    # Identity — copied verbatim from the input instance.
    upstream: str
    fork_owner: str
    fork_branch: str

    taxonomy_version: str

    # Pattern names; must match the names in label_assignments.
    labels: list[str]
    label_assignments: list[LabelAssignment]
    taxonomy_updates: list[TaxonomyUpdate] = []

    uninformative_commit_messages: bool = False
    patch_sufficiency: PatchSufficiency = "sufficient"
    input_context: dict
    rationale: str = ""
