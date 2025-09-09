id: 2025-09-09
slug: network-frames-actor-classification
title: Ticket 2025-09-09 — Network Frames Actor Classification & Coverage
branch: feat/gpt5-2025-09-09-network-frames
ticket_file: ./codex/tickets/2025-09-09-network-frames-actor-classification.md
log_file: ./codex/logs/2025-09-09-network-frames.md

## Objective
- Resolve empty players in network frames by hardening actor classification (ball vs car) and broadening attribute coverage in the Rust adapter.
- Add a debug harness to inspect early-frame actor classes and attribute kinds for replay builds that deviate.

## Scope
- Update `parsers/rlreplay_rust/src/lib.rs`:
  - Classify actors using object/class names with allow-lists; persist `ActorKind` per actor id.
  - Continue to detect ball; filter out ball from player set.
  - Accept additional attribute variants for transforms/velocity where available.
  - Add `debug_first_frames(path, max_frames)` for integration troubleshooting.
- Refresh `codex/docs/parser_adapter.md` to reflect boxcars-backed frames and the debug harness.

## Out of Scope
- Shipping real replay fixtures (large files); use local/manual validation instead.
- Switching to alternate parsers (e.g., rrrocket) except as a future fallback plan.

## Acceptance
- Frames emitted by `iter_frames` include non-empty `players` for typical ballchasing.com replays when the Rust core is present.
- Debug harness returns a list for the first N frames with `new_actors` and `updated_actors` annotated.
- Adapter docs describe actual, non-stub behavior and the fallback policy.

## Deliverables
- Branch: feat/gpt5-2025-09-09-network-frames
- Files: parsers/rlreplay_rust/src/lib.rs, codex/docs/parser_adapter.md
- Log: ./codex/logs/2025-09-09-network-frames.md

