---
name: iter-taxonomy-build
description: Iteratively build a taxonomy of skill-modification patterns from a representative sample via grounded-theory open coding.
---

# Iterative Taxonomy Building

Build a two level taxonomy (family -> pattern) of how forks modify existing skills to adapt them to new contexts, by open-coding a representative sample of in-skill adaptation instances until the taxonomy saturates.

## Meta-characteristic

- Classify modifications inside skill directories that change skill-relevant artifacts.
- Primary skill instructions are stored in `SKILL.md`.
- For `SKILL.md` and other instruction documents, use Markdown `#` and `##` sections as the main granularity for modification patterns.
- Include skill-local resources and executable support only when they are bundled with or referenced by a skill.
- Do not label a change solely because a file was added or deleted; the changed file must contain skill-relevant content.

## Workflow

### 1. Initialization

1. Check the existence of `data/label/sample/` directory, otherwise run `uv run python -m label.sample` to create it.
2. Check the existence of `skills/iter-taxonomy-build/taxonomy.json` file, otherwise create an empty taxonomy with the top-level fields `taxonomy_version`, `source`, and an empty `families` list.

### 2. Bootstrap coding (300 representative instances)

Build the initial taxonomy from the full representative sample.

1. Read every instance in `data/label/sample/` (300 instances).
2. Open-code each instance: add new patterns or families to `skills/iter-taxonomy-build/taxonomy.json` following the schema. Ground every pattern in real patch evidence; do not infer from commit messages alone.
3. Cluster and merge similar patterns and families in the taxonomy.
4. Run `uv run python skills/iter-taxonomy-build/scripts/validate.py` to check the taxonomy for consistency and errors.
5. Wait for human feedback and changes to the taxonomy.

### 3. Iteration (50 new instances per batch until saturation)

Extend and validate the taxonomy on instances *outside* the bootstrap sample.
Repeat for each batch:

1. Run `uv run python skills/iter-taxonomy-build/scripts/iter.py --next` to get and claim the next 50 uncoded instances (drawn from `data/label/inputs/`, excluding the bootstrap sample).
2. Open-code each instance: if it contains new patterns or families, add them to the taxonomy following the schema. Ground every pattern in real patch evidence.
3. Cluster and merge similar patterns and families in the taxonomy.
4. Run `uv run python skills/iter-taxonomy-build/scripts/validate.py` to check the taxonomy for consistency and errors.
5. Wait for human feedback and changes to the taxonomy.
6. Stop when the taxonomy saturates: two consecutive batches both produce no new pattern or family.

## Schemas

### Family

For each family, we record the following information:

- `name`: the name of the family, which is a unique string identifier
- `definition`: a description of the family's characteristics
- `patterns`: a list of patterns associated with the family

### Pattern

For each pattern, we record the following information:

- `name`: the name of the pattern, which is a unique string identifier
- `definition`: a description of the pattern's characteristics
- `patch_evidence_required`: a description of the evidence required to apply the pattern
- `decision_rule`: a description of the decision rule for applying the pattern

## References

| File | Description |
| --- | --- |
| `skills/iter-taxonomy-build/taxonomy.json` | The taxonomy file that contains the families and patterns. |
| `skills/iter-taxonomy-build/scripts/schemas.py` | Pydantic models defining the taxonomy structure. |
| `skills/iter-taxonomy-build/scripts/validate.py` | Validate `taxonomy.json` against the schema and consistency rules. |
| `skills/iter-taxonomy-build/scripts/iter.py` | Get and claim the next batch of uncoded instances (`--next` / `--status`). |