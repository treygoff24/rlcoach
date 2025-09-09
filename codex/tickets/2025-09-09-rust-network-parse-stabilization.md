id: 2025-09-09
slug: rust-network-parse-stabilization
title: Ticket 2025-09-09 — Rust Network Parse Stabilization (iter_frames → normalized frames)
branch: feat/gpt5-2025-09-09-rust-network-parse-stabilization
ticket_file: ./codex/tickets/2025-09-09-rust-network-parse-stabilization.md
log_file: ./codex/logs/2025-09-09-network-parse-stabilization.md

## Objective
- Ensure Rust adapter consistently returns non-empty network frames for real replays and that `generate_report` sets `quality.parser.parsed_network_data = true` when Rust core is present.
- Remove "stub"-style warnings and standardize a single `parsed_with_rust_core` quality signal.

## Scope
- Rust core (`parsers/rlreplay_rust/src/lib.rs`):
  - Guarantee `iter_frames(path)` yields a concrete list of per-frame dicts on typical replays; avoid swallowing errors that degrade to `None` silently.
  - Include, at minimum, per-frame: `timestamp`, `ball: {position, velocity, angular_velocity}`, `players: [{player_id, team, position, velocity, rotation, boost, is_supersonic, is_on_ground, is_demolished}]`.
  - Tighten error handling: distinguish fatal vs recoverable issues; log quality warnings back to Python (e.g., `missing_attribute: RigidBody.angular_velocity`).
- Python shim (`src/rlcoach/parser/rust_adapter.py`):
  - Treat generator/iterator from Rust robustly; coerce to list once; ensure `NetworkFrames(..., frames=list)` not empty for valid replays.
  - Replace `parsed_with_rust_core_stub` with `parsed_with_rust_core` only.
- Tests:
  - Expand `tests/parser/test_rust_adapter_smoke.py` to assert frame count > 0, presence of players, and required keys when Rust core is importable.

## Out of Scope
- Full attribute parity for all replay variants (covered by actor-classification ticket).
- Event detection and analysis calibration (separate tickets).

## Acceptance
- On a typical real replay (local-only validation), `python -m rlcoach.cli analyze testing_replay.replay --adapter rust --out out` produces JSON with:
  - `quality.parser.parsed_network_data == true`
  - `metadata.total_frames > 1000`
  - `quality.warnings` contains `parsed_with_rust_core` and does not contain any `*_stub` markers.
- `tests/parser/test_rust_adapter_smoke.py` passes and asserts frames non-empty and well-formed (when Rust core importable).

## Deliverables
- Branch: feat/gpt5-2025-09-09-rust-network-parse-stabilization
- Files: `parsers/rlreplay_rust/src/lib.rs`, `src/rlcoach/parser/rust_adapter.py`, `tests/parser/test_rust_adapter_smoke.py`
- Log: ./codex/logs/2025-09-09-network-parse-stabilization.md

