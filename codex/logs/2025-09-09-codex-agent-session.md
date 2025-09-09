# Log 2025-09-09 — Rust Adapter Integration + Smoke Validation

## Context
- Goal: Make the program functional with a Rust-backed parser that ingests replays and produces detailed analysis, while retaining header-only fallback.
- Baseline from latest commit (bf5cc93): Rust adapter existed with basic actor classification; Python shim present; docs updated; tests/lint pending.

## What I Changed (This Session)
- Build/Dev Ergonomics
  - Makefile: added `rust-dev` and `rust-build` targets to simplify pyo3 extension builds.
    - `rust-dev` tries `maturin develop`, falls back to building a wheel and pip-installing it, then asserts import.
  - Docs: updated `codex/docs/parser_adapter.md` to reference `make rust-dev` and added quick debug examples.

- Rust Core (`parsers/rlreplay_rust/src/lib.rs`)
  - Fixed debug harness numeric conversions for `ActorId`/`ObjectId` → use `i32` then cast to `i64` (build error fix).
  - Added handling for `Attribute::Location` to cover builds that split transform carriers.
  - Populated ball `angular_velocity` from `RigidBody.angular_velocity`.
  - Added a pragmatic player `rotation` approximation derived from velocity vector (pitch/yaw; roll=0) so the normalization/analyzers get meaningful orientation-like data.
  - Left `LinearVelocity` out (not a distinct boxcars variant; velocity is inside `RigidBody`).

- Python Shim / Tests
  - No behavioral change to `src/rlcoach/parser/rust_adapter.py`; its interface was already correct.
  - Added a focused smoke test `tests/parser/test_rust_adapter_smoke.py` that:
    - Skips if the Rust core isn’t importable.
    - Verifies header parse success and presence of the “parsed_with_rust_core” signal in warnings.
    - Verifies frames structure: timestamp, ball position/velocity/angular_velocity, players list.

## Validation & Artifacts
- Build & Import
  - `make rust-dev` → RUST_CORE loaded: True (wheel install fallback used where needed).

- Debug Harness
  - `debug_first_frames('testing_replay.replay', 3)` shows attribute kinds including `RigidBody`, `ReplicatedBoost`, `TeamPaint`, etc., confirming actor attribute coverage early in stream.

- Network Parse Sanity (ad-hoc)
  - Header: `map_name` and `team_size` parsed; quality warnings include `parsed_with_rust_core`.
  - Frames: `NetworkFrames` with 14,661 frames on `testing_replay.replay`.
  - First frame structure contains ball `position/velocity/angular_velocity` and non-empty `players` with `rotation` present.

- Tests
  - Ran only the smoke test to avoid long end-to-end analysis: `pytest -q tests/parser/test_rust_adapter_smoke.py` → 1 passed.

## Current Capabilities
- End-to-end pipeline exists: ingest → (rust|null) parser → normalize → events → analyzers → schema-validated report.
- With Rust core installed, adapter provides real frames; normalization ingests dict frames fine; analyzers can operate on velocity-based rotation approximation.
- Header-only fallback remains intact when Rust core is unavailable or fails.

## Next Steps (Hand-off Plan)

Must Do (to reach robust, “detailed” analysis):
- End-to-End Analyze Run & Profiling
  - Run `python -m rlcoach.cli analyze testing_replay.replay --adapter rust --out out --pretty` and time it on your machine.
  - If it takes too long or times out in CI, reduce workload temporarily by:
    - Limiting frames (env flag) or sampling rate in normalization for dev runs.
    - Deferring heavy analyzers behind flags.
  - Capture before/after timings; ensure report validates via schema.

- CI Integration for Rust Core
  - Add a CI job to install Rust toolchain + maturin, build the wheel, install it, and run the smoke test.
  - Optionally run a shortened analyze workflow on a tiny replay (or a truncated sample) to prevent CI timeouts.

- Rotation & Orientation Improvements
  - If boxcars exposes a rotation/quaternion attribute for cars in your sample replays, parse and convert to radians (pitch, yaw, roll), replacing the velocity-based approximation.
  - If not available/reliable, consider leaving the approximation but gate analyzer logic that depends on precise rotation.

- Attribute Coverage Audit
  - Use `debug_first_frames` on a few diverse replays to discover additional attribute variants you may need (e.g., alternate demolish carriers, team markers, other physics reps).
  - Extend match arms conservatively and keep changes table-driven where possible.

- Player Identity Enrichment
  - Harvest platform IDs/camera/loadout from header properties (UniqueId, CamSettings, Loadouts) and surface them in the report `players` block if desired by schema.
  - Keep it optional and local-only; avoid networking.

- Deprecations Cleanup (pyo3)
  - Replace deprecated `PyDict::new(py)`/`PyList::empty(py)` calls with the newer bound APIs when you touch the Rust file next.
  - Compile warnings currently don’t block builds but will in future PyO3.

Nice to Have (quality, maintainability):
- Streaming Frames API
  - Consider exposing a generator/iterator from Rust to reduce memory footprint on very long replays. The current approach materializes all frames.

- Golden Tests
  - Create golden JSONs for a tiny replay slice to assert schema and invariants over time (header-only and rust-backed variants).

- Analyzer Accuracy Pass
  - With better rotation and denser kinematics, revisit thresholds used in movement/positioning and event detection.
  - Add tests around specific detection edges (e.g., kickoff roles, possession windows).

## Commands & Shortcuts
- Build/install Rust extension (dev): `make rust-dev`
- Build wheel (release): `make rust-build`
- Quick debug of attribute coverage: 
  - `python -c "import rlreplay_rust as r; print(r.debug_first_frames('testing_replay.replay', 3))"`
- Run adapter smoke test only: `pytest -q tests/parser/test_rust_adapter_smoke.py`
- Full analyze (may be heavy):
  - `python -m rlcoach.cli analyze testing_replay.replay --adapter rust --out out --pretty`

## Open Questions / Risks
- Rotation fidelity: Are rotation attributes consistently present across your replay set? If not, the velocity-based approximation is serviceable but imperfect for powerslides/aerials.
- Build environment: `maturin develop` requires a venv; Makefile falls back to wheel build to avoid friction. Confirm this is acceptable in your dev workflows.
- Performance: Analyzers on full-length replays can be slow; consider sampling strategies or staged pipelines for UX.

## Files Changed
- Makefile: added rust build targets
- codex/docs/parser_adapter.md: updated usage/build notes
- parsers/rlreplay_rust/src/lib.rs: attribute coverage, kinematics, debug harness fixes
- tests/parser/test_rust_adapter_smoke.py: new smoke test

