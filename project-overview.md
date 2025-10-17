# RLCoach Project Overview

This document equips a senior engineer with the context needed to diagnose and fix critical bugs in **rlcoach**, an all-local Rocket League replay analysis toolkit. It distills the repository’s architecture, tooling, data flow, and known problem areas so work can begin without cloning the project.

---

## Mission & Current Status
- **Goal:** Parse Rocket League `.replay` files entirely offline and produce schema-stable JSON + Markdown dossiers for coaches and analysts.
- **Pipeline:** `ingest → parser adapter → normalization → events → analyzers → report generation → optional UI`. The Python path is functional in header-only mode; per-frame metrics rely on the Rust adapter.
- **Adapters:** A Python “null” adapter always works (header only). The Rust adapter (`pyo3` + `boxcars`) should unlock full telemetry but currently fails to emit populated player frames (critical bug).
- **Outputs:** JSON constrained by `schemas/replay_report.schema.json` and a Markdown dossier rendered by `src/rlcoach/report_markdown.py`.
- **Tooling:** CLI entrypoint (`python -m rlcoach.cli`), optional CLI viewer (`python -m rlcoach.ui`), parity scripts, and comprehensive pytest coverage including golden fixtures.

---

## Repository Layout

| Path | Purpose |
| --- | --- |
| `src/rlcoach/` | Core Python package (pipeline, analyzers, CLI, UI). |
| `src/rlcoach/analysis/` | Modular analyzers: fundamentals, boost, movement, positioning, passing, challenges, kickoffs, heatmaps, insights. |
| `src/rlcoach/parser/` | Adapter abstraction, null adapter, Rust bridge, shared data types. |
| `src/rlcoach/events.py` | Event detection & timeline aggregation. |
| `src/rlcoach/normalize.py` | Coordinate normalization, frame rate measurement, identity mapping, timeline builder. |
| `parsers/rlreplay_rust/` | Rust crate compiled with `maturin` to expose replay parsing via `pyo3`. |
| `schemas/` | JSON Schema for reports. |
| `tests/` | pytest suite mirroring pipeline stages, parity harnesses, and golden fixtures. |
| `codex/Plans/` | Project roadmap (`rlcoach_implementation_plan.md` is canonical). |
| `codex/docs/` | Deep dives (e.g., JSON↔Markdown mapping, network frame issue summary). |
| `codex/tickets/` | Conventional commits / ticket trail for ongoing and future work. |
| `assets/replays/` | Git LFS staging area for large replay fixtures (only pointers checked in). |
| `Replay_files/` | Local scratch replays used for manual testing (not all tracked). |
| `examples/` | Sample success/error JSON payloads. |
| `scripts/` | Utility scripts such as boost parity diffing. |

---

## End-to-End Pipeline

### 1. Ingestion (`src/rlcoach/ingest.py`)
- Validates file size bounds (`MIN_REPLAY_SIZE` 10 KB, `MAX_REPLAY_SIZE` 50 MB).
- Computes SHA256, performs format sniffing via known header sequences, and prepares CRC scaffolding (polynomial constants implemented, verification flagged as TODO).
- Emits structured metadata and warnings consumed up-pipeline; raises rich `RLCoachError` subclasses for CLI clarity.

### 2. Parser Layer (`src/rlcoach/parser/`)
- **Interface:** `ParserAdapter` abstract base class defines `parse_header`, `parse_network`, `name`, and `supports_network_parsing`.
- **Types:** `types.py` declares immutable dataclasses for headers, players, frames, boost pad events, etc., shared across adapters and normalization.
- **Null Adapter (`null_adapter.py`):** Generates placeholder header/team data to keep the pipeline operable when only file metadata is available.
- **Rust Adapter (`rust_adapter.py`):** Wraps the compiled module from `parsers/rlreplay_rust`. Attempts header parse first; network parsing optional based on adapter capabilities. Fallback to null adapter is automatic on errors.

### 3. Normalization (`src/rlcoach/normalize.py`)
- Measures actual frame rate (`measure_frame_rate`) using median timestamp deltas.
- Harmonizes vectors into RLBot field coordinates via `to_field_coords` and clamps values to arena bounds defined in `src/rlcoach/field_constants.py`.
- Builds deterministic player identities by merging header stats with sampled frame aliases (`utils/identity.py` handles sanitization, slugification, and platform ID precedence).
- Produces normalized `Frame` objects (`build_timeline`) with canonical ball/player structures; includes kickoff buffer logic for timeline completeness.

### 4. Event Detection (`src/rlcoach/events.py`)
- Encodes heuristics for goals, demos, kickoffs, boost pickups, touches, and challenges. Constants (goal line thresholds, boost pad radii, supersonic flags, etc.) mirror community analyzers like Ballchasing for parity.
- Maintains temporal and spatial context (e.g., `PadState`, `PadEnvelope`) to reconcile boost pad respawns and stolen pads, with optional debug logging via `RLCOACH_DEBUG_BOOST_EVENTS`.
- Aggregates events into a chronological timeline for downstream reporting (`TimelineEvent` dataclass).

### 5. Analysis Layer (`src/rlcoach/analysis/`)
- `aggregate_analysis` orchestrates all analyzers, returns per-team and per-player sections plus coaching insights.
- **Fundamentals:** Counts goals/assists/shots/saves/demos; fuses header stats when present.
- **Boost:** Computes BPM/BCPM, time at 0/100, overfill, waste, stolen pads; matches events to frames to estimate consumption.
- **Movement:** (see `movement.py`) tracks ground/air time, speed buckets, supersonic coverage.
- **Positioning:** Breaks down field thirds/halves, behind-ball percentages, rotation roles; calculates rotation compliance separately (`calculate_rotation_compliance`).
- **Passing & Possession:** Placeholder metrics exist but expect richer data once network frames are fixed.
- **Challenges & Kickoffs:** Analyzes 50/50 outcomes, kickoff roles, time-to-first-touch.
- **Heatmaps:** Down-sampled occupancy grids for ball/player positions.
- **Insights:** `insights.py` derives textual coaching cues (severity, evidence) from metric thresholds.

### 6. Reporting (`src/rlcoach/report.py`, `report_markdown.py`, `ui.py`)
- `generate_report` orchestrates ingest → parse → normalize → events → analysis. Builds quality warnings, metadata, and teams/players blocks. Serializes timeline events via `_timeline_event_to_dict`.
- Validation uses `schemas/replay_report.schema.json` through `src/rlcoach/schema.py` (`jsonschema` Draft-07).
- `write_report_atomically` and `write_markdown` ensure atomic writes using temp files.
- Markdown composer mirrors the schema: front matter, team/player tables, timeline, heatmaps, appendices. Golden files under `tests/goldens/*.md` guard formatting.
- CLI viewer (`src/rlcoach/ui.py`) pretty-prints JSON summaries and supports `--player` focus filters.

---

## Data Contracts & Schemas
- **Parser Data (`parser/types.py`):** Immutable dataclasses for `Header`, `PlayerInfo`, `Frame`, `PlayerFrame`, `BallFrame`, `BoostPadEventFrame`, etc. These are the lingua franca between adapters, normalization, and analytics.
- **Events Dataclasses (`events.py`):** `GoalEvent`, `DemoEvent`, `KickoffEvent`, `BoostPickupEvent`, `TouchEvent`, `ChallengeEvent`, `TimelineEvent`. Each is serializable via `_serialize_value`.
- **Report Schema (`schemas/replay_report.schema.json`):**
  - Differentiates success payload vs error contract (`{"error": "unreadable_replay_file", "details": "..."}"`).
  - Enforces metadata, quality, teams, players, events, analysis structure, and enumerations (playlist IDs, team names).
  - Analysis payload uses nested objects keyed by player ID; insights are arrays with severity/message/evidence fields.
- **Examples:** `examples/replay_report.success.json` and `examples/replay_report.error.json` demonstrate schema-shape for quick reference.

---

## CLI, Tooling & Developer Workflow
- **Entry Point:** `python -m rlcoach.cli` or `rlcoach` (via `pyproject.toml` script entry). Subcommands:
  - `ingest` (with `--json` for structured output).
  - `analyze` (header-only or adapter-backed; writes JSON to `--out`).
  - `report-md` (atomically writes both JSON and Markdown).
- **Make Targets (see `Makefile`):**
  - `make install-dev` → editable install with dev dependencies (pytest, Ruff, Black).
  - `make test`, `make fmt`, `make lint`, `make clean`.
  - `make rust-dev` → install `maturin`, build the Rust adapter (prefers `maturin develop`), verifies import.
  - `make rust-build` → release wheel for distribution.
- **Parity Script:** `scripts/diff_boost_parity.py` compares per-player boost metrics against Ballchasing exports (fixtures under `tests/fixtures/boost_parity/`).
- **UI:** `python -m rlcoach.ui view out/replay.json --player "DisplayName"` for quick local inspection.

---

## Rust Adapter Deep Dive (`parsers/rlreplay_rust/`)
- **Structure:** `Cargo.toml` + `src/lib.rs` exposing `parse_header`, `parse_network`, and helper utilities via `pyo3`.
- **Header Path:** Uses `boxcars::ParserBuilder::never_parse_network_data()` to populate playlist/map, team scores, player stats, goals, and highlight tick marks. Emits warnings (e.g., `build_version:*`) for visibility.
- **Network Path:** Intended to call `must_parse_network_data()` and iterate frames, projecting ball `RigidBody` updates, car actors, boost events, demolitions, and team assignments.
- **Current Output:** Returns frame count and ball data but misses player actors, resulting in empty `players` arrays per frame.
- **Build & Test Locally:**
  ```bash
  make rust-dev
  python - <<'PY'
  import rlreplay_rust
  print("Adapter:", rlreplay_rust.__dict__.get("__all__", []))
  print("Frames:", rlreplay_rust.net_frame_count("testing_replay.replay"))
  PY
  ```
- **Debug Artifacts:** `codex/docs/network-frames-integration-issue.md` documents the investigation, hypotheses, and requested guidance for actor classification and attribute coverage.

---

## Testing & Quality Gates
- **Pytest Suite (`tests/`):** Mirrors pipeline modules.
  - `test_ingest.py`, `test_parser_interface.py`, `test_normalize.py`, `test_events.py`.
  - Analyzer-specific tests (`test_analysis_*.py`) ensure per-metric correctness and header fallbacks.
  - `tests/analysis/` contains Ballchasing parity harnesses and boost pickup fixture validations.
  - `test_report_end_to_end.py` exercises CLI + report validation on synthetic replays.
  - `test_report_markdown.py` and `tests/goldens/*.md` lock the Markdown output.
  - `test_schema_validation*.py` harden JSON Schema enforcement (success/error paths).
  - `test_events_calibration_synthetic.py` feeds fabricated frames to verify that detection heuristics fire as expected.
  - `test_rust_adapter.py` ensures Python shim loads the compiled module and adheres to interface expectations (even though player frames are currently empty).
- **Fixtures & Goldens:**
  - `tests/goldens/*.json|.md` capture canonical outputs for regression detection.
  - `tests/fixtures/boost_parity/` houses Ballchasing reference metrics for diffing.
  - `examples/` provide ready-made success/error payloads for manual inspection.
- **Coverage Expectations:** ≥80 % for analyzers and schema validators per repository guidelines.

---

## Supporting Documentation & Tickets
- **Primary Plan:** `codex/Plans/rlcoach_implementation_plan.md` — architecture, feature roadmap, error handling expectations.
- **Docs of Interest:**
  - `codex/docs/json-report-markdown-mapping.md` — ensures Markdown mirrors JSON content.
  - `codex/docs/json-to-markdown-report-plan.md` — outlines composer roadmap.
  - `codex/docs/ui.md` — offline viewer usage notes.
  - `codex/docs/network-frames-integration-issue.md` — deep dive into the critical bug.
- **Tickets (`codex/tickets/`):** Each major feature has a historical ticket (001–014). Recent 2025-09-09 tickets capture outstanding tasks (e.g., `...-rust-network-parse-stabilization.md`, `...-network-frames-actor-classification.md`, `...-real-replay-gated-e2e-test.md`). Cross-reference these for prior discussion and acceptance criteria.

---

## Known Limitations & Critical Issues
1. **Network Frames Missing Player Data (Critical):**
   - Symptom: Reports generated with the Rust adapter show accurate header data but analyzers output zeros because `Frame.players` is empty.
   - Location: Rust exporter (`parsers/rlreplay_rust/src/lib.rs`) not mapping actor IDs to car entities correctly; suspected gaps in class resolution or attribute handling (`Attribute::RigidBody`, `Attribute::ReplicatedBoost`, `Attribute::TeamPaint`, demolish events).
   - References: `codex/docs/network-frames-integration-issue.md`, `codex/docs/network-frames-integration-issue-report.md`.
2. **CRC Validation Placeholder:**
   - `ingest.bounds_check` works, but CRC reports “not yet implemented” and sets `crc_checked=False`. Full CRC support is planned but not essential for the current bug.
3. **Passing/Challenges Analyzers Need Real Frames:**
   - Metrics degrade to defaults under header-only mode. Once frames are populated, revisit heuristics for richer analysis.
4. **Golden Fixtures Use Synthetic Data:**
   - Real replay fixtures should live under Git LFS in `assets/replays/`. Several local `.replay` files exist in `Replay_files/` for experimentation but are not part of automated tests.

---

## Reproducing the Critical Bug
1. Ensure the Rust adapter is compiled (`make rust-dev`).
2. Generate a report with adapter preference:
   ```bash
   python -m rlcoach.cli analyze Replay_files/testing_replay.replay --adapter rust --out out --pretty
   ```
3. Inspect JSON (`out/testing_replay.json`):
   - `analysis.per_player` shows zeros for speed, boost, positioning metrics.
   - Quality block indicates `parsed_network_data: true` yet `analysis.warnings` may include `header_only_mode_limited_metrics`.
4. Run CLI viewer:
   ```bash
   python -m rlcoach.ui view out/testing_replay.json --player "ApparentlyJack"
   ```
   The summary lists players but lacks meaningful stats, confirming player frames were empty.
5. Confirm via Python shell:
   ```python
   from rlcoach.parser import get_adapter
   adapter = get_adapter("rust")
   frames = adapter.parse_network("Replay_files/testing_replay.replay")
   print(frames.frame_count, len(frames.frames))
   print(frames.frames[0].get("players"))
   ```
   `players` is `[]` across all frames.

---

## Suggested Debugging Approach
1. **Instrument Actor Mapping:**
   - Add temporary logging in `parsers/rlreplay_rust/src/lib.rs` to dump `new_actors` and `updated_actors` (object names, class indices). Compare against expected car classes (`Car_TA`, `Vehicle_TA`, `Default__PRI_TA`, etc.).
   - Validate whether `replay.objects` lookup is sufficient or if `replay.class_indices` / `replay.net_cache` must be consulted for modern versions.
2. **Expand Attribute Handling:**
   - Observe which `Attribute` variants carry car transforms/velocity in current builds (possible variants: `RigidBody`, `ReplicatedRBState`, `Location`, etc.).
   - Ensure boost amount, demolish info, and team assignments (`TeamPaint`, `TeamIndex`) are captured.
3. **Associate Actors with Header Players:**
   - Use platform IDs / PRIs when available; fallback to team-based ordering with stability across frames.
   - Populate `player_id`, `team`, `position`, `velocity`, `rotation`, `boost_amount`, `is_supersonic`, `is_on_ground`, `is_demolished`.
4. **Validate via Synthetic + Real Replays:**
   - Keep `tests/test_events_calibration_synthetic.py` passing (expects player frames in normalized output).
   - Add focused tests under `tests/parser/` or `tests/test_rust_adapter.py` once real player frames are produced (e.g., assert non-empty players for sample fixtures).
5. **Regenerate Reports & Goldens:**
   - After fixes, update JSON/Markdown goldens with rust-backed data.
   - Re-run parity script against Ballchasing exports to confirm metrics alignment.
6. **Document Learnings:**
   - Update `codex/docs/network-frames-integration-issue.md` with findings and adjust relevant tickets (`...-rust-network-parse-stabilization.md`, `...-network-frames-actor-classification.md`).

---

## Setup Checklist (Fresh Environment)
```bash
python -m venv .venv && source .venv/bin/activate
make install-dev            # installs rlcoach in editable mode + pytest/ruff/black
make rust-dev               # optional; compiles Rust adapter via maturin
pytest -q                   # run test suite
python -m rlcoach.cli --help
```

For Markdown reports:
```bash
python -m rlcoach.cli report-md Replay_files/testing_replay.replay --adapter rust --out out --pretty
```
Outputs `out/testing_replay.json` + `out/testing_replay.md`.

---

## Additional Reference Points
- **Field Geometry:** `src/rlcoach/field_constants.py` enumerates arena dimensions, goal depth, boost pad locations (used by event detection and heatmaps).
- **Utility Helpers:** `src/rlcoach/utils/identity.py` resolves canonical player IDs; `src/rlcoach/utils/parity.py` contains parity helpers.
- **Versioning:** `src/rlcoach/version.py` exposes `get_schema_version()` used in reports.
- **Local Replays:** `Replay_files/` contains various `.replay` assets (e.g., `0925.replay`, `testing_replay.replay`) plus Ballchasing exports for comparison (`ballchasing_output/`).
- **Markdown Style:** Follow Title Case headings, deterministic table layout (see goldens) when editing docs.

---

## What to Hand Off
- This overview file (`project-overview.md`).
- `codex/docs/network-frames-integration-issue.md` for detailed bug history.
- `Replay_files/testing_replay.replay` (or any available real replay) for reproduction.
- Latest JSON/Markdown outputs in `out/` after running `report-md`.

With this context, a senior engineer can dive straight into the Rust adapter, restore per-frame player data, and verify that analyzers produce meaningful metrics end-to-end.

