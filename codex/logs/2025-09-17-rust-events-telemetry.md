# Rust Telemetry & Event Detection Remediation – 2025-09-17

## Context
- Replay QA document: `docs/planning/2025-09-17-replay-report-qa.md`
- Target replay: `Replay_files/4985385d-2a6a-4bea-a312-8e539c7fd098.replay`
- Goal: eliminate bogus stats (goals, boost, movement, challenges, passing, kickoffs) and stabilise Rust adapter telemetry per QA findings.

## Issues Identified
1. **Goal Detection**
   - Ball crossing logic relied on `0.99 * BACK_WALL_Y`, missing positive-Y goals.
   - Goals re-fired every frame while the ball sat inside the goal, inflating counts >9k.

2. **Boost Pickup Classification**
   - Field constants listed only eight small pads; boost pickups rarely matched a pad and defaulted to `pad_id=-1`.

3. **Touch & Challenge Noise**
   - Touch detector emitted every dribble tick; challenges paired near-zero separation touches, reporting bogus 100% first-to-ball values for the wrong team.

4. **Passing Metrics**
   - `_is_forward_progress` required strict +Y movement, dropping diagonal/teamforward give-and-go plays.

5. **Rust Adapter Telemetry**
   - Actor classification included `CarComponent_*` actors, producing duplicate player entries.
   - Boost values remained frozen at 33; kickoff deltas never appeared in Python.

6. **Testing Gaps**
   - No regression coverage to ensure full pad table usage, goal gating, or teleport detection stability.

## Implemented Fixes
- **Events (`src/rlcoach/events.py`)**
  - Replaced goal plane with `FIELD.BACK_WALL_Y - GOAL_DEPTH` and gated duplicates until ball exits goal volume.
  - Debounced touches using 0.2s / 120uu windows plus relative speed checks; filtered challenges by distance (200-1000 uu) and minimum ball speed (>15 kph).
  - Introduced boost pad lookup via new 34-pad metadata, guaranteeing consistent `pad_id` and stolen-half calculation.

- **Field Constants (`src/rlcoach/field_constants.py`)**
  - Added `BoostPad` dataclass and exported `BOOST_PAD_TABLE` built from the canonical RLBot list (6 big, 28 small pads).

- **Passing Analysis (`src/rlcoach/analysis/passing.py`)**
  - Reduced forward delta threshold to 80 uu and projected displacement onto the attack axis, allowing diagonal passes to count while still requiring meaningful progress.

- **Rust Adapter (`parsers/rlreplay_rust/src/lib.rs`)**
  - Tightened actor classification (filtering out `CarComponent` objects) and only mapping `TeamPaint` for true cars.
  - Cached car position/velocity per actor and used a `BTreeMap` keyed by resolved player index to emit a single entry per player with evolving telemetry.

- **Python Adapter Shim (`src/rlcoach/parser/rust_adapter.py`)**
  - Added a safety dedupe pass that strips duplicate `player_id`s from frames (guarding older builds).

- **Tests**
  - Expanded `tests/test_events.py` with goal gating and 34-pad matching cases.
  - Added diagonal pass regression (`tests/test_analysis_passing.py`) and updated challenge fixtures (`tests/test_analysis_challenges.py`).
  - Introduced `tests/test_rust_adapter.py` to assert unique players plus velocity/boost changes in real replay frames.
  - Symlinked `testing_replay.replay` → `Replay_files/testing_replay.replay` to satisfy existing smoke tests.

- **CLI Validation**
  - Regenerated the markdown dossier (`python -m rlcoach.cli report-md ... --pretty`) after fixes to confirm metrics now align with the source header.

## Validation
- `pytest -q` (all 223 tests pass)
- `python -m rlcoach.cli report-md Replay_files/4985385d-2a6a-4bea-a312-8e539c7fd098.replay --out out --pretty`

## Notable Outcomes
- Goal counts/distance now match scoreboard; no duplicate entries per goal.
- Boost pickups classify all pads, enabling accurate boost economy metrics.
- Player movement averages reflect realistic speeds; kickoff analysis sees boost usage.
- Challenges and passing tables now surface non-zero contests and diagonal give-and-go events.
- Rust adapter produces six unique cars per frame with evolving velocity/boost values, verified via new telemetry tests.
