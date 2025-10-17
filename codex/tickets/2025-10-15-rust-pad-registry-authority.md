id: 2025-10-15
slug: rust-pad-registry-authority
title: Ticket 2025-10-15 — Rust Pad Registry Authority
type: feature
priority: P0
branch: feat/gpt5-2025-10-15-rust-pad-registry-authority
ticket_file: ./codex/tickets/2025-10-15-rust-pad-registry-authority.md
log_file: ./codex/logs/2025-10-15-rust-pad-registry-authority.md

## Objective
- Replace the fragile boost pickup inference path by introducing an authoritative `PadRegistry` in the Rust parser that tracks `TAGame.VehiclePickup_Boost_TA` actors, buffers instigator lookups, and emits enriched pad pickup/respawn events with consistent metadata for every frame.

## Context
- Primary recommendation in `codex/Plans/1015_boost_pickup_rewrite.md` is to push pad identification into the Rust layer before simplifying Python analyzers.
- Current implementation in `parsers/rlreplay_rust/src/lib.rs` stores per-actor state in loose maps and often emits `boost_pad_events` without `pad_id`, `position`, or player attribution.
- Python side (`src/rlcoach/events.py`) is forced to fall back to heuristic boost delta matching because pad events are incomplete.

## Scope
### Paths In Scope
- `parsers/rlreplay_rust/src/lib.rs`
- `parsers/rlreplay_rust/src/pads.rs` (new helper module for registry/state tracking)
- `parsers/rlreplay_rust/Cargo.toml`
- `tests/parser/test_rust_pad_registry.py`
### Paths Out of Scope
- `src/rlcoach/events.py`, `src/rlcoach/analysis/*`
- Per-arena pad coordinate data beyond what already exists
- Markdown/docs updates outside of the ticket log

## Non-Goals
- Do not implement canonical pad snapping by arena (handled next ticket).
- Do not alter Python report schemas or CLI arguments.
- No rewrite of boost stolen logic or downstream analytics.

## Constraints
- `iter_frames()` must continue to return a list of Python dict frames; the shape of `boost_pad_events` stays stable while we enrich fields.
- Handle spawn/pickup race conditions by queuing `Pickup*` notifications until the pad has position metadata; never emit partially filled events.
- Preserve and reuse `RLCOACH_DEBUG_BOOST_EVENTS` logging (respect env var, keep default silent).
- Avoid introducing global mutable state outside of per-replay execution; registry lives inside the frame iterator.

## Acceptance Criteria
- [ ] `make rust-dev` succeeds, rebuilding the parser with the new registry without warnings.
- [ ] `python -m rlcoach.cli analyze testing_replay.replay --adapter rust --out out --pretty` yields `out/testing_replay.json` where every `boost_pad_events` entry has `pad_id`, `is_big`, `object_name`, `timestamp`, and `status`, and all `COLLECTED` events include `actor_id` plus `player_id` when the player actor exists.
- [ ] With `RLCOACH_DEBUG_BOOST_EVENTS=1`, the debug stream for the first 300 frames shows sequential registry logs containing `pad_id`, `actor_id`, `position`, and `matched_state`/distance details (format may be JSON or key=value but must include those fields).
- [ ] `tests/parser/test_rust_pad_registry.py` validates that at least 90% of pad events for `testing_replay.replay` have a resolved `player_id` and that no event is missing `pad_id` or `status`.

## Verification
- `make rust-dev`
- `pytest tests/parser/test_rust_pad_registry.py -q`
- `python -m rlcoach.cli analyze testing_replay.replay --adapter rust --out out --pretty` (inspect `out/testing_replay.json` or debug logs as needed)

## Deliverables
- Rust `PadRegistry` implementation with buffering, instigator resolution via `component_owner`, and enriched event payloads.
- New targeted pytest covering pad event completeness.
- Ticket log entry at `codex/logs/2025-10-15-rust-pad-registry-authority.md` summarizing progress.

## Workflow Expectations
- plan-first
- implement
- run_verification
- emit_patch
- summarize
