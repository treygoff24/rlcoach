---
# network-frames-integration-issue Diagnosis and Resolution

## Issue Summary
- When analyzing a Rocket League replay (e.g., a ballchasing.com download), the Rust adapter returns a non‑zero network frame count and emits `ball` data, but **every frame’s `players` array is empty**, so analyzers receive no player state and output zeros. This behavior is captured in *Network Frames Integration Issue — Rust Adapter + Boxcars* under “Current state,” “Symptoms,” and “Expected vs actual.” fileciteturn0file2
- The project architecture expects a **pluggable parser** producing both header and network frames; the Rust adapter is intended to provide real frames (boxcars), with fallback to a header‑only `null` adapter. fileciteturn0file0
- The **adapter documentation** still describes a stubbed frame iterator and explicit degradation to header‑only (quality warnings), which is now **out of sync** with the boxcars‑backed behavior described in the issue, contributing to confusion during integration. fileciteturn0file1 fileciteturn0file2

## Technical Diagnosis
- **Primary root cause — actor classification gap:** The Rust exporter tracks `new_actors` / `updated_actors` and tries to map `actor_id → object_name` via `replay.objects[object_id]`. For this replay/build, that mapping isn’t identifying **car actors**, so candidate car updates are never recognized and `players` remains empty. This aligns with the “Working Hypotheses: Actor mapping gap” in the issue doc. fileciteturn0file2
- **Secondary root cause — attribute coverage gap:** Car kinematics may not arrive solely via the `RigidBody` attribute; if other attributes carry transforms/velocity for this build, they’re **not being consumed**, leaving player state unpopulated. This aligns with “Working Hypotheses: Attribute coverage gap” in the issue doc. fileciteturn0file2
- **Version/documentation drift:** The README positions `rust` as a richer adapter with network frames, while the adapter doc still frames it as a stub that may return `None` for network data (and notes quality warnings). The current issue confirms **real frames exist** but `players` is empty — indicating **the adapter is active but incomplete**, not absent. This mismatch can mislead debugging flow. fileciteturn0file0 fileciteturn0file1 fileciteturn0file2
- **Effect on pipeline:** Because `normalize.build_timeline(...)` receives frames with empty `players`, analyzers degrade to zeros “by design,” matching the issue’s observation. This explains the end‑to‑end “header looks fine, metrics are zeros” symptom. fileciteturn0file2

## Resolution Steps
1. **Harden actor classification in the Rust adapter.**  
   Update `parsers/rlreplay_rust/src/lib.rs` to resolve canonical class names for actors using not only `replay.objects` but also class indices / net cache as suggested in “Information Needed,” then classify **ball vs car** via explicit allow‑lists (e.g., canonical class names containing `Ball_TA`, `Vehicle_TA`, `Car_TA`, etc.). fileciteturn0file2  
   *Sketch (Rust):*
   ```rust
   // Pseudocode / sketch: illustrates structure, not exact boxcars APIs
   struct ActorInfo {
       class_name: String,
       is_ball: bool,
       is_car: bool,
       team: Option<u8>,
       boost: Option<f32>,
       last_pos: Option<[f32;3]>,
       last_vel: Option<[f32;3]>,
   }

   // Build once, then update per frame
   let mut actors: HashMap<u32, ActorInfo> = HashMap::new();

   fn canonical_class_name(replay: &Replay, object_id: u32) -> String {
       // Prefer class indices / net cache if available; otherwise fallback to objects[] text
       // (Exact API depends on boxcars; this is conceptual.)
       resolve_class_name_via_net_cache(replay, object_id)
           .or_else(|| resolve_class_name_via_class_indices(replay, object_id))
           .unwrap_or_else(|| replay.objects[object_id as usize].clone())
   }

   fn classify(class_name: &str) -> (bool, bool) {
       // Make allow-lists configurable for future builds
       let is_ball = class_name.contains("Ball_TA");
       let is_car  = class_name.contains("Vehicle_TA") || class_name.contains("Car_TA");
       (is_ball, is_car)
   }

   // On NewActor(frame): register
   for new_actor in frame.new_actors.iter() {
       let class_name = canonical_class_name(&replay, new_actor.object_id);
       let (is_ball, is_car) = classify(&class_name);
       actors.insert(new_actor.actor_id, ActorInfo {
           class_name, is_ball, is_car, team: None, boost: None,
           last_pos: None, last_vel: None
       });
   }
   ```

2. **Expand attribute handling to capture car kinematics/team/boost.**  
   In the per‑frame loop, handle **all relevant attributes** that deliver car transforms/velocity/boost/team/demolish — at minimum keep `RigidBody`, `ReplicatedBoost`, `TeamPaint`, and demolition flags, and optionally include additional transform carriers if present in boxcars for the current build (to cover attribute drift). This step implements the issue doc’s “Expand attribute handling” plan. fileciteturn0file2  
   *Sketch (Rust):*
   ```rust
   // On UpdatedActor(frame): update state
   for upd in frame.updated_actors.iter() {
       if let Some(info) = actors.get_mut(&upd.actor_id) {
           for attr in upd.attributes.iter() {
               match attr {
                   Attribute::RigidBody(rb) => {
                       if info.is_ball || info.is_car {
                           info.last_pos = Some([rb.location.x, rb.location.y, rb.location.z]);
                           info.last_vel = Some([rb.velocity.x, rb.velocity.y, rb.velocity.z]);
                       }
                   }
                   Attribute::ReplicatedBoost(boost) => {
                       if info.is_car { info.boost = Some((boost.amount as f32) * (100.0/255.0)); }
                   }
                   Attribute::TeamPaint(tp) => {
                       if info.is_car { info.team = Some(tp.team as u8); }
                   }
                   // Optionally also handle other transform carriers if exposed by boxcars
                   _ => {}
               }
           }
       }
   }
   ```

3. **Emit `players` by materialized car actors each frame.**  
   After processing updates for a frame, build `players` from actors with `is_car == true`, projecting stable fields (`position`, `velocity`, `team`, `boost`) and mapping to stable `player_id` indices per team (e.g., `player_0`, `player_1`) as already envisioned in the issue doc (“Stable identity mapping”). fileciteturn0file2  
   *Sketch (Rust)*
   ```rust
   let mut players_vec = Vec::new();
   for (actor_id, info) in actors.iter() {
       if info.is_car {
           if let Some(pos) = info.last_pos {
               players_vec.push(json!({
                   "actor_id": actor_id,
                   "team": info.team.unwrap_or(255),
                   "position": pos,
                   "velocity": info.last_vel,
                   "boost": info.boost,
               }));
           }
       }
   }
   emit_frame(json!({ "timestamp": ts, "ball": ball_json, "players": players_vec }));
   ```

4. **Add a debug harness to verify coverage and future‑proofing.**  
   Implement a CLI flag (e.g., `--debug-net N`) that dumps, for the first *N* frames, the set of `updated_actors` with resolved class names and attribute tags. This mirrors the issue doc’s “Validation harness” and will quickly reveal when car actors or attributes drift in future builds. fileciteturn0file2

5. **Align Python shim and docs with current behavior.**  
   - Update `src/rlcoach/parser/rust_adapter.py` so `parse_network(...)` consistently returns the new per‑frame dicts; ensure graceful degradation remains (quality warnings) only when the Rust core is truly unavailable. fileciteturn0file1  
   - Refresh `codex/docs/parser_adapter.md` to reflect the boxcars‑backed implementation (not “stub only”), keeping the documented quality warnings as the *fallback* path. fileciteturn0file1 fileciteturn0file2

6. **Integration tests to prevent regressions.**  
   Add tests that: (a) assert `net_frame_count(replay) > 0`, (b) assert that **within the first K active frames** at least one `players` entry exists, and (c) validate basic invariants (e.g., team ∈ {0,1}, 0≤boost≤100). Place these under `tests/` per project structure. fileciteturn0file0

7. **Fallback implementation (if boxcars limitations persist).**  
   If, after the above, car actors still don’t materialize for this replay/build, introduce a local alternative (e.g., rrrocket) behind the same adapter API as already contemplated in the issue doc’s “Fallback path.” Keep the JSON contract identical so analyzers remain unchanged. fileciteturn0file2

## Error Handling and Assumptions
- **Assumptions**
  - Boxcars exposes enough metadata (objects, class indices, or net cache) to resolve canonical class names needed for reliable car/ball classification. If not, the fallback in Step 7 becomes mandatory. fileciteturn0file2
  - The analyzers require only per‑frame `ball` and `players[*]` with `position`, `velocity`, `team`, `boost`, and demolition flags; no additional per‑attribute fidelity is required to restore non‑zero metrics. (Consistent with the project’s pipeline expectations.) fileciteturn0file0
- **Uncertainties / Open Questions**
  - Which **exact** attribute(s) in current builds carry car transforms if `RigidBody` is absent or incomplete? Confirmation is called out in “Information Needed.” fileciteturn0file2
  - What is the **canonical mapping** path for `actor_id → class` in modern replays: purely from `objects`, or via `class_indices` / `net_cache`? The issue doc asks for this specifically. fileciteturn0file2
  - Is `TeamPaint.team` sufficient for team identification across all modes, or should PRI/Reservation be consulted? Also listed under “Information Needed.” fileciteturn0file2
- **Proposed Actions to Resolve Uncertainties**
  - Use the new debug harness (Step 4) to inspect the first 150–300 frames and record: (i) actor class names seen with transform‑like attributes, (ii) presence/absence of `RigidBody` vs alternates, and (iii) whether team/boost attributes appear on the same actors. fileciteturn0file2
  - If attributes differ, extend the match arms to include the confirmed transform tags, keeping the code table‑driven (allow‑lists) to avoid brittle string matching. fileciteturn0file2

## References
- **README.md — Project overview, parsers, and pipeline.** Establishes the pluggable adapter layer (`null`, `rust`) and overall architecture (ingest → parser → analysis → report/UI). fileciteturn0file0
- **parser_adapter.md — Rust adapter build/usage & degradation behavior.** Documents pyo3 module surface, Python shim, and the intended graceful fallback with explicit quality warnings (currently out of sync with boxcars integration). fileciteturn0file1
- **network-frames-integration-issue.md — Detailed symptoms, hypotheses, and proposed fixes.** Confirms boxcars‑backed header parsing works, frames exist (`net_frame_count == 14661`), but `players` is empty; outlines actor/attribute gaps and a fix plan including a validation harness and rrrocket fallback. fileciteturn0file2

---
