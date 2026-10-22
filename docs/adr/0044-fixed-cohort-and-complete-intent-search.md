# 0044. Fixed cohort of thirty and a complete intent search

Date: 2026-10-21

## Status

accepted

## Context

The September candidate run is lost, so the cohort must be reconstructed from a new discovery run (ADR 0027 imports the confirmed repositories from it). The run started on 2026-10-21 showed that the retrieval frame of ADRs 0002 and 0019 is not complete: the two manifest queries stop at the search cap of 1,000 results out of 42,880 and 31,680, and the four intent queries return 85, 83, 57 and 13 repositories because they require a topic containing `skill` or an exact phrase in the description. Three structurally eligible repositories were missed, among them the confirmed `earthtojake/text-to-cad` (description "Give your agent CAD superpowers", no skill topic), so the import would fail. The 30 confirmed repositories had about 148,000 forks together on 2026-10-21, which already makes acquisition a multi day, quota bound job. The user decided on 2026-10-21 to keep the cohort at about 30 repositories.

## Decision

Keep the cohort at the 30 repositories confirmed by ADRs 0025 and 0026. Eligible candidates that a later discovery run surfaces stay pending and are reported with their counts as a limitation of retrospective selection; they are not added without a new ADR.

Drop the sensitivity analysis of ADR 0002 at 500 and 2,000 forks. The user decided on 2026-10-21 that the study counts from 1,000 forks upwards only; the 500 band could only add repositories and the 2,000 band would not change a cohort of this size. `sensitivity_fork_thresholds` is removed from the configuration.

Make the intent channel complete: search `skill in:name,description,topics,readme` from 1,000 forks upwards and split every intent query into fork bands until each band's total count is under the search cap, probing one result per band and splitting in the middle, or at twice the lower bound for the open ended band. Probes on 2026-10-21 returned 1,164 repositories at 1,000 forks or more, which splits into 539 between 1,000 and 1,999 and 625 at 2,000 or more, and found all three missed repositories. Topic queries and the two manifest queries remain as supplementary evidence; a truncated manifest query is recorded as incomplete and no longer prevents the intent channel from being complete.

Record a candidate whose metadata returns HTTP 404 between search and retrieval as unavailable, as ADR 0031 does for forks, instead of failing the discovery run.

## Alternatives

- **Add the missed repositories through `registry_pointers`**: repairs three known cases without making the frame systematic; the next missed repository would stay unknown.
- **One readme query without fork bands**: 1,164 results exceed the cap, so completeness could not be claimed at the main threshold.
- **Fixed bands written in the configuration**: hand tuned to today's counts; a band that grows past the cap would make a later replication incomplete.
- **Keep the sensitivity bands**: the 500 band contradicts the fixed cohort size and would require acquiring forks of every repository between 500 and 999 forks; the user judged the 2,000 band unnecessary.

## Consequences

- Easier: the funnel from a complete intent frame to the 30 confirmed repositories can be reported with counts; the import no longer depends on a ranked slice of code search.
- Harder: the cohort was confirmed on an incomplete frame; candidates with 1,000 forks or more that the complete frame adds must be listed in the paper as unreviewed. The dependence of the results on the fork threshold is no longer tested and must be stated as a limitation.
- If reverted: restore `sensitivity_fork_thresholds: [500, 2000]` and the phrase queries, and rerun discovery under a new run ID. This revises the sensitivity design of ADR 0002 and the query construction of ADR 0019. Implementation: `configs/skill-pattern-mine.yaml`, `src/config.py`, `src/repositories.py` (`fork_bands`), `src/review.py`, and the behavioral tests. A configuration change requires a new candidate run; the run `candidates` of 2026-10-21 is kept as the coverage baseline.
