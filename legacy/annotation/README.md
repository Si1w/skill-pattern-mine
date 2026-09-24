# Coauthor annotation for the rebuttal

The rebuttal deadline is September 25, 2026; confirm the exact time and timezone with the corresponding author. Both raters independently annotate the same 293 randomly selected eligible final instances and the same 109 eligible security-positive instances. Neither form includes model predictions or rationales. Coordinator mappings and completed ratings are not part of this package.

## Current version

Both forms use `human-unseen-v2-20260923`. Run `git pull --ff-only` on the `rebuttal` branch before opening them if you already cloned the repository. Old forms are superseded. Keep any previous exports separately; repeated B/S task IDs do not identify the same records across versions. Browser storage is separated by run ID.

The starting corpus contains 1,126 final instances; 94 of the original 1,220 candidates were excluded after receiving no final labels. We additionally exclude 277 previously audited instances and 280 known taxonomy bootstrap instances, with 69 in both, leaving 638 eligible records. The blind sample selects 293 without replacement (seed 42). Security validation covers all 109 detector-positive instances in that eligible frame, excluding 100 previously exposed positives. Both forms have zero overlap with the saved audit and bootstrap sets.

## Get the materials

```bash
git clone --branch rebuttal --single-branch https://github.com/Si1w/skill-pattern-mine.git
cd skill-pattern-mine
```

Open [blind.html](blind.html) and [security.html](security.html) from your local checkout in a browser. GitHub's file preview does not run these forms. No Python installation or model account is required. Allow the browser time to load these large standalone files. Use these shared copies for both raters so that credential redaction is identical.

## Work independently

The patch viewer colors additions green and deletions red, with original and modified line numbers. Use **Jump to file** or **Previous/Next change** to navigate, **Wrap lines** and **Font** to adjust readability, and **Wider patch** for more space. **Raw patch** shows the exact original text. All context lines are retained; file sections can be collapsed manually. These display controls do not change labels or sampling.

Before refreshing after a viewer update, export a backup. Reopen the same file in the same browser and enter the same rater ID to reload saved judgments. This display update preserves the run ID, task IDs and browser storage keys; it does not migrate ratings from superseded sampling versions.

1. Coordinate who uses rater ID `A` and who uses `B`. Each person completes all tasks, rather than splitting the sample between raters.
2. Start with the blind form. Read each patch and select every directly supported taxonomy label. Expand a label to see its definition and decision rule. Evidence notes are optional; explicitly mark the task reviewed even if no label applies.
3. In the security form, assess every highlighted matched line. The card includes eight lines of surrounding context on each side; the complete patch remains available on the left. Use additional context when needed and choose `uncertain` if the prior state cannot be established.
4. Record textual meaning separately from change direction. A guardrail or benign example can match a detector without increasing risk. These judgments do not establish exploitability.
5. Click **Mark this task reviewed**. Overall evidence and uncertainty notes are optional. Security tasks still require both classifications for every matched line. Export regularly and at the end; exports include saved entries even when their completion flag is false. Browser storage is not a backup.
6. Keep the two sets of ratings separate until both raters finish. Then preserve the independent exports and coordinate disagreements before consulting the model outputs.

Avoid the existing corpus labels, old audit results, model rationales, coordinator manifests and label-prevalence results during annotation. This repository has historical labeled artifacts, so browsing unrelated data would compromise independence. The fixed taxonomy is allowed in the blind form; this is not independent open coding.

## Return results

Return `blind-A.json`, `blind-B.json`, `security-A.json` and `security-B.json` to the corresponding author through the agreed private channel. Do not post ratings as GitHub issues, pull-request comments or public files before independent annotation and adjudication finish. Exported ratings are ignored by Git to reduce accidental commits. Coauthor repository write access is not necessary to open the forms or export results.

Alongside the exports, state your relevant expertise, prior exposure to the sampled changes or original model answers, and any incomplete tasks. Known audit and bootstrap overlap is zero, but later taxonomy iteration membership and unrecorded exposure remain unknown, so do not describe this as a strictly held-out evaluation. All selected records belong to the final analyzed corpus. Complete them in the supplied order without cherry-picking.

## Time and evidence limits

There are 293 blind tasks with a median patch length of 181 lines; 62 exceed 1,000 lines. The security form covers 642 distinct matched lines across 109 instances. Time the first few tasks and report feasibility early. Unfinished tasks must stay missing, not be recorded as empty label sets or benign judgments. Human annotation is still pending; this package contains no completed judgments.

For one binary proportion within the 638 eligible records, a sample of 293 has approximately 4.2 percentage points of worst-case 95% sampling precision under simple random sampling with finite-population correction. This does not establish representativeness of all 1,126 analyzed instances or validate the 94 zero-label exclusions. It does not guarantee that rare labels have precise precision or recall. Security tasks cover eligible detector positives only; results cannot represent all 209 original positives or estimate detector recall.

Credential-shaped strings have been replaced with `<REDACTED_CREDENTIAL>` while task IDs and sample membership remain unchanged. File checksums and task counts are in [package.json](package.json).
