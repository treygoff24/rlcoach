# Execution Prompt — Ticket 010: Analyzers — Challenges/50s and Kickoffs

You are a coding agent in Codex CLI. Plan–execute–verify until all acceptance checks pass.

## Critical Rules (repeat)
- Persist; deterministic thresholds; explicit errors; no network.

## Environment & Tools
- Agent context: Codex CLI
- Tools: plan, shell, apply_patch, pytest
- Approvals: never; Network: enabled; Filesystem: full


## Goal
- Implement challenge/50s identification and outcomes, first-to-ball, challenge depth/risk index; and kickoff classification with outcomes and approach types, per schema.

## Scope
- Add `src/rlcoach/analysis/challenges.py` and `src/rlcoach/analysis/kickoffs.py`.
- Deterministic parameters: contest radius/time-to-ball window; risk index features (last-man, low boost, ahead-of-ball).
- Tests using synthetic frames verifying wins/losses/neutral and kickoff types.

## Out of Scope
- Other analyzers.

## Primary Files to Modify or Add
- `src/rlcoach/analysis/challenges.py`
- `src/rlcoach/analysis/kickoffs.py`
- `tests/test_analysis_challenges.py`
- `tests/test_analysis_kickoffs.py`

## Implementation Plan
1) Derive contests from proximity and time-to-ball; tag results by post-contact ball trajectory/change and next touch owner.
2) Compute risk index [0..1] using defined heuristics; document constants.
3) Classify kickoff approaches and outcomes; compute averages.

## Acceptance Checks (must pass)
- `pytest -q` passes; schema-aligned outputs.
- Deterministic results; thresholds documented and used consistently.

## Validation Steps
- Run: `pytest -q`

## Deliverables
- Files: analyzers + tests
- Log: `./codex/logs/010.md`

## Safety & Compliance
- Deterministic, local-only; explicit warnings for ambiguous events.

---
