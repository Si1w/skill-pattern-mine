# 0023. Use PyDriller for monthly history acquisition

Date: 2026-09-17

## Status

proposed

## Context

The user authorized production integration after the compatibility pilot in ADR 0021. Its adapted reader reproduced the two saved monthly records, while direct modifications missed merge changes. This serves RQ1 to RQ4 and the Repository Mining requirements for documented acquisition and preprocessing. The pilot does not validate attribution accuracy or population performance.

## Decision

Use PyDriller for complete ancestry at frozen commit SHAs and GitPython for complete trees, blobs and path history in monthly extraction. Preserve first parent month boundaries, complete endpoint comparisons, origin checks and sampling semantics. Do not use `modified_files` to detect monthly changes. Repository discovery, fork enumeration, divergence metadata and GitHub identities remain API responsibilities; local commit records leave unavailable account mappings null.

Keep an explicit API reader for comparison and old configurations; new experiment YAML selects `pydriller`. Freeze the selected reader and Git timeout in run settings. Cache local evidence separately from API responses, with repository, frozen head and request identities. Offline replay must never fetch Git objects or silently switch readers. Use temporary bare repositories without checkout; remove them on success and failure while retaining replay evidence and errors. Record reader versions and Git fetch counts. Move the pinned libraries into project dependencies.

## Alternatives

- **Direct PyDriller modifications**: rejected by the merge cases in the pilot.
- **Replace every API operation**: local Git does not supply repository metadata or GitHub account mappings.
- **Discard all acquisition evidence after extraction**: prevents independent offline replay.

## Consequences

Complete object reads preserve merge, binary, mode and cancellation behavior while reducing API history requests. Local evidence uses disk space; full histories may still be expensive. Errors must remain distinguishable from absent changes. Existing frozen runs require their original configuration; migration uses new run IDs. Implementation: `src/git_objects.py`, `src/extract.py`, `src/config.py`, `eval/skill-pattern-mine/main.py`, `pyproject.toml` and `configs/skill-pattern-mine.yaml`; behavioral checks in `tests/test_git_objects.py`, followed by the saved real example through the production entry point.
