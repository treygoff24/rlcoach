# Boost Pickup Rewrite Follow-Up Implementation Plan

## Context And Goals
- **Objective**: Resolve remaining inaccuracies in boost pad attribution after the initial rewrite so that Rust emits authoritative pad events for all supported arenas, Python consumes them without heuristic fallbacks, and parity with Ballchasing metrics is provable.
- **Scope**: Covers Rust `PadRegistry`, parser-to-Python normalization, analyzer attribution, test harnesses, and shared pad metadata. Excludes unrelated telemetry subsystems (touches, kickoffs, etc.).
- **Dependencies**: Existing rewrite reference (`codex/Plans/1015_boost_pickup_rewrite.md`), telemetry log (`codex/logs/2025-09-17-rust-events-telemetry.md`), and access to representative replays (standard + non-standard maps).

## Summary Of Current Findings
- **Parser-side fallback reintroduced heuristics**  
  `parsers/rlreplay_rust/src/pads.rs:126-154` assigns canonical pad IDs by snapping to the nearest pad using the *player’s* location whenever a pickup arrives before the pad actor has a known pose. This repeats the legacy “guess by player position” failure mode the rewrite was meant to eliminate.
- **Single-map pad table**  
  `parsers/rlreplay_rust/src/pads.rs:204-333` hard-codes a Soccar pad list without map awareness. Arenas with offset pads (Forbidden Temple, Neo Tokyo, Hoops, Labs) will be mislabelled without any warning.
- **Incomplete attribute handling**  
  `parsers/rlreplay_rust/src/lib.rs:520-589` only consumes `Attribute::PickupNew`, omitting older `Pickup` or `ReplicatedPickupData` packets. Legacy builds and some mutator modes emit only the older attributes, so events silently disappear.
- **Dropped metadata in Python**  
  `src/rlcoach/normalize.py:377-440` discards pad events that lack `player_id` even though the frame payload carries `actor_id`, `instigator_actor_id`, and `snap_distance`. As a result, analyzer logic falls back to boost-delta heuristics instead of performing a secondary attribution attempt.
- **Lack of parity/regression coverage**  
  Tests (`tests/parser/test_rust_pad_registry.py`) only validate structural fields on a single fixture. There are no assertions for pad mapping completeness across maps, no comparison to Ballchasing stats, and no synthetic coverage for race conditions (spawn + pickup same tick, respawn jitter, actor reuse).

## Implementation Phases

### Phase 1 — Ground Truth & Telemetry Capture
1. **Replay Selection**
   - Identify at least three fixtures: (a) Standard Soccar, (b) Alternative arena with shifted pads (e.g., Forbidden Temple), (c) Older-engine replay to exercise legacy attributes.
2. **Telemetry Dumps**
   - Extend `rlreplay_rust::debug_first_frames` to optionally include boost-specific attributes (Trajectory, RigidBody, Pickup/PickupNew, ReplicatedPickupData).
   - Run the harness on the selected replays and store the dumps under `codex/logs/` with date-stamped filenames.
3. **Parity Baseline**
   - Script a one-off CLI (under `scripts/` or as a notebook note) that compares our current boost totals/stolen counts with Ballchasing’s API exports for the same replays.
   - Record discrepancies in the plan to benchmark progress.

### Phase 2 — Canonical Pad Metadata Source Of Truth
1. **Data Acquisition**
   - Export canonical pad coordinates, radii, and side assignments from RLBot field info or the referenced community projects.
   - Capture per-map tolerances (default: 160uu big, 140uu small; override where maps require).
2. **Shared Schema**
   - Author a new JSON resource, e.g., `schemas/boost_pads.json`, keyed by map name with pad arrays (id, x/y/z, size, radius, tolerance).
   - Document schema fields and validation rules in `schemas/README.md`.
3. **Rust & Python Consumption**
   - Add a build step (Rust `build.rs` or codegen script) that transforms the JSON into `BOOST_PAD_DEFS` for Rust.
   - Update `src/rlcoach/field_constants.py` to load the same JSON so both languages stay in sync.
   - Fail fast during initialization if the replay map is missing from the catalog; surface a quality warning instead of defaulting to Soccar coordinates.

### Phase 3 — Rust Pad Registry Overhaul
1. **Constructor Overload**
   - Modify `PadRegistry::new` to accept map metadata (pad list, tolerances) derived from Phase 2.
   - Remove `name_to_def` caching that assumes identical positions across maps.
2. **Comprehensive Position Capture**
   - Track pad actor positions via any available attribute (`Trajectory`, `RigidBody`, `Location`, `StaticLocation`, `Transform`).
   - Maintain a pending event queue, but do **not** emit collected events until both pad position and canonical mapping succeed within tolerance.
3. **Pickup Handling**
   - Support `Pickup`, `PickupNew`, and `ReplicatedPickupData`. Normalize them to a single internal representation (`Collected` vs `Respawned`).
   - When instigator resolution fails, record the unresolved state and emit a warning event (`status = "UNRESOLVED"`) for Python to reconcile.
4. **Quality Telemetry**
   - Store `snap_distance`, pad tolerance, and actor metadata on every emitted event.
   - Emit structured debug logs (`RLCOACH_DEBUG_BOOST_EVENTS=1`) instead of raw `eprintln!`, including map name, pad id, and reason when an event cannot be resolved.

### Phase 4 — Python Normalization & Attribution Enhancements
1. **Struct Extensions**
   - Extend `BoostPadEventFrame` (`src/rlcoach/parser/types.py`) with fields for `snap_distance`, `tolerance`, `status_detail`, and raw instigator IDs.
2. **Normalization Pipeline**
   - Adjust `normalize.py` to preserve the additional fields, drop the blanket rejection of events missing `player_id`, and translate `status="UNRESOLVED"` into metadata for later stages.
   - Build an `actor_id` → `player_id` index during frame normalization to facilitate lookups.
3. **Analyzer Logic**
   - Update `_detect_boost_pickups_from_pad_events` (`src/rlcoach/events.py`) to:
     - Attempt actor-based resolution when `player_id` is missing by reusing the frame index.
     - Reject events only if both actor lookup and instigator chain fail.
     - Surface explicit quality warnings when falling back to deltas so downstream reports include a “boost attribution degraded” notice.

### Phase 5 — Testing & Validation
1. **Rust Unit Tests**
   - Create a new module (`src/pads/tests.rs`) with synthetic sequences covering:
     - Spawn → pickup same tick.
     - Pickup before the first position update (ensures buffering).
     - Respawn timing and actor reuse with tolerance checks.
     - Map-specific snappings (load fixture from JSON).
2. **Python Tests**
   - Augment `tests/parser/test_rust_pad_registry.py` with:
     - Map-aware assertions (pad IDs vs map metadata).
     - Validation of `snap_distance` ≤ tolerance.
     - Checks for actor-based resolution path.
   - Add high-level parity tests (marked `@pytest.mark.data`) comparing counts against stored golden JSON extracted from Ballchasing for the selected replays.
   - Expand `tests/test_events.py` to cover fallback warnings and actor attribution edge cases.
3. **End-to-End Fixtures**
   - Store replay-specific expected metrics under `tests/goldens/boost_parity/*.json`.
   - Integrate a CI job (opt-in) that runs the parity suite when fixtures are present.

### Phase 6 — Documentation & Logging
1. **Update Planning Docs**
   - Cross-reference this plan with the original rewrite document and describe how each finding is resolved.
2. **Session Log**
   - Record progress and parity outcomes in `codex/logs/` with timestamps.
3. **User Facing Notes**
   - Update `project-overview.md` or relevant docs to highlight the new pad metadata dependency and quality warning surfaces.

## Deliverables Checklist
- [ ] Telemetry dumps and parity baseline notes committed under `codex/logs/`.
- [ ] Shared pad metadata JSON plus documentation under `schemas/`.
- [ ] Refactored Rust `PadRegistry` with comprehensive attribute and map handling.
- [ ] Enhanced Python normalization and analyzer logic preserving fallback-free attribution.
- [ ] New/updated tests for Rust, Python, and parity suites with CI integration guidance.
- [ ] Documentation updates summarizing the new guarantees and warning behavior.

## Risk Mitigation
- **Map Coverage Gaps**: Failing open is unacceptable; the JSON loader will emit quality warnings and bypass attribution rather than mislabel pads.
- **Legacy Replay Variants**: Cover via telemetry dumps and ensure the parser handles older attribute variants before enabling parity enforcement.
- **Performance Concerns**: Event buffering is short-lived (≤ few frames); ensure benchmarks demonstrate negligible overhead. Use `VecDeque` and preallocated maps to keep allocations bounded.

## Validation Strategy
- Run `pytest -q` locally, including data-marked parity tests.
- For each benchmark replay, generate a markdown report (`python -m rlcoach.cli report-md ...`) and compare stolen counts/boost totals against Ballchasing exports.
- Review debug logs with `RLCOACH_DEBUG_BOOST_EVENTS=1` for any unresolved pads; resolve before ship.

## Acceptance Criteria
- Rust layer emits pad events with canonical IDs and full metadata for all pads on supported maps.
- Python attribution succeeds without resorting to boost-delta heuristics on the tested replays; any residual fallbacks surface as quality warnings and trigger CI failures.
- Boost metrics (pads collected, stolen counts, boost totals) match Ballchasing within ±1% across the designated parity suite.
- Documentation and logs reflect the new architecture and validation process.
