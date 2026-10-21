# 0017. Package file ratio over all tracked files

Date: 2026-09-16

## Status

proposed

## Context

The user confirmed the ratio of tracked files inside skill packages to all tracked files in the repository, including Markdown, and delegated routine implementation choices. The previous denominator excluded documentation that could still appear in the numerator. Satisfies: Repository Mining/Essential "describes and justifies measures or metrics used" and "describes data preprocessing steps". This refines ADR 0002; it does not select the calibration threshold.

## Decision

At the frozen upstream default branch tree, count every distinct tracked blob path once, including Markdown, source, binary, executable and symlink entries. Directories and submodule references are not files in this repository's tree and are not counted or traversed as external repositories. A package root is the directory containing a regular or executable file named exactly `SKILL.md`; a symlink does not establish a package root. A `SKILL.md` at the repository root makes the repository root a package. The numerator is the union of blob paths under these roots, so nested packages do not count files more than once. Compare directory components rather than bare string prefixes.

Persist numerator, denominator, discovered roots and their ratio. An empty tree has an undefined ratio. An incomplete or truncated tree must not produce a ratio: expand the remaining subtrees or report extraction failure. Calibrate and validate the inclusion threshold as required by ADR 0002; do not invent a cutoff. GitHub documents blob/tree/commit entries and recovery of truncated trees in its [tree API](https://docs.github.com/en/rest/git/trees#get-a-tree).

## Alternatives

- **Exclude documentation only from the denominator**: permits inconsistent ratios and penalizes packages centered on documentation unpredictably.
- **Count bytes or only selected source extensions**: changes the approved measure based on file counts and adds weighting decisions.
- **Count each nested package separately and sum**: counts the same tracked file multiple times.

## Consequences

Implementation flow: preserve the frozen tree and raw API responses; finish pagination and expand truncated trees before measurement; map entries to `TreeEntry`; compute `SkillCentricity`; then apply the calibrated threshold and record screening completion. Conflicting entries at one path fail validation. An unset threshold must not silently become a default. The collector and threshold application are planned; the metric is implemented and covered by 11 tests in `tests/test_preprocess.py`.

- Easier: the ratio is bounded and reproducible without content classification for each language.
- Harder: large asset trees affect the count and manifests at the repository root yield a ratio of one. Human calibration and aggregator screening remain necessary; this metric alone does not establish repository intent.
- If reverted: rerun screening, calibration and downstream corpus construction. Code locations: `src/domain.py` (`TreeEntry`, `SkillCentricity`, `Repository`), `src/preprocess.py`, `tests/test_preprocess.py`; `configs/skill-pattern-mine.yaml` records the approved metric and unresolved calibrated threshold.
