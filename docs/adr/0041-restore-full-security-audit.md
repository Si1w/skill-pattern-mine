# 0041. Restore the full security audit and preserve completed judgments

Date: 2026-09-25

## Status

accepted

## Context

ADR 0038 extended taxonomy exposure exclusions to security validation without a separate security rationale. The user confirmed that the two tasks assess different constructs and requested restoration of the excluded instances in both the form and rebuttal, retaining completed work and leaving unfinished judgments blank.

## Decision

Audit all 209 detector-positive instances. Preserve the 109 completed tasks, their IDs, line IDs, original A/B judgments and reconciled judgments. Append the other 100 tasks with blank judgments in a new security run, matched through instance identity, path and patch line. Preserve all source exports and historical results. The 293-task taxonomy validation and its exposure exclusions remain unchanged.

Implementation: `legacy/eval/rebuttal/restore_security.py`, `audit_materials.py`, `prepare_collaboration.py`, `security_resume.js`, `legacy/annotation/`, and `Rebuttal.md`. Continuation files live in `legacy/data/rebuttal/security-full-20260925/`. Preserve historical completion flags; the earlier explicit confirmation applies only to the original 109 tasks. Keep their 642-line category distribution identified as partial results; leave the full audit distribution blank until the additional judgments are completed and reconciled.

## Alternatives

- Retain the exclusion: prior taxonomy exposure alone does not justify omitting security evidence.
- Replace or renumber completed tasks: risks losing judgments or associating them with different patches.

## Consequences

The security audit again covers the full positive set. Another 100 instances require human review; missing judgments must not count as benign, negative or agreed. Full results remain pending, and detector recall and confirmed vulnerabilities are not established.
