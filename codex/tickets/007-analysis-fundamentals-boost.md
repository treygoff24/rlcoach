# Execution Prompt — Ticket 007: Analyzers — Fundamentals and Boost Economy

You are a coding agent in Codex CLI. Plan–execute–verify until all acceptance checks pass.

## Critical Rules (repeat)
- Persist; deterministic computations; explicit errors; no network.

## Environment & Tools
- Agent context: Codex CLI
- Tools: plan, shell, apply_patch, pytest
- Approvals: never; Network: enabled; Filesystem: full

## Branching
- Base: main
- Create: `feat/gpt5-007-analysis-fundamentals-boost`

## Goal
- Implement per-player and per-team analyzers for Fundamentals and Boost, matching schema fields and community conventions (BPM/BCPM, overfill, waste, time at 0/100, etc.).

## Scope
- Add `src/rlcoach/analysis/fundamentals.py` and `src/rlcoach/analysis/boost.py`.
- Add aggregator `src/rlcoach/analysis/__init__.py` to merge results by player/team.
- Tests using synthetic events/timeline to verify metrics and schema alignment.

## Out of Scope
- Movement, positioning, passing, challenges, kickoffs (separate tickets).

## Primary Files to Modify or Add
- `src/rlcoach/analysis/fundamentals.py`
- `src/rlcoach/analysis/boost.py`
- `src/rlcoach/analysis/__init__.py`
- `tests/test_analysis_fundamentals.py`
- `tests/test_analysis_boost.py`

## Implementation Plan
1) Fundamentals: compute goals, assists, shots, saves, demos, score, shooting % from events.
2) Boost: compute BPM/BCPM, overfill, waste, pad counts, time at 0/100, averages from pickups + frame states.
3) Add deterministic tests and edge cases (header-only fallback scenarios).

## Acceptance Checks (must pass)
- `pytest -q` passes; outputs match schema types/ranges.
- Header-only mode yields partial metrics with clear warnings.

## Validation Steps
- Run: `pytest -q`

## Deliverables
- Branch: `feat/gpt5-007-analysis-fundamentals-boost`
- Files: analyzers + tests
- Log: `./codex/logs/007.md`

## Safety & Compliance
- Deterministic, local-only; explicit warnings for incomplete data.

---
