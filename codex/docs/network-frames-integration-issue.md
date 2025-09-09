# Network Frames Integration Issue — Rust Adapter + Boxcars

## Summary
- Goal: Produce per-frame ball and player state from `.replay` files so analyzers compute real metrics (movement, boost, positioning, passing, challenges, kickoffs, touches).
- Current state:
  - Header parsing works via Rust adapter (pyo3 + boxcars 0.10.6): player names/teams, map, team size, scores populate the report and UI.
  - Network frames count is non-zero for the provided replay.
    - Example: `net_frame_count('testing_replay.replay') == 14661`.
  - However, the exported per-frame structures have empty `players` arrays throughout (no car actors realized into player frames), causing analyzers to see zero data and emit zeros.

## Symptoms Observed
- Header path
  - Players: TempoH, DRUFINHO, ApparentlyJack, Snasski (teams BLUE/ORANGE) parsed from `PlayerStats`.
  - Map: EuroStadium_Dusk_P, Team Size: 2, Scores OK.
- Network path
  - `iter_frames()` returns a list of dict frames, length matching `net_frame_count`.
  - For every frame, `players` list is empty.
  - Therefore `normalize.build_timeline(...)` receives an empty player stream; analyzers degrade to zeros (by design).

## What The Rust Exporter Does Now
- Uses `boxcars::ParserBuilder::must_parse_network_data().parse()`.
- Tracks `new_actors` in each frame to map `actor_id -> object_name` via `replay.objects[object_id]` (e.g., contains substrings like `Ball_TA`, `Vehicle_TA`, `Car_TA`).
- For `updated_actors` per frame:
  - `Attribute::RigidBody` → stores ball position/velocity if object is ball; otherwise stores candidate car position/velocity.
  - `Attribute::ReplicatedBoost` → stores boost amount (scaled 0..255 to 0..100).
  - `Attribute::TeamPaint` → sets team (0/1) for the actor.
  - `Attribute::Demolish*` → marks demolition flags.
- Player mapping:
  - Builds stable `player_id`s by aligning car actors to header players within team (e.g., `player_0`, `player_1`), with fallback by field-half if `TeamPaint` missing.
- Emits per-frame dicts: `{ timestamp, ball: {position, velocity, angular_velocity}, players: [...] }`.

## Attempts and Results
- Relaxed car detection:
  - Initially filtered to `Car_TA`/`Vehicle_TA`; then relaxed to treat any non-ball `RigidBody` update as candidate car.
  - Result: Still no `players` entries in any frame for this replay.
- Aggregated actor inclusion:
  - Constructed `players` from the union of actors with any of: position (`RigidBody`), boost (`ReplicatedBoost`), or team (`TeamPaint`) updates.
  - Result: Still empty players arrays → implies we’re not capturing these updates for car actors under current mapping.
- Verified frames exist:
  - `net_frame_count` consistently returns 14661 for `testing_replay.replay`.
  - `iter_frames` returns a list with that many frames; `ball` is filled, `players` empty.
- Boxcars API access fixes:
  - Adjusted imports to use public re-exports (`boxcars::{Attribute, Vector3f, Frame, NewActor}`) since `network` module is private.

## Working Hypotheses
- Actor mapping gap:
  - Our `object_id -> object_name` mapping (via `replay.objects`) might not label certain car actors as expected for this replay/build, so we’re missing or misclassifying car actors.
  - Updates carrying car position might land on actors whose names don’t include `Car_TA`/`Vehicle_TA`, or the actor-to-class association requires consulting `replay.class_indices` / `replay.net_cache` rather than `replay.objects` directly.
- Attribute coverage gap:
  - Car kinematics may arrive under attributes beyond the generic `RigidBody` we’re watching (e.g., different tags in recent builds), so we miss car positions entirely.
- Version compatibility:
  - boxcars 0.10.x may parse the replay header fine but not emit expected car updates for this build’s network stream semantics, even though frame count is large.

## Information Needed
- Canonical method (for current Rocket League build) to map `actor_id` → entity type (ball vs car) using boxcars outputs:
  - Whether to derive from `replay.objects[object_id]` alone, or to traverse `class_indices` / `net_cache` to resolve canonical class names.
- Confirm which attribute(s) carry car transform/velocity in the current build:
  - Is `Attribute::RigidBody` still the correct path for car position/velocity, or do we need to watch additional attribute tags?
- Best practice for team derivation in network:
  - Is `TeamPaint.team` sufficient/consistent for car actors, or should we infer via PRI/Reservation or another attribute stream?
- Example code or mapping table (actor/object names → roles) known to work with boxcars for modern replays.

## Proposed Fix Plan (Once We Have Answers)
1. Correct actor classification:
   - Build a robust actor registry using `new_actors` + `class_indices`/`net_cache` resolution to canonical class names; classify ball vs car using explicit lists.
2. Expand attribute handling:
   - Handle all attribute tags that deliver car transforms/velocities/boost/team/demolish (not only `RigidBody`, `ReplicatedBoost`, `TeamPaint`).
3. Stable identity mapping:
   - Link car actors to header `PlayerStats` using team and, if available, `UniqueId`/PRI to map to platform IDs; keep `player_id` stable (`player_0`, …) for analyzers.
4. Validation harness:
   - Add a debug export (optional CLI) that dumps, for N frames, the set of `updated_actors` with object names and attribute tags to quickly verify coverage in future builds.
5. Fallback path:
   - If boxcars cannot decode current network stream for this replay build, integrate rrrocket (or a known‑good alternative) locally to produce the required per‑frame dicts behind the same adapter API.

## Current Workarounds and Limitations
- Header-only coaching is insufficient; analyzers require per-frame data.
- We can partially use header goals to populate fundamentals as a fallback, but detailed metrics (movement/boost/positioning/passing/challenges) won’t be meaningful without frames.

## Repro Steps (Local)
- Build Rust module: `cd parsers/rlreplay_rust && maturin build -r && pip install target/wheels/*.whl`
- Check network frames exist:
  - Python: `import rlreplay_rust; print(rlreplay_rust.net_frame_count('testing_replay.replay'))  # → 14661`
- Generate report with rust adapter preferred:
  - `python -m rlcoach.cli analyze testing_replay.replay --adapter rust --out out --pretty`
- View report:
  - `python -m rlcoach.ui view out/testing_replay.json --player "ApparentlyJack"`
- Expected vs actual:
  - Players appear in header/UI, but metrics remain zeros due to empty `players` arrays in frames.

## References
- Plan: `codex/Plans/rlcoach_implementation_plan.md` — Parser Layer + Normalization + Analysis requirements.
- Current adapter code:
  - Rust: `parsers/rlreplay_rust/src/lib.rs`
  - Python shim: `src/rlcoach/parser/rust_adapter.py`
  - Report: `src/rlcoach/report.py`
  - Normalization: `src/rlcoach/normalize.py`
- Tests validate the interface but not full network fidelity yet.

---

If you can provide the mapping guidance (actor classification and the exact attributes to watch for car kinematics in current builds), I’ll implement the exporter to emit full per‑frame player+ball state and wire analyzers to real data end‑to‑end.

