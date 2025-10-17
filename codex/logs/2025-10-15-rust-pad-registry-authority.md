# 2025-10-15 — Rust Pad Registry Authority

## 2025-10-15

- Implemented a dedicated `PadRegistry` in the Rust adapter with canonical pad mapping, buffered pickup handling, and debug logging gated by `RLCOACH_DEBUG_BOOST_EVENTS`.
- Reworked `iter_frames` to consume structured pad events from the registry and added `snap_distance` plus required metadata to each payload.
- Added `tests/parser/test_rust_pad_registry.py` to assert pad event completeness (pad_id/status presence and ≥90% player_id coverage).
- Verification: `make rust-dev`; `pytest tests/parser/test_rust_pad_registry.py -q`; `python -m rlcoach.cli analyze testing_replay.replay --adapter rust --out out --pretty` (produced error payload for invalid demo attacker data but generated outputs for inspection).
