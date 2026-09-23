"""Pydantic models for the skill-modification taxonomy (family -> pattern).

Pure data models only — field types and shape. Cross-field consistency checks
(unique family and pattern names) live in ``validate.py``.
"""

from __future__ import annotations

from pydantic import BaseModel


class Pattern(BaseModel):
    name: str
    definition: str
    patch_evidence_required: str
    decision_rule: str


class Family(BaseModel):
    name: str
    definition: str
    patterns: list[Pattern]


class Taxonomy(BaseModel):
    taxonomy_version: str
    source: str
    families: list[Family]
