# Execution Prompt — Ticket 012: Golden Tests and Replay Fixtures

You are a coding agent in Codex CLI. Plan–execute–verify until all acceptance checks pass.

## Critical Rules (repeat)
- Persist; deterministic artifacts; atomic writes; no large binaries in git.

## Environment & Tools
- Agent context: Codex CLI
- Tools: plan, shell, apply_patch, pytest
- Approvals: never; Network: enabled; Filesystem: full

## Branching
- Base: main
- Create: `feat/gpt5-012-golden-tests-and-fixtures`

## Goal
- Establish golden JSON outputs for synthetic inputs and a pathing strategy for local replay fixtures (not committed). Add tests that compare outputs to goldens for regression safety.

## Scope
- Add `tests/goldens/` with 2–3 minimal JSONs representing header-only and full data (synthetic).
- Add `assets/replays/README.md` describing local-only fixture paths and Git LFS guidance (do not commit large files).
- Add tests `tests/test_goldens.py` that generate reports from synthetic frames and compare to goldens.

## Out of Scope
- Real replay files in repo; network-based downloads.

## Primary Files to Modify or Add
- `tests/goldens/*.json`
- `assets/replays/README.md`
- `tests/test_goldens.py`

## Implementation Plan
1) Create small synthetic inputs to exercise pipeline deterministically.
2) Generate JSON outputs and store under `tests/goldens/`.
3) Add tests that compare normalized JSON (stable ordering) to goldens.

## Acceptance Checks (must pass)
- `pytest -q` passes; golden comparisons stable across runs.
- No files >1MB added; `assets/replays/README.md` exists and documents policy.

## Validation Steps
- Run: `pytest -q`

## Deliverables
- Branch: `feat/gpt5-012-golden-tests-and-fixtures`
- Files: goldens, tests, assets README
- Log: `./codex/logs/012.md`

## Safety & Compliance
- No large binaries; deterministic tests; no secrets; local-only usage of fixtures.

---
