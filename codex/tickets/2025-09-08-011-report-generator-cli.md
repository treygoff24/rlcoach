# Execution Prompt — Ticket 011: Report Generator and CLI

You are a coding agent in Codex CLI. Plan–execute–verify until all acceptance checks pass.

## Critical Rules (repeat)
- Persist; deterministic JSON; atomic writes; schema validation; explicit errors.

## Environment & Tools
- Agent context: Codex CLI
- Tools: plan, shell, apply_patch, pytest
- Approvals: never; Network: enabled; Filesystem: full

## Branching
- Base: main
- Create: `feat/gpt5-011-report-generator-cli`

## Goal
- Assemble full JSON report per schema using ingestion → parser adapter → normalization → events → analyzers. Add CLI `analyze <replay> --header-only` producing one JSON file per replay, validating against the schema.

## Scope
- Add `src/rlcoach/report.py` to orchestrate pipeline and produce JSON (success or error contracts).
- Extend CLI in `src/rlcoach/cli.py` with `analyze` command, options: `--header-only`, `--out <path>`, `--pretty`.
- Integrate `validate_report` to enforce schema before writing.
- Tests for success path (synthetic data) and error path (unreadable file).

## Out of Scope
- UI and performance optimizations; advanced physics in analyzers.

## Primary Files to Modify or Add
- `src/rlcoach/report.py`
- `src/rlcoach/cli.py`
- `tests/test_report_end_to_end.py`

## Implementation Plan
1) Wire null adapter by default; propagate quality warnings and header-only mode.
2) Build per-team and per-player aggregates, coaching insights placeholder array.
3) Validate against `schemas/replay_report.schema.json`; write atomically to `out/<replay_basename>.json`.

## Acceptance Checks (must pass)
- `pytest -q` passes end-to-end test.
- `python -m rlcoach.cli analyze /tmp/foo.replay --header-only --out out/` writes JSON and validates.
- Error case returns `{ "error": "unreadable_replay_file", ... }` exactly as specified.

## Validation Steps
- Run: `pytest -q`
- Manual: run CLI with a small temp file; inspect JSON keys.

## Deliverables
- Branch: `feat/gpt5-011-report-generator-cli`
- Files: report orchestrator, CLI updates, tests
- Log: `./codex/logs/011.md`

## Safety & Compliance
- Atomic writes; explicit errors; no network in pipeline.

---
