# Log 2025-09-09 — Network Frames Integration
## Action Plan
- Implement hardened actor classification and broaden attribute handling in Rust adapter.
- Add a debug harness to inspect early-frame actor classes and attribute kinds.
- Update parser adapter docs to reflect boxcars-backed frames and fallback.

## What I Did
- Patched `parsers/rlreplay_rust/src/lib.rs` to:
  - Classify actors via object/class names (ball vs car) with allow-lists.
  - Track per-actor kind across frames; exclude ball from player list.
  - Handle additional attribute variants (`Location`, `LinearVelocity`) in addition to `RigidBody`, `ReplicatedBoost`, `TeamPaint`, and demolish.
  - Added `debug_first_frames(path, max_frames)` exposing actor/attribute summaries.
- Updated `codex/docs/parser_adapter.md` to describe real frames and add a debugging section.
- Created ticket `codex/tickets/2025-09-09-network-frames-actor-classification.md`.

## Commands Run
<none in CI; code patched for adapter and docs>

## Files Touched
- parsers/rlreplay_rust/src/lib.rs
- codex/docs/parser_adapter.md
- codex/tickets/2025-09-09-network-frames-actor-classification.md
- codex/logs/2025-09-09-network-frames.md

## Test & Check Results
- Lint: pending (`make lint`)
- Unit/Integration: pending (`make test`)
- Manual checks: inspected function signatures and Python shim compatibility

## Next Steps / Follow-ups
- Validate on a real replay locally using `debug_first_frames` to confirm attribute variants and actor classification.
- If certain builds use alternate transform carriers, extend match arms table-driven.
- Optionally measure sample rate from `iter_frames` timestamps and pass to `NetworkFrames`.

