# Replay Report QA Findings – 4985385d-2a6a-4bea-a312-8e539c7fd098

## Context
- Source JSON: `out/4985385d-2a6a-4bea-a312-8e539c7fd098.json`
- Generated Markdown: `out/4985385d-2a6a-4bea-a312-8e539c7fd098.md`
- Replay: RLCS match (Archie/Joyo/Joreuz vs ApparentlyJack/oaly/stizzy)
- Parser: current `parsers/rlreplay_rust` network export feeding `build_timeline`

The Markdown dossier surfaces multiple obvious correctness failures. This note tracks each symptom, pinpoints the faulty layer (Rust adapter vs Python analysis), and outlines concrete fix plans.

## Observed Failures
- **Team fundamentals** list 0 blue goals and 9,515 orange goals, with scores in the hundreds of thousands.
- **Boost economy** shows sub-1 `bcpm`, `bpm` in the 20s, and “overfill” totals larger than the boost collected.
- **Movement** reports average speeds below 25 kph and >600 seconds of ground time for a single player inside a 550 second match.
- **Possession & passing** returns zeros for every pass metric despite 92 touch events.
- **Challenges** tables report single-digit contests with 100% first-to-ball for the losing team.
- **Kickoff approach** lists only FAKE/DELAY, no SPEEDFLIP despite observing them live, and boost usage is always 0.
- **Player fundamentals** (goals, shots, score) are zero for blue players even when header/scoreboard confirms scoring plays.

## Root Cause Analysis

### 1. Goal + Score Accounting (Python event detector)
- `events.detect_goals` emits a new `GoalEvent` *every frame* while the ball remains beyond `GOAL_LINE_THRESHOLD`. This leads to 9,515 duplicates for the first orange goal (`events.goals` shows 9,515 entries, all ORANGE).
- Blue goals never register because the threshold is set to `0.99 * BACK_WALL_Y ≈ 5,068`, yet the positive-Y goal frames from the parser cap at ≈4,919 (ball never crosses the hard-coded gate). We are missing all positive-Y goals, so blue fundamentals stay at zero.
- Downstream: `analysis.fundamentals` for teams inherits the bogus counts; `score` inflates by 100 points per phantom goal.

**Fixes**
1. Gate goal detection with state: once we log a goal, wait for the ball to exit the goal volume (or rely on header `goal.frame` indices) before emitting again.
2. Replace the `0.99` magic factor with a data-driven limit (e.g. `FIELD.BACK_WALL_Y - GOAL_DEPTH`) or expose a calibration constant derived from sample replays.
3. Add regression tests around `detect_goals` using recorded frames across both net directions.

### 2. Boost Economy (Python field constants + detection)
- `FIELD.SMALL_BOOST_POSITIONS` only defines eight pads; the real field has 28 small pads (34 total). As a result `detect_boost_pickups` rarely matches a pad, leaves `pad_id = -1`, and records the player’s location `(0,0,17)` instead of the actual pad. That makes “pad counts” and stolen logic meaningless.
- Because pad IDs default to `-1`, `analyze_boost` cannot distinguish big/small or stolen pads. The algorithm still sums boost increases, hence the oddly low but non-zero `bpm` and the nonsensical `overfill` totals (artifact of subtracting against `pad_id = -1`).

**Fixes**
1. Populate the full RLBot boost pad table (34 entries with coordinates and “is_big” flags) in `field_constants.py`.
2. Re-run pickup detection with the expanded table and clamp distances using pad-specific radii.
3. Add fixture tests verifying that all 34 pads can be matched and that `pad_id` is never `-1` when the player is on a canonical pad.

### 3. Movement Metrics (Rust adapter data loss)
- The Rust bridge outputs player velocities with `x=0, y=0` for every frame; only small `z` spikes appear (likely ball angular data leaking). Example: `frames.frames[1200]['players'][0]['velocity']` is `{0,0,0}`. The analyzer therefore thinks players barely move and reports `avg_speed_kph ≈ 23`.
- Positions also collapse to `(0,0,17)` for long stretches in the normalized timeline because we overwrite the per-frame state each tick without persisting actor updates correctly.

**Fixes** (Rust side)
1. Ensure `parsers/rlreplay_rust` extracts `RigidBody` velocity components (linear + angular) for each car actor. Right now we only decode position and never map the velocity attribute IDs.
2. Revisit the frame builder so we persist the last known state and apply delta updates between network frames instead of rebuilding a blank slate each tick.
3. Extend the adapter unit tests to assert non-zero velocity magnitudes for known frames (e.g., kickoff dash).

### 4. Possession & Passing (Python heuristics + touch noise)
- Touch detection fires on nearly every frame during dribbles (no velocity check), so the `touches` list is heavily polluted with self-touches at identical coordinates.
- `_compute_pass_metrics` requires forward progress of ≥200 uu strictly along the attack axis. Diagonal passes or small give-and-go touches fail the check, so no attempts/completions are counted.

**Fixes**
1. Debounce touches by combining proximity with relative velocity and minimum ball speed; collapse repeated touches within ~0.2s at the same location.
2. Relax `_is_forward_progress` to allow diagonal progress (project displacement onto the attack vector instead of hard ±ΔY) and set a smaller minimum (≈80 uu) validated against real replays.
3. Add golden tests that load touch streams and assert non-zero passes/turnovers for known scripted scenarios.

### 5. Challenge Detection (Python)
- Because the touch stream is noisy, `detect_challenge_events` pairs consecutive touches from the same team or at identical coordinates, producing trivial “challenges” with depth ≈0.9 m and risk scores that do not match reality.

**Fixes**
1. Consume the debounced touch stream from the fix above.
2. Require a minimum spatial separation between touches (`_distance_3d > 200`) and enforce ball speed thresholds so only true 50/50s enter the window.
3. Recompute risk metrics using the actual situational data once touches are meaningful.

### 6. Kickoff Role & Approach (Python + data gaps)
- Kickoff players report `boost_used = 0` because the adapter never updates `boost_amount` during the kickoff dash (the exported values stay at 33 until ~26s). That invalidates the speedflip heuristic (`boost_used >= 25`), so every approach defaults to FAKE/DELAY.
- `movement_start_time` often stays `None` because player positions stay frozen at spawn (same root cause as movement metrics).

**Fixes**
1. Fix boost telemetry in the Rust adapter (the same actor update used for mid-match pickups must be wired to kickoff frames).
2. Once boost deltas exist, recalibrate `_classify_approach_type` thresholds using labelled kickoff samples (ballchasing exports or manual annotations).
3. Add regression tests that ingest a replay with known speedflip kickoffs and assert that the classifier returns SPEEDFLIP for the right players.

### 7. Player Fundamentals (Python event fan-out)
- Per-player data inherits the broken goal detection. Example: `player_1` records 1 goal (correct) while blue scorers are stuck at 0 because their goals never trigger.

**Fixes**
- Same as Section 1; once goal events are deduplicated and both nets are detected, per-player/team fundamentals will align with the header scoreboard.

## Proposed Remediation Plan
1. **Stabilize event detectors first.**
   - Patch `detect_goals` gating + threshold.
   - Rework touch dedupe and challenge filtering.
   - Expand boost pad catalog.
   - Add unit tests that exercise each detector against hand-crafted frame sequences.
2. **Repair the Rust adapter telemetry.**
   - Implement velocity/boost extraction for car actors.
   - Preserve actor state between frames instead of rebuilding from partial payloads.
   - Validate numeric ranges (positions ±4096/5120, linear velocity up to 2300 uu/s).
3. **Recalibrate analyzers after telemetry stabilizes.**
   - Review per-minute normalization once raw metric totals look sane.
   - Tune passing/challenge heuristics using labelled replays.
   - Revisit kickoff heuristics with real boost deltas.
4. **Add end-to-end golden tests.**
   - Store a known replay and assert that JSON + Markdown `fundamentals/boost/movement/etc.` match Ballchasing outputs within tolerance.
   - Include a small header-only case to keep degradation path working.

Once these blockers are cleared we can regenerate the Markdown dossier and re-verify against the RLCS replay.
