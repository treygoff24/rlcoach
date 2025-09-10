# 2025-09-09 — Rust Network Parse Stabilization

Relates-to: codex/tickets/2025-09-09-rust-network-parse-stabilization.md
Plan: codex/Plans/rlcoach_implementation_plan.md

Summary
- Standardized quality signal: remove `*_stub` warnings from the Rust adapter header path; keep `parsed_with_rust_core` only.
- Verified Rust core iter_frames returns concrete per-frame dicts with required keys (timestamp, ball.position/velocity/angular_velocity, players[]).
- Ensured report generation flags `quality.parser.parsed_network_data = true` when frames present.

Changes
- Python shim (`src/rlcoach/parser/rust_adapter.py`):
  - Dropped appending `parsed_with_rust_core_stub` to header warnings. We now defer entirely to Rust-sourced `quality_warnings` (which include `parsed_with_rust_core`).

Notes
- Existing smoke test (`tests/parser/test_rust_adapter_smoke.py`) asserts non-empty frames and required keys when Rust core is importable.
- Report generator already sets `parsed_network_data` based on frames presence; no change needed there.

Next
- Optional: surface recoverable attribute-missing warnings from Rust network parsing (e.g., `missing_attribute: RigidBody.angular_velocity`) back into `quality.warnings` for better diagnostics.

