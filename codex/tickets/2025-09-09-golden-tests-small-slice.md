id: 2025-09-09
slug: golden-tests-small-slice
title: Ticket 2025-09-09 — Golden Tests for Small Replay Slice (optional)
branch: feat/gpt5-2025-09-09-goldens-small
ticket_file: ./codex/tickets/2025-09-09-golden-tests-small-slice.md
log_file: ./codex/logs/2025-09-09-goldens-small.md

## Objective
- Add golden JSONs for a tiny, deterministic slice of frames to protect schema and invariants across refactors (both header-only and rust-backed variants).

## Scope
- Create or synthesize a tiny replay-like sequence that exercises: kickoff, a touch, and a boost pickup.
- Generate and commit two goldens under `tests/goldens/`: header-only and rust-backed equivalents (the latter based on the synthesized frames, not a large real replay).
- Tests: compare generated report segments against the goldens with stable keys and tolerances where needed.

## Out of Scope
- Shipping large replays.

## Acceptance
- `pytest -q` includes a test that validates against the new golden(s) with stable results.

## Deliverables
- Branch: feat/gpt5-2025-09-09-goldens-small
- Files: `tests/goldens/*`, corresponding tests
- Log: ./codex/logs/2025-09-09-goldens-small.md

