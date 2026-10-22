# 0043. Record repository exclusions outside the configuration

Date: 2026-10-21

## Status

accepted

## Context

ADR 0042 made `screening.repositories` a plain list of the 30 confirmed repositories, so the experiment configuration no longer carries exclusion reasons. ADR 0025 refers to "four confirmed exclusions" without naming them, and the exclusion of `affaan-m/everything-claude-code`, which the submitted study had used as an upstream, was never written down. The September candidate run that held this evidence no longer exists.

## Decision

Keep every human exclusion of a structurally eligible candidate in this ADR or its successors, with the date and reason. The recorded exclusions are:

- `ComposioHQ/awesome-claude-skills`, 2026-09-16: a collection of skills from other repositories (ADR 0022).
- `github/awesome-copilot`, 2026-09-17: a mixed collection of agents, instructions, skills and hooks.
- `wshobson/agents`, 2026-09-17: a mixed collection of agents, commands and skills.
- `teng-lin/notebooklm-py`, 2026-09-17: an SDK and CLI repository with a skill interface.
- `tt-a1i/archify`, 2026-09-22: a complete diagram tool with a skill interface (ADR 0026).
- `affaan-m/everything-claude-code`, now `affaan-m/ECC`, confirmed by the user on 2026-10-21: the same skill packages exist at overlapping paths inside one repository. At head `90606c8315ee09cafc303515c5f33024db6b9882` the tree holds 1,062 `SKILL.md` files under 314 distinct package names; 265 names appear at more than one path, mainly `skills/`, translated copies under `docs/{language}/skills/` and host specific copies under `.agents/`, `.kiro/`, `.cursor/` and `pi/core/`. Only 26 names have byte identical copies, so the copies are translations and adaptations rather than mirrors. Package identity by path (ADR 0020) would count one change several times or miss its propagation between copies, and translation handling is unresolved. The repository is excluded for this methodological reason; it is not classified as an aggregator, and no overlap of package names with the confirmed upstreams was found.

`mattpocock/skills` is not excluded. It carries 38 `SKILL.md` manifests and both plugin manifests under `.claude-plugin/`, so it passes the structural rules; its absence from the September review is a discovery coverage question that the next candidate run must answer before membership is revisited.

## Alternatives

- **Keep reasons in the configuration**: rejected by the user on 2026-10-21; the configuration lists only the cohort while the run artifacts keep the measured evidence.
- **Keep reasons only in the review worksheet**: the worksheet is a run artifact outside version control and was lost once already.

## Consequences

- Easier: the selection funnel can be reported from the candidate run plus this list; ADR 0025's unnamed exclusions are now explicit.
- Harder: overlapping package copies inside one repository are a new exclusion ground; any confirmed repository that later shows the same layout needs the same review.
- If reverted: move the reasons back into the configuration schema and `src/config.py`. Implementation: `configs/skill-pattern-mine.yaml` comment, `docs/adr/README.md`.
