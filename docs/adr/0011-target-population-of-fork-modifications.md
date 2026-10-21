# 0011. Target population of fork modifications

Date: 2026-09-16

## Status

proposed

## Context

RQ1 to RQ4 use repositories selected by fork counts at retrieval and content, then observe public fork changes to existing skill packages. The user confirmed this restricted population on 2026-09-16. Satisfies: Sampling/Essential "states the theoretical population"; Repository Mining/Essential "discusses threats to external validity". Exact observation dates and monthly denominators remain separate decisions.

## Decision

Limit the conclusions to observable public fork modifications of existing skill packages in repositories retained by ADR 0002. These repositories focus on skills and meet the fork threshold. [ADR 0014](0014-fork-default-branch-only.md) further restricts observation to each fork's default branch history frozen at retrieval, and ADR 0013 defines monthly net outcomes. Describe temporal results within this population selected at retrieval; do not generalize to all skill creation, customization outside forks, other fork branches, or the whole historical skills ecosystem. Retain ADR 0002's main fork threshold and sensitivity analyses, which assess sensitivity to that threshold rather than representativeness of the whole ecosystem.

## Alternatives

- **Whole skills ecosystem**: requires a broader sampling frame and observations of development outside forks; outside the confirmed scope.
- **All packages existing at each historical date**: requires repeated stock observations independent of modification events; not supplied by the current collection design.

## Consequences

- Easier: the retrieval strategy can be retained with explicit claim boundaries; ADR 0013 defines the current observation unit.
- Harder: retrospective selection and unavailable/deleted history remain limitations; report the contributing repositories and pairs of owners and skills over time. This scope does not settle the temporal denominator or inference method.
- If reverted: reconsider retrieval, sampling, and the interpretation of every RQ. Code locations: `src/domain.py` for observation identity and retrieval metadata; planned `configs/skill-pattern-mine.yaml` for the frozen corpus specification, `eval/skill-pattern-mine/main.py` for population accounting, and `README.md` for claim scope and reproduction commands.
