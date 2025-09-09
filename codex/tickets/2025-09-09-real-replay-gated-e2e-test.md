id: 2025-09-09
slug: real-replay-gated-e2e-test
title: Ticket 2025-09-09 — Gated E2E Test with Real Replay
branch: feat/gpt5-2025-09-09-real-replay-gated-test
ticket_file: ./codex/tickets/2025-09-09-real-replay-gated-e2e-test.md
log_file: ./codex/logs/2025-09-09-real-replay-gated-test.md

## Objective
- Add an end-to-end test that runs the CLI analyze command against a real replay path when explicitly enabled via environment variables.
- Assert non-degraded output: `parsed_network_data = true`, non-empty timeline, and schema validation.

## Scope
- Tests (`tests/test_smoke.py` or a new file):
  - If `RLCOACH_REAL_REPLAY=1` and `RLCOACH_REPLAY_PATH` (defaults to `testing_replay.replay`) exists, run:
    - `python -m rlcoach.cli analyze <path> --adapter rust --out <tmp>`
    - Load the JSON; assert `quality.parser.parsed_network_data` true, `events.timeline` non-empty, and `validate_report(...)` passes.
  - Otherwise, skip with a clear reason.
- Docs: add a note in `codex/docs/parser_adapter.md` or README about enabling the gated test locally.

## Out of Scope
- Shipping large replays to the repo or CI.

## Acceptance
- Locally, with the environment enabled and Rust core installed, the test passes and validates the full stack.
- In CI, the test is skipped by default and does not impact runtime significantly.

## Deliverables
- Branch: feat/gpt5-2025-09-09-real-replay-gated-test
- Files: new test file under `tests/` and small docs update
- Log: ./codex/logs/2025-09-09-real-replay-gated-test.md

