---
name: pattern-labeling
description: "label the patterns of how forks modify existing skills to adapt them to new contexts"
---

# Pattern Labeling

Classify each skill adaption instance against the shared taxonomy (family -> pattern) and produce one validated label record per instance, grounded in real patch evidence.

## Workflow

### 1. Locate inputs and outputs

- Inputs: one self-contained instance per file under `data/label/inputs/` (`<stem>.json`).
- Outputs: write one label record per instance to `data/label/outputs/<stem>.json`, reusing the input stem. Create the directory if it does not exist.

### 2. Determine scope

1. Separate skill changes from maintenance changes.
2. Keep bundled references, templates, scripts, configs, examples, and assets only when they support a skill.

### 3. Gather evidence

Evidence priority, highest first:

1. patch
2. file status
3. file content
4. file path
5. commit message
6. branch name

Patch evidence is authoritative. Never assign a label from a branch name alone.

### 4. Match labels

For every candidate pattern in `taxonomy.json`, evaluate its `decision_rule` and `patch_evidence_required`.

1. Assign every label directly supported by evidence; multi-label assignment is expected.
2. Prefer the most specific applicable pattern.
3. Record each label by its pattern `name`, exactly as it appears in the taxonomy. Family is not recorded per label; it is derived from the taxonomy at aggregation time.
4. If no pattern applies, emit an empty `labels` and `label_assignments` and explain why in `rationale` (e.g. the change is purely maintenance). Do not force a label to avoid an empty record.

### 5. Assign confidence

| confidence | criteria                                            |
| ---------- | --------------------------------------------------- |
| high       | direct patch evidence, low ambiguity                |
| medium     | supported but partially ambiguous                   |
| low        | weak, indirect, truncated, or commit-message-driven |

Never assign `high` without direct patch evidence.

### 6. Determine patch sufficiency

Use one value: `sufficient`, `truncated`, `empty`, or `ambiguous`. Use `truncated` only when patch content is unavailable for oversized files.

### 7. Emit and validate

1. Write one label record to `data/label/outputs/<stem>.json` per instance, copying the identity fields (`upstream`, `fork_owner`, `fork_branch`, `input_context`) verbatim from the input instance. Set `taxonomy_version` to the value in `taxonomy.json`. Never reconstruct values from filenames. All generated strings must be English.
2. Run `uv run python skills/pattern-labeling/scripts/validate.py --dir data/label/outputs` to check records against the schema and the taxonomy.

## Schemas

### Label record

For each instance, we record:

- `upstream`, `fork_owner`, `fork_branch`, `input_context`: identity fields copied verbatim from the input instance.
- `taxonomy_version`: the version string from `taxonomy.json`.
- `labels`: the list of assigned pattern names; must equal the set of `label_assignments[].name`. May be empty when no pattern applies.
- `label_assignments`: a list of assigned labels (see below).
- `taxonomy_updates`: candidate new patterns surfaced while labelling; advisory only.
- `uninformative_commit_messages`: `true` when commit messages add no signal.
- `patch_sufficiency`: `sufficient` | `truncated` | `empty` | `ambiguous`.
- `rationale`: a concise overall justification.

### Label assignment

For each assigned label, we record:

- `name`: the taxonomy pattern name, exactly as in `taxonomy.json`.
- `confidence`: `high` | `medium` | `low`.
- `evidence`: a non-empty list of evidence items, each with `type` (`patch` | `file_status` | `commit_message` | `branch_name`), a concise `summary`, and an optional `file`. Avoid speculation. A `high` assignment requires at least one `patch` evidence item.

## References

| File | Description |
| --- | --- |
| `data/label/inputs/` | Label-input instances (`<stem>.json`). |
| `data/label/outputs/` | Label records produced by this skill (`<stem>.json`). |
| `skills/pattern-labeling/taxonomy.json` | Symlink to the iter-taxonomy-build taxonomy; the read-only label vocabulary. |
| `skills/pattern-labeling/scripts/schemas.py` | Pydantic models defining the label record structure. |
| `skills/pattern-labeling/scripts/validate.py` | Validate label record(s) against the schema and the taxonomy (`<record.json>` / `--dir`). |
