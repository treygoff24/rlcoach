id: 2025-10-17
slug: python-boost-aggregator-rewrite
title: Ticket 2025-10-17 — Python Boost Aggregator Rewrite
type: feature
priority: P0
branch: feat/gpt5-2025-10-17-python-boost-aggregator-rewrite
ticket_file: ./codex/tickets/2025-10-17-python-boost-aggregator-rewrite.md
log_file: ./codex/logs/2025-10-17-python-boost-aggregator-rewrite.md

## Objective
- Refactor the Python boost ingestion and analysis pipeline to consume authoritative pad events from the Rust bridge, eliminate heuristic boost-delta matching, and align stolen boost metrics with Ballchasing semantics (opponent-half only, midfield excluded).

## Context
- Preceding tickets establish a reliable Rust-side `PadRegistry` with canonical pad metadata; Python still maintains legacy heuristics in `src/rlcoach/events.py` and derived analytics in `src/rlcoach/analysis/boost.py`.
- Current stolen/collected totals diverge because pads are inferred from player positions and boost deltas. With enriched events (`pad_id`, `pad_side`, `snap_error_uu`) we can delete the fallback path except for header-only mode.
- Golden Markdown reports under `tests/goldens/*.md` need to reflect the corrected attribution.

## Scope
### Paths In Scope
- `src/rlcoach/events.py`
- `src/rlcoach/analysis/boost.py`
- `src/rlcoach/report.py`
- `src/rlcoach/parser/rust_adapter.py` (only if minor wiring updates needed)
- `tests/test_events.py`
- `tests/analysis/test_boost.py`
- `tests/test_goldens.py` and updated fixtures under `tests/goldens/`
- Any new shared fixtures under `assets/replays/` (ensure Git LFS pointers)
### Paths Out of Scope
- Rust parser crate (already covered by previous tickets)
- Non-boost analytics (movement, positioning) unless required for compilation
- CLI flags or schema version bumps

## Non-Goals
- Do not drop the legacy fallback entirely; keep it accessible when no pad events are present (e.g., header-only ingest) and cover with tests.
- No redesign of the report layout beyond updating boost tables/fields that change due to corrected data.
- No changes to Markdown composer outside boost sections.

## Constraints
- `detect_boost_pickups` should consume parser-provided pad events by default; legacy delta inference only triggers when frames contain zero pad events (assert this in tests).
- Compute stolen pads purely from `pad_side` metadata (`mid` must never count as stolen). Include per-player/team aggregates that align with Ballchasing terminology.
- Preserve existing dataclasses/typing contracts exposed by `BoostPickupEvent` but extend them with new fields (`pad_side`, `snap_error_uu`, etc.) as needed.
- Update or regenerate golden Markdown fixtures to reflect new totals; keep 2-space indentation and deterministic ordering.

## Acceptance Criteria
- [ ] `pytest tests/test_events.py -k boost -q` passes with new assertions verifying that pad events drive pickup detection and that mid-line pads are excluded from stolen counts.
- [ ] `pytest tests/analysis/test_boost.py -q` validates updated player/team metrics, including stolen amounts and big/small pad breakdowns.
- [ ] `pytest tests/test_goldens.py -q` passes with refreshed Markdown fixtures showing corrected boost sections (include before/after commentary in the ticket log).
- [ ] `python -m rlcoach.cli analyze testing_replay.replay --adapter rust --out out --pretty` produces JSON where `analysis.boost.amount_stolen` (and per-player breakdowns) match expectations recorded in the updated tests/goldens; no warning about heuristic fallback appears when pad events are present.

## Verification
- `make test`
- `python -m rlcoach.cli analyze testing_replay.replay --adapter rust --out out --pretty`
- Manual diff of updated Markdown golden(s) to confirm formatting and totals.

## Deliverables
- Simplified boost pickup detection relying on canonical pad events with legacy fallback guarded and tested.
- Updated analysis logic and golden fixtures reflecting Ballchasing-aligned stolen metrics.
- Ticket log at `codex/logs/2025-10-17-python-boost-aggregator-rewrite.md` summarizing implementation details and verification results.

## Workflow Expectations
- plan-first
- implement
- run_verification
- emit_patch
- summarize
