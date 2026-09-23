---
name: msg-labeling
description: label the commit messages of how forks modify existing skills to adapt them to new contexts
---

# Commit Message Labeling

Code each skill-adaption instance from **its commit messages alone**, with no access to the patch. Two axes are coded, mirroring the RQ5 commit-message codebook:

- **What** — which skill-modification patterns the messages state or imply, and how the messages express the change.
- **Why** — how the messages express the motivation for the change, plus the stated intentions in free text.

The goal is to measure how much signal commit messages carry on their own. The What pattern labels are scored against the patch-derived consensus (`gt_labels`); the expression categories measure message quality. Predicting from the message alone, blind to the diff, is the point of the experiment, not a limitation to work around.

Every axis is **multi-label**. An instance is the cumulative change of one fork branch, so `msg` is usually several commit messages spanning several distinct modifications. Code the union across all messages: assign every applicable pattern, every applicable What category, and every applicable Why category, rather than collapsing to one dominant label per axis.

## Workflow

### 1. Locate inputs and outputs

- Input: `data/msg/inputs/`, one JSON file per instance. Each file holds:
  - `modification_id`: stable index, e.g. `affaan-m/everything-claude-code::OnlyYC::lyb_config`.
  - `msg`: the list of fork commit messages (already filtered to skill-relevant commits).
- Output: `data/msg/predictions.jsonl`. One line per instance.

### 2. Read the two taxonomies

- `skills/msg-labeling/taxonomy.json` (symlink to the shared skill-modification taxonomy) — the closed vocabulary for `pred_labels`. For every pattern evaluate its `definition` and `decision_rule`.
- `skills/msg-labeling/msg_taxonomy.json` — the closed vocabulary for the What/Why expression categories.

Never invent a label outside these vocabularies.

### 3. Code the What axis

Consider only `msg`.

1. `pred_labels`: assign every skill-modification pattern the messages state or strongly imply. Multi-label is expected; prefer the most specific applicable pattern; use the pattern `name` exactly as in the taxonomy. Assign a label only on positive textual evidence: a message that states *what changed* ("add a review step", "translate to Chinese", "fix the script bug") supports a label; vague messages ("update", "fix", "wip") usually support none. **Empty `pred_labels` is valid and expected** when the messages carry no recoverable pattern signal; do not force a label.
2. `what_expression_categories`: from `msg_taxonomy.json`, assign every What expression category the messages support. Use `missing-what` only when no What information is present.

### 4. Code the Why axis

Still considering only `msg`.

1. `why_expression_categories`: from `msg_taxonomy.json`, assign every Why expression category the messages support. This is multi-label: a branch's messages often state both a problem and a goal (e.g. `describe-skill-issue` and `describe-skill-objective`), so assign all that apply. Use `missing-why` only when no Why information is present, and then only on its own.
2. `why_intentions`: concise free-text summaries of the message-stated motivations, one per distinct intention (e.g. "fix broken command invocation", "adapt the skill to a new client convention"). Multiple intentions are expected when the branch bundles several changes. Emit an empty list when `why_expression_categories` is only `missing-why`.

Do not use the `modification_id` string (repo, owner, branch names) as evidence. Code from the message body only.

### 5. Emit

Write one line per instance to `data/msg/predictions.jsonl` with the fields in the schema below. Copy `modification_id` verbatim from the input. All generated strings must be English.

### 6. Validate

```
uv run python skills/msg-labeling/scripts/validate.py \
    --pred data/msg/predictions.jsonl \
    --gt data/analysis/msg_instances.jsonl
```

This checks every label against its taxonomy, that `message_what_families` equals the families derived from `pred_labels`, the expression-category axes are non-empty and use the missing sentinels correctly, and `modification_id` covers the gt set exactly.

## Schemas

### Prediction record (one JSON object per line)

What axis:

- `modification_id`: the instance index, present in each input file under `data/msg/inputs/`.
- `pred_labels`: skill-modification pattern names inferred from the messages; may be empty.
- `message_what_families`: the taxonomy families of `pred_labels` (the set, derived from the taxonomy); empty when `pred_labels` is empty.
- `what_expression_categories`: non-empty subset of the What categories in `msg_taxonomy.json`; `["missing-what"]` when no What signal.

Why axis:

- `why_expression_categories`: non-empty subset of the Why categories in `msg_taxonomy.json`; `["missing-why"]` when no Why signal.
- `why_intentions`: list of short free-text intentions; empty when Why is only `missing-why`.

Shared:

- `evidence`: short quotes or paraphrases from the messages supporting the What and Why coding.

## References

| File | Description |
| --- | --- |
| `data/msg/inputs/` | Message-only inputs, one JSON per instance (`modification_id`, `msg`). |
| `data/msg/predictions.jsonl` | Coded records produced by this skill. |
| `skills/msg-labeling/taxonomy.json` | Symlink to the shared skill-modification taxonomy; vocabulary for `pred_labels`. |
| `skills/msg-labeling/msg_taxonomy.json` | What/Why expression-category vocabulary. |
| `skills/msg-labeling/scripts/validate.py` | Validate coded records against both taxonomies and the gt set. |
| `src/msg/build_inputs.py` | Builds the gt-free `data/msg/inputs/` from `msg_instances.jsonl`. |
| `src/analysis/build_instances.py` | Builds `msg_instances.jsonl` (`--step msgs`). |
