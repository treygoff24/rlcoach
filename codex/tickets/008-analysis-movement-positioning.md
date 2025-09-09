# Execution Prompt — Ticket 008: Analyzers — Movement/Speed and Positioning/Rotations

You are a coding agent in Codex CLI. Plan–execute–verify until all acceptance checks pass.

## Critical Rules (repeat)
- Persist; deterministic bins/thresholds; explicit warnings for missing data.

## Environment & Tools
- Agent context: Codex CLI
- Tools: plan, shell, apply_patch, pytest
- Approvals: never; Network: enabled; Filesystem: full


## Goal
- Compute movement/speed and positioning/rotation metrics per schema: speed buckets, air/ground times, powerslides, aerials, halves/thirds occupancy, behind-/ahead-of-ball, distances, role occupancy, rotation compliance score (0–100).

## Scope
- Add `src/rlcoach/analysis/movement.py` and `src/rlcoach/analysis/positioning.py`.
- Implement rotation compliance scoring with flag collection (e.g., `double_commit`, `last_man_overcommit`).
- Tests on synthetic timelines verifying thresholds and flags.

## Out of Scope
- Passing, challenges, kickoffs.

## Primary Files to Modify or Add
- `src/rlcoach/analysis/movement.py`
- `src/rlcoach/analysis/positioning.py`
- `tests/test_analysis_movement.py`
- `tests/test_analysis_positioning.py`

## Implementation Plan
1) Implement speed buckets and time accounting with fixed thresholds; document constants.
2) Implement field segmentation (halves/thirds) with RLBot extents and role occupancy.
3) Implement rotation compliance scoring and flags.

## Acceptance Checks (must pass)
- `pytest -q` passes; computed fields within schema ranges.
- Deterministic results across runs; flags populated as strings.

## Validation Steps
- Run: `pytest -q`

## Deliverables
- Files: analyzers + tests
- Log: `./codex/logs/008.md`

## Safety & Compliance
- Deterministic; no network; explicit errors on invalid inputs.

---
