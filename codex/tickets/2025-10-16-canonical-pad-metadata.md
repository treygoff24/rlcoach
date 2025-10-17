id: 2025-10-16
slug: canonical-pad-metadata
title: Ticket 2025-10-16 — Canonical Pad Metadata & Arena Tables
type: feature
priority: P0
branch: feat/gpt5-2025-10-16-canonical-pad-metadata
ticket_file: ./codex/tickets/2025-10-16-canonical-pad-metadata.md
log_file: ./codex/logs/2025-10-16-canonical-pad-metadata.md

## Objective
- Introduce canonical per-arena boost pad tables and fuzzy snapping in the Rust bridge so every pad pickup references a stable pad ID, arena slug, and field side classification (blue/orange/mid), eliminating coordinate drift across maps.

## Context
- Follow-up to the PadRegistry ticket: we now have enriched events but still rely on a single static coordinate table that assumes DFH Stadium.
- Plan `codex/Plans/1015_boost_pickup_rewrite.md` highlights arena variance and the need to snap ephemeral network actors to canonical pads using per-map tolerances.
- `src/rlcoach/field_constants.py` already exposes a standard Soccar table; we must extend this to multiple arenas and keep Rust/Python in sync.

## Scope
### Paths In Scope
- `parsers/rlreplay_rust/src/lib.rs`
- `parsers/rlreplay_rust/src/pads.rs`
- `parsers/rlreplay_rust/src/arena_tables.rs` (new module with canonical pad data & snapping helpers)
- `parsers/rlreplay_rust/Cargo.toml`
- `schemas/boost_pad_tables.json` (new shared canonical data set)
- `src/rlcoach/field_constants.py`
- `tests/parser/test_pad_metadata.py`
- `tests/test_field_constants.py`
### Paths Out of Scope
- Analyzer/event logic (Python) beyond syncing the data structure definition
- Non-Soccar arenas (Hoops, Dropshot) — document but leave unsupported for now
- CLI/reporting format changes

## Non-Goals
- No rewrite of boost pickup aggregation; just ensure metadata is canonical and available.
- No automatic download of external datasets; canonical tables must be stored locally in repo.
- Do not rework Git LFS assets.

## Constraints
- Maintain a single source of truth (JSON/structure) for pad coordinates that both Rust and Python consume; avoid divergent hard-coded tables.
- Cover at least the common ranked arenas (DFH, ChampionsField, Mannfield, BeckwithPark variants, UrbanCentral, Utopia Coliseum). Document unsupported maps in code comments.
- Snap pads within configurable tolerances (default 160uu small, 200uu big) and expose the `snap_error_uu` metric in events for debugging.
- `boost_pad_events` must now include `arena` (string map key) and `pad_side` ∈ {`blue`,`orange`,`mid`}.

## Acceptance Criteria
- [ ] `make rust-dev` regenerates the bridge without warnings after incorporating shared pad tables.
- [ ] `python -m rlcoach.cli analyze testing_replay.replay --adapter rust --out out --pretty` emits `boost_pad_events` entries containing `arena`, `pad_side`, and `snap_error_uu`; 34 unique `pad_id` values are observed for Soccar arenas.
- [ ] Added pytest `tests/parser/test_pad_metadata.py` loads the canonical table and asserts each supported arena maps network pad positions within <120uu for small pads and <180uu for big pads using sample coordinates.
- [ ] Updated `tests/test_field_constants.py` verifies Python helpers expose matching pad metadata (positions, radius, side) derived from the shared dataset.

## Verification
- `make rust-dev`
- `pytest tests/parser/test_pad_metadata.py -q`
- `pytest tests/test_field_constants.py -q`
- Manual spot check: `python -m rlcoach.cli analyze testing_replay.replay --adapter rust --out out --pretty` then inspect `boost_pad_events` for `arena` and `pad_side`.

## Deliverables
- Shared canonical pad dataset under `schemas/boost_pad_tables.json` with docstring header referencing data source.
- Rust snapping helpers providing `pad_side`, `arena`, and `snap_error_uu`.
- Python constants module updated to load/sync the same data (with tests).
- Log update at `codex/logs/2025-10-16-canonical-pad-metadata.md`.

## Workflow Expectations
- plan-first
- implement
- run_verification
- emit_patch
- summarize
