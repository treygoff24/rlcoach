id: 2025-09-09
slug: analysis-real-frames-completeness
title: Ticket 2025-09-09 — Analysis Completeness on Real Frames
branch: feat/gpt5-2025-09-09-analysis-real-frames
ticket_file: ./codex/tickets/2025-09-09-analysis-real-frames-completeness.md
log_file: ./codex/logs/2025-09-09-analysis-real-frames.md

## Objective
- Ensure per-team and per-player analyzers output non-zero, plausible metrics using real network frames (fundamentals, boost, movement, positioning; plus placeholders for others consistent with schema).
- Guarantee per-player mapping (header ↔ frame IDs) is stable so `analysis.per_player` is populated and keyed correctly.

## Scope
- Analysis aggregator (`src/rlcoach/analysis/__init__.py`):
  - Verify extraction of players from frames; ensure mapping yields non-empty `per_player` for real replays.
- Individual analyzers (fundamentals, boost, movement, positioning):
  - Sanity-pass calculations on real frames; adjust safe defaults and thresholds to avoid all-zeros in normal play.
  - Gate any rotation-sensitive metrics behind availability of proper rotation; fall back to velocity-based approximation when necessary.
- Normalization (`normalize.normalize_players`):
  - Confirm aliasing logic handles frame-provided player IDs gracefully.

## Out of Scope
- Advanced accuracy tuning and insights heuristics.
- Heatmap computation (remain placeholder) and passing/challenges/kickoffs depth; keep present but simple.

## Acceptance
- Running analyze on `testing_replay.replay` produces:
  - `analysis.per_team.blue` and `.orange` fields with at least one non-zero metric each.
  - `analysis.per_player` map with entries for all header players; values contain non-zero metrics in at least fundamentals and movement.
  - No schema validation errors.

## Deliverables
- Branch: feat/gpt5-2025-09-09-analysis-real-frames
- Files: `src/rlcoach/analysis/*`, `src/rlcoach/normalize.py` (if mapping tweak needed)
- Log: ./codex/logs/2025-09-09-analysis-real-frames.md

