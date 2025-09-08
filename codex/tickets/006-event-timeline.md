# Execution Prompt — Ticket 006: Event Detection and Timeline Aggregation

You are a coding agent in Codex CLI. Plan–execute–verify until all acceptance checks pass.

## Critical Rules (repeat)
- Persist; inspect inputs; deterministic event rules; explicit errors.
- No network; small, focused diffs.

## Environment & Tools
- Agent context: Codex CLI
- Tools: plan, shell, apply_patch, pytest
- Approvals: never; Network: enabled; Filesystem: full

## Branching
- Base: main
- Create: `feat/gpt5-006-event-timeline`

## Goal
- From normalized frames, identify and emit events per schema: goals, demos, kickoffs, boost pickups, touches, plus a chronological `timeline` with frame/time indices.

## Scope
- Add `src/rlcoach/events.py` with detectors:
  - `detect_goals(...)`, `detect_demos(...)`, `detect_kickoffs(...)`, `detect_boost_pickups(...)`, `detect_touches(...)`
  - `build_timeline(...)` assembling chronological list with required fields
- Tests using synthetic sequences to validate detectors and timeline ordering.

## Out of Scope
- On-target shot classification and advanced physics; approximate rules acceptable now.

## Primary Files to Modify or Add
- `src/rlcoach/events.py`
- `tests/test_events.py`

## Implementation Plan
1) Define minimal frame attributes required for detectors; document assumptions.
2) Implement detectors with clear thresholds and deterministic behavior.
3) Compose into a single timeline; ensure stable sorting by time then type.

## Acceptance Checks (must pass)
- `pytest -q` passes with 2+ tests per detector and a timeline aggregation test.
- Timeline events conform structurally to schema definitions (types/fields).

## Validation Steps
- Run: `pytest -q`

## Deliverables
- Branch: `feat/gpt5-006-event-timeline`
- Files: events module + tests
- Log: `./codex/logs/006.md`

## Safety & Compliance
- Deterministic thresholds; explicit warnings for missing data.

---
