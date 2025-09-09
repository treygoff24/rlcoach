id: 2025-09-09
slug: rotation-fidelity-improvements
title: Ticket 2025-09-09 — Rotation Fidelity Improvements (optional)
branch: feat/gpt5-2025-09-09-rotation-fidelity
ticket_file: ./codex/tickets/2025-09-09-rotation-fidelity-improvements.md
log_file: ./codex/logs/2025-09-09-rotation-fidelity.md

## Objective
- Improve rotation/orientation fidelity for players by parsing true rotation (quaternion/euler) when available, falling back to velocity-based approximation otherwise, and gating sensitive metrics accordingly.

## Scope
- Rust core: map rotation attributes from actor updates where present; surface as radians (pitch, yaw, roll) or a consistent vector.
- Normalization: prefer true rotation; otherwise retain approximation; record a quality warning `player_rotation_approximated` when using fallback for >50% of frames.
- Analysis: ensure rotation-sensitive metrics check availability and degrade gracefully.

## Out of Scope
- Perfect rotation parsing across all historical versions (best-effort on common builds).

## Acceptance
- On at least one real replay where rotation is present, normalized frames include non-zero rotation vectors from attributes (not only from velocity approximation).
- When not present, the warning appears once in `quality.warnings`.

## Deliverables
- Branch: feat/gpt5-2025-09-09-rotation-fidelity
- Files: `parsers/rlreplay_rust/src/lib.rs`, `src/rlcoach/normalize.py`, `src/rlcoach/analysis/*` (gates)
- Log: ./codex/logs/2025-09-09-rotation-fidelity.md

