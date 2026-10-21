---
description: This file describes when and how to record an Architecture Decision Record (ADR).
paths:
  - "docs/adr/**"
---

# Architecture Decision Records

## When
- Write an ADR before implementing any decision that is expensive to reverse or changes how results are produced or interpreted (e.g., benchmark, dataset, model, metric, experiment protocol, core dependency, data layout)
- Bug fixes, refactors, and changes that follow existing conventions do not need one
- After a Grill session converges on such a decision, write the ADR first, then implement

## Where
- One file per decision under `docs/adr/`, named `{NNNN}-{kebab-case-title}.md`
- Numbers are sequential and never reused
- Copy `docs/adr/template.md` and fill in every section; keep it under half a page
- Keep experiment design, implementation mappings and unresolved design questions in the ADRs and their index, rather than duplicating them in separate protocol or review documents.
- Use plain English and avoid compound modifiers joined by hyphens when a natural phrase is clearer. Preserve technical identifiers, filenames, commands and URLs.

## Lifecycle
- Status is one of `proposed`, `accepted`, `deprecated`, `superseded by {NNNN}`
- Do not edit an accepted ADR except to change its status; to change a decision, write a new ADR and mark the old one superseded
