# Execution Prompt — Ticket 002: JSON Schema, Examples, and Validator

You are a coding agent in Codex CLI. Plan–execute–verify until all acceptance checks pass.

## Critical Rules (repeat)
- Persist; read first; small, focused diffs. Determinism and atomic writes.
- No network beyond Python deps if needed; no secrets.
- Follow AGENTS.md style; explicit errors and logs.

## Environment & Tools
- Agent context: Codex CLI
- Tools: plan, shell, apply_patch, pytest
- Approvals: never; Network: enabled; Filesystem: full

## Branching
- Base: main
- Create: `feat/gpt5-002-schema-and-validator`

## Goal
- Materialize the Statistical Analysis Report JSON Schema v1.0.x from the plan, add abridged success and error examples, and a Python validator with tests.

## Scope
- Add `schemas/replay_report.schema.json` (Draft‑07) mirroring section 3 of the plan.
- Add examples: `examples/replay_report.success.json`, `examples/replay_report.error.json` (abridged but valid per schema).
- Add `src/rlcoach/schema.py` with `validate_report(obj) -> None` raising clear errors.
- Tests validating examples against the schema.

## Out of Scope
- Parser, analyzers, or generators; only schema + validation utilities.

## Primary Files to Modify or Add
- `schemas/replay_report.schema.json` — formal schema
- `examples/replay_report.success.json` — abridged valid example
- `examples/replay_report.error.json` — exact error contract example
- `src/rlcoach/schema.py` — `validate_report`
- `tests/test_schema_validation.py` — tests for both examples

## Implementation Plan
1) Transcribe schema properties/definitions faithfully from the plan; set `schema_version` pattern `^1\.0\.\d+$`.
2) Create concise success/error JSON exemplars that validate.
3) Implement `validate_report` using `jsonschema` with Draft‑07; produce actionable error messages.
4) Add pytest covering valid/invalid cases.

## Acceptance Checks (must pass)
- `pytest -q` passes; tests validate both examples.
- `validate_report` raises on invalid fields (e.g., wrong enum/shape) with clear messages.
- Files exist at exact paths listed above.

## Validation Steps
- Run: `pytest -q`
- Manual: `python -c 'import json,rlcoach.schema as s; s.validate_report(json.load(open("examples/replay_report.success.json")))'`

## Deliverables
- Branch: `feat/gpt5-002-schema-and-validator`
- Files: schema, examples, validator, tests
- Log: `./codex/logs/002.md` with commands and results

## Safety & Compliance
- No secrets; examples small; deterministic outputs.

---
