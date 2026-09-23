# 0015. GitHub commit timestamps and UTC calendar months

Date: 2026-09-16

## Status

proposed

## Context

The user confirmed committer time and UTC calendar months, and specified that field availability and acquisition must be checked against GitHub's API. Monthly net comparisons in RQ1 to RQ4 need an explicit, reproducible time coordinate. Satisfies: General/Essential "describes in detail what, where, when and how data were collected"; Repository Mining/Essential "describes and justifies measures or metrics used". The [GitHub commit API](https://docs.github.com/en/rest/commits/commits#list-commits) exposes nested commit author/committer dates and parent SHAs.

## Decision

Retrieve commit metadata through `GET /repos/{owner}/{repo}/commits`, starting at the frozen default branch head SHA from ADR 0014 via the `sha` parameter. Preserve both `commit.author.date` and `commit.committer.date`, along with ordered `parents[].sha` and raw responses. Outermost `author` and `committer` objects identify GitHub accounts; they are not the timestamp fields.

Assign source commits to calendar months using `commit.committer.date` converted to UTC, with intervals that include the start and exclude the end `[month_start, next_month_start)`. Preserve the original timestamps that include UTC offsets for traceability. Missing or invalid committer timestamps are explicit extraction failures, never silently replaced by author time, repository `pushed_at`, or retrieval time. Validate membership locally from the returned field; do not equate the API's `since`/`until` filter wording with the study's exact interval semantics. Acquisition must preserve required ancestry preceding the month and record pagination completeness. Neither timestamp sorting nor API response order alone determines lineage endpoints; merge ancestry and handling of nonmonotonic history remain to be specified.

## Alternatives

- **Author time for the primary month**: describes original authorship and can predate the recorded revision after replay; retain it as provenance.
- **Repository push or retrieval time**: does not timestamp each individual historical change.
- **Local Git metadata as the primary acquisition interface**: not the selected metadata source; Git documentation remains useful for field semantics.

## Consequences

- Easier: API field mappings and month membership are explicit; one timezone prevents local offsets from assigning equivalent instants to different months.
- Harder: committer time is embedded commit metadata. It does not record when GitHub received a push or when the default branch adopted a change, and history rewriting can alter it. Pin the API version in run configuration before collection; document these limits when interpreting temporal results.
- If reverted: rebuild monthly instances, labels and measurements. Code locations: `src/domain.py` (`Commit.author_date`, `Commit.committer_date`, `Commit.parent_shas`); planned `configs/skill-pattern-mine.yaml` for API/time settings and `eval/skill-pattern-mine/main.py` for acquisition and UTC grouping.
