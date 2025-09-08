# Execution Prompt — Ticket 005: Normalization Layer (Timeline, Coordinates, Players)

You are a coding agent in Codex CLI. Plan–execute–verify until all acceptance checks pass.

## Critical Rules (repeat)
- Persist; deterministic transforms; explicit logs; small diffs.
- No network; pure functions where possible.

## Environment & Tools
- Agent context: Codex CLI
- Tools: plan, shell, apply_patch, pytest
- Approvals: never; Network: enabled; Filesystem: full

## Branching
- Base: main
- Create: `feat/gpt5-005-normalization-layer`

## Goal
- Convert parser outputs to a normalized timeline with measured `recorded_frame_hz`, stable coordinates (RLBot refs), and unified player identity/team assignment.

## Scope
- Add `src/rlcoach/normalize.py` with:
  - `measure_frame_rate(frames) -> float`
  - `to_field_coords(vec) -> vec3` using constants: x=±4096, y=±5120, z≈2044
  - `normalize_players(header, frames) -> players_index`
  - `build_timeline(header, frames) -> list[Frame]`
- Tests using synthetic frames verifying FPS measurement and coordinate mapping.

## Out of Scope
- Feature analyzers; only normalization.

## Primary Files to Modify or Add
- `src/rlcoach/normalize.py`
- `tests/test_normalize.py`

## Implementation Plan
1) Implement frame-rate measurement and coordinate transform helpers.
2) Build a simple normalized timeline structure consumable by analyzers.
3) Add tests for edge cases (gaps, variable sampling).

## Acceptance Checks (must pass)
- `pytest -q` passes; functions behave deterministically.
- Coordinate transform matches RLBot field constants.

## Validation Steps
- Run: `pytest -q`

## Deliverables
- Branch: `feat/gpt5-005-normalization-layer`
- Files: normalize module + tests
- Log: `./codex/logs/005.md`

## Safety & Compliance
- No network; pure deterministic transforms; explicit errors on bad input.

---
