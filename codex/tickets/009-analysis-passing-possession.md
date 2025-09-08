# Execution Prompt — Ticket 009: Analyzers — Possession and Passing

You are a coding agent in Codex CLI. Plan–execute–verify until all acceptance checks pass.

## Critical Rules (repeat)
- Persist; deterministic windowing (τ), explicit thresholds; no network.

## Environment & Tools
- Agent context: Codex CLI
- Tools: plan, shell, apply_patch, pytest
- Approvals: never; Network: enabled; Filesystem: full

## Branching
- Base: main
- Create: `feat/gpt5-009-analysis-passing-possession`

## Goal
- Implement possession and passing metrics per schema: possession time, pass attempts/completions/received, turnovers, give-and-go sequences.

## Scope
- Add `src/rlcoach/analysis/passing.py`.
- Define deterministic τ windows and spatial/velocity heuristics per plan.
- Tests using synthetic touch sequences verifying metrics and edge cases.

## Out of Scope
- Challenge/50s and kickoff metrics (separate tickets).

## Primary Files to Modify or Add
- `src/rlcoach/analysis/passing.py`
- `tests/test_analysis_passing.py`

## Implementation Plan
1) Implement possession model (`team in control` if last touch by team within τ and ball not traveling toward own half at high speed).
2) Implement pass detection and turnovers with spatial deltas toward opponent net.
3) Add tests covering multi-touch sequences and neutrality.

## Acceptance Checks (must pass)
- `pytest -q` passes; outputs match schema fields.
- Deterministic results with fixed τ and thresholds documented in code.

## Validation Steps
- Run: `pytest -q`

## Deliverables
- Branch: `feat/gpt5-009-analysis-passing-possession`
- Files: analyzer + tests
- Log: `./codex/logs/009.md`

## Safety & Compliance
- Deterministic, local-only; explicit warnings for insufficient data.

---
