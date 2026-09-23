# Coauthor annotation for the rebuttal

The rebuttal deadline is September 25, 2026; confirm the exact time and timezone with the corresponding author. Both raters independently annotate the same 293 randomly selected candidates and the same 209 security-positive instances. Neither form includes model predictions or rationales. Coordinator mappings and completed ratings are not part of this package.

## Get the materials

```bash
git clone --branch rebuttal --single-branch https://github.com/Si1w/skill-pattern-mine.git
cd skill-pattern-mine
```

Open [blind.html](blind.html) and [security.html](security.html) from your local checkout in a browser. GitHub's file preview does not run these forms. No Python installation or model account is required. The files are approximately 15 MB and 35 MB; allow the browser time to load them. Use these shared copies for both raters so that credential redaction is identical.

## Work independently

1. Coordinate who uses rater ID `A` and who uses `B`. Each person completes all tasks, rather than splitting the sample between raters.
2. Start with the blind form. Read each patch and select every directly supported taxonomy label. Expand a label to see its definition and decision rule. Record supporting evidence or explain why an empty label set is appropriate.
3. In the security form, assess every highlighted matched line. The card includes eight lines of surrounding context on each side; the complete patch remains available on the left. Use additional context when needed and choose `uncertain` if the prior state cannot be established.
4. Record textual meaning separately from change direction. A guardrail or benign example can match a detector without increasing risk. These judgments do not establish exploitability.
5. Click **Mark this task reviewed**. Export regularly and at the end. Browser storage is not a backup.
6. Keep the two sets of ratings separate until both raters finish. Then preserve the independent exports and coordinate disagreements before consulting the model outputs.

Avoid the existing corpus labels, old audit results, model rationales, coordinator manifests and label-prevalence results during annotation. This repository has historical labeled artifacts, so browsing unrelated data would compromise independence. The fixed taxonomy is allowed in the blind form; this is not independent open coding.

## Return results

Return `blind-A.json`, `blind-B.json`, `security-A.json` and `security-B.json` to the corresponding author through the agreed private channel. Do not post ratings as GitHub issues, pull-request comments or public files before independent annotation and adjudication finish. Exported ratings are ignored by Git to reduce accidental commits. Coauthor repository write access is not necessary to open the forms or export results.

Alongside the exports, state your relevant expertise, prior exposure to the sampled changes or original model answers, and any incomplete tasks. There is known overlap with taxonomy development, so do not describe this as a strictly held-out evaluation. The sample includes candidates excluded from the final analysis and must be completed in the supplied order without cherry-picking.

## Time and evidence limits

There are 293 blind tasks with a median patch length of 184 lines; 59 exceed 1,000 lines. The security form covers 1,521 distinct matched lines across 209 instances. Time the first few tasks and report feasibility early. Unfinished tasks must stay missing, not be recorded as empty label sets or benign judgments. Human annotation is still pending; this package contains no completed judgments.

The sample size targets approximately five percentage points of worst-case sampling precision for one overall binary proportion under simple random sampling from 1,220 candidates. It does not guarantee that rare labels have precise precision or recall. Security tasks cover detector positives only and cannot estimate detector recall.

Credential-shaped strings have been replaced with `<REDACTED_CREDENTIAL>` while task IDs and sample membership remain unchanged. File checksums and task counts are in [package.json](package.json).
