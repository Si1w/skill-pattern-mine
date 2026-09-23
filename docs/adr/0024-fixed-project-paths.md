# 0024. Fixed project paths

Date: 2026-09-22

## Status

accepted

## Context

Repository directories are implementation conventions rather than experiment parameters. Keeping them in YAML adds unused configuration and couples frozen experiment settings to file locations.

## Decision

Define default paths in the entry points relative to the project root derived from `__file__`. Remove acquisition output directories and pilot file paths from YAML; retain pilot `--input` and `--output` options to select observations and preserve separate results. Keep the existing data layout and refuse to overwrite pilot results.

Read historical configuration snapshots by discarding only the retired `outputs` field before normal validation. Keep new YAML validation strict and preserve all experiment settings and existing artifact files.

## Alternatives

- Keep paths in YAML: mixes storage conventions with experiment parameters.
- Use absolute machine paths: prevents moving the checkout between machines.

## Consequences

- Easier: fewer configuration fields and stable defaults regardless of the working directory.
- Harder: changing the acquisition directory requires editing its entry point.
- If reverted: restore YAML path fields and their validation. Implementation affects `src/config.py`, snapshot readers, both evaluation entry points, configs, and behavioral tests.
