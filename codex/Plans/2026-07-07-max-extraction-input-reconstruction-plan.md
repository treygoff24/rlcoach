# Maximum Extraction & Input Reconstruction Plan

> Goal: make rlcoach's parser+pipeline extract and expose *everything* a Rocket League replay contains — culminating in reconstructed controller inputs, success/failure mechanic grading with confidence scores, per-event coaching timelines, and a published validation methodology. Target user: a GC1 player climbing to SSL. Open-source ambition: the parser (+ input reconstruction) becomes the best public RL replay toolchain, with *measured* accuracy instead of folklore thresholds.

**Status:** REVISED r1 — dual adversarial review complete (opus plan-reviewer + codex safe, both FIX-THEN-EXECUTE); all P1/P2 findings folded in below
**Date:** 2026-07-07
**Prereq reading:** `MECHANICS_DETECTION.md` (esp. 30Hz analysis), research findings summarized in §1.

---

## 0. Current state (one paragraph)

The pipeline (boxcars 0.10.7 → pyo3 → normalize → events → 12 per-replay analyzers + 3 cross-replay modules → JSON/markdown report) already detects 26 mechanic types, classifies kickoffs, and computes the full positioning/boost/movement stat suite; 598 tests pass and 99.5% of a 202-replay corpus parses. But detectors run on *reconstructed* signals (Euler-diffed rotation rates) while the parser silently drops the real ones (car angular velocity, inputs, component vectors); success-vs-failure discrimination doesn't exist; the per-event mechanic timeline is computed then discarded (`analysis/__init__.py:315`); and no detector has ever been validated against ground truth.

## 1. Research findings this plan is built on

From source-level due diligence (Codex lanes, 2026-07-07; boxcars @ `9450615`, RLCarInputSolver @ `b31efbf`):

| # | Finding | Consequence |
|---|---------|-------------|
| R1 | Car angular velocity is decoded per frame and dropped for cars (`parsers/rlreplay_rust/src/lib.rs:1221`, kept only for ball) | Sprint 0 emits it; detectors stop Euler-diffing |
| R2 | `TAGame.Vehicle_TA:ReplicatedThrottle`/`ReplicatedSteer` (Byte 0–255, ~128 center) and `bReplicatedHandbrake` (Bool) are in the stream; our dispatch drops them at the `_ => {}` catch-all (`lib.rs:1482`) | Driving inputs are *free* — extract, don't infer |
| R3 | `TAGame.CarComponent_Dodge_TA:DodgeTorque` **and** `DodgeImpulse` (Vector3f), `TAGame.CarComponent_DoubleJump_TA:DoubleJumpImpulse` (Vector3f), `TAGame.CarComponent_AirActivate_TA:AirActivateCount` (Int) all exist | Flip *direction* is replicated ground truth; the solver localizes timing, not direction |
| R4 | `TAGame.CarComponent_TA:ReplicatedActive` is a u8 **transition counter** (odd=active best interpretation; MEDIUM confidence, SDK-shape + fixture-sequence inferred) | Needs empirical validation early in Sprint 0 (V-0 below) |
| R5 | `ReplicatedRBState.sleeping`: when sleeping, linear/angular velocities are **absent** from the stream | Emit `sleeping`; treat absent velocities as "at rest," never zero-fill silently |
| R6 | **RecordFPS is not universally 30** — boxcars fixtures include 60 and 120 (2025-09-17 fixture records at 120) | Never hardcode 30Hz; scan our corpus + Trey's own replays; at 120fps input reconstruction gets ~4× better |
| R7 | StatEvent carries only Goal/Save/EpicSave/KO_Death (+`-1` sentinel) in observed fixtures | Good for save/epic-save labels; **not** general touch attribution — keep proximity+impulse touch detection |
| R8 | `WeldedInfo` is Rumble spike-attach state; inactive in standard soccar | **Correction to earlier analysis:** not a dribble signal; deprioritize |
| R9 | RLCarInputSolver: 670 LOC MIT core, hard-depends on RocketSim/Bullet (wheel traces for ground detection, mutated friction solver for steer), tick-quantized (`int(dt/RL_TICKTIME)` — 0.033s float-truncates to 3 ticks = 25% force error), stateless by design, assumes max-magnitude flip inputs, partial cancels TODO | **Reimplement ideas, don't port.** Keepers: inverse aerial-control math (Sam Mish model), dodge-impulse inversion, flip z-damping signature |
| R10 | Codex-recommended architecture: stateful 120Hz tick-lattice estimator — per recorded interval, search candidate substep events, forward-fit against next observed frame, emit confidence | The solver and the resimulation validator are the same machinery (rocketsim-rs) |

---

## 2. Sprint map & dependencies

```
S0 Parser signal completion ──┬─→ S1 Input solver spike ──GATE──→ S2 Detector rebuild ──→ S3 Attempt/failure modeling
                              │                                            │
                              └─→ V1 Resim harness (co-built with S1)      └─→ S4 Event timeline surfacing
V0 ReplicatedActive validation (inside S0)
V2 BakkesMod logger / V3 RLBot corpus (parallel track, any time after S0)
H  Hygiene (anytime; H1 before any new fixture work)
```

Sprints are sized for solo+agents work; each ends with the full gate (`ruff` + `black --check` + `pytest`; `cargo test` + `cargo clippy` for Rust work).

---

## 2b. Execution model & staffing

**Model families permitted on this project: Claude (Fable / Opus / Sonnet) and OpenAI Codex. No other lanes** (no Cursor/Grok/Droid/etc.).

| Role | Who | Does | Never does |
|---|---|---|---|
| Orchestrator | **Fable (main session)** | Scoping, work-package briefs, gate adjudication, merge decisions, coordinator-level verification, running the canonical gate after every wave, talking to Trey | Mechanical implementation, bulk reading of diffs/logs (delegated), anything that pollutes judgment context |
| Wicked-core engineering | **Fable subagents** (spawned sparingly) | The judgment-dense engineering cores: tick-lattice estimator design + its hairiest implementation (S1.2), decision-gate analysis writeup, thorniest debugging escalations (stuck-twice rule) | Routine implementation, boilerplate, test scaffolding |
| Primary implementation engine | **Codex headless `/goal` runs** (babysat via periodic check-ins where possible) | Bounded work packages per sprint; each run's prompt REQUIRES: (a) load the **rust-engineer skill** before starting — itself AND any subagents it spawns — for all Rust work packages; (b) use its native subagents for implementation and internal review→fix loops *before* declaring the goal complete; (c) end with a structured completion report (files touched, tests added, gate output, residual risks) | Merging to main, schema-contract decisions without orchestrator sign-off, expanding scope beyond the brief |
| Substantive review lanes | **Opus subagents** | Adversarial review of Codex-authored waves (cross-family), spec/brief review before dispatch, plan review | — |
| Mechanical/parallel work | **Sonnet subagents** | Corpus scans (S0.5/V0), golden pinning + regeneration, test scaffolding, doc moves (H-track), verification sweeps of on-disk state after fan-outs | Design decisions |

**End-of-phase review→fix loop (every sprint/wave, 1–3 iterations):**
1. Author lane completes (usually Codex).
2. Cross-family adversarial review — Opus reviews Codex-authored work; Codex (`safe`/read-only) reviews Claude-authored work. Findings ranked P0–P3.
3. Author lane fixes P0–P2; P3s at orchestrator discretion.
4. Re-review only the fixes. Stop when clean, or after 3 iterations — residuals escalate to the orchestrator for a judgment call, never silently dropped.
5. Orchestrator runs the canonical gate (`ruff` + `black --check` + `pytest` (+ `cargo test`/`clippy`)) at coordinator level and verifies on-disk state directly — subagent/child "done" claims are not trusted (known failure mode: trailing call-site updates and test additions get cut off).

**Context hygiene rules for the orchestrator:** consume structured completion reports, not raw diffs (except where the diff *is* the judgment call); one work-package brief per Codex run with explicit file ownership; no two concurrent lanes owning the same files; commits between waves so each lands reviewable (per Trey's commit authorization each time).

**Per-sprint staffing:**
- **S0**: Codex `/goal` for Rust extraction + Python threading (rust-engineer skill mandatory); Sonnet for the RecordFPS corpus scan (S0.5) and V0 correlation study; Opus↔Codex review loop; Fable verifies boundary contract.
- **S1**: Fable subagent designs the estimator core + fit objective (S1.2); Codex implements solver components, calibration oracle, and V1 harness against that design; Opus reviews; **Fable (main) adjudicates the decision gate** — this is the sprint where orchestrator judgment matters most.
- **S2**: Codex `/goal` waves per detector family (primitives → flip family → ball-interaction family); Sonnet pins pre-rebuild goldens and produces the count-diff report; Opus reviews each wave.
- **S3**: Taxonomy = Trey + Fable (conversation, then frozen); Codex implements attempt state machines; Opus + Codex cross-review (inference-heavy code gets the full 3-iteration loop).
- **S4**: Codex for schema/report/API threading; Sonnet for markdown goldens.
- **V2 (BakkesMod plugin)**: Codex `/goal` in a separate mini-repo (C++); babysat.
- **V3 (RLBot corpus)**: Codex authors bot scripts; Sonnet wires fixtures into CI.
- **H-track**: Sonnet.

---

## 3. Sprint 0 — Parser signal completion (foundation; unconditional value)

Extract everything the file already carries. All items land behind the existing frame-dict boundary (`lib.rs:1489-1893`) → `rust_adapter.py` → `parser/types.py` → `normalize.py` → schema.

> **⚠ Routing reality (review finding P1-1):** most new signals do NOT fall at the `_ => {}` catch-all. boxcars maps them to *generic* variants that hit **existing, load-bearing arms**: `ReplicatedThrottle`/`ReplicatedSteer` → `Attribute::Byte` (existing arm at `lib.rs:1289` currently routes ALL bytes to component-active logic); `DodgeTorque`/`DodgeImpulse`/`DoubleJumpImpulse` → `Attribute::Location` (existing arm at `lib.rs:1255` feeds the **boost-pad registry** and marks dodge actors active). Only `bReplicatedHandbrake` (Boolean) is genuinely unhandled. All new extraction MUST dispatch by object name (`upd.object_id` → `objects.get`, pattern at `lib.rs:1139`/`1458`) *inside* those arms. Pad-registry behavior and existing activation-edge semantics must be regression-protected — a naive Location-arm refactor regresses pad detection and/or fabricates activation edges.
>
> **Also (P1-2):** the comment at `lib.rs:1479-1481` claiming boxcars doesn't expose Jump/Dodge/Throttle/Steer/Handbrake is **false** (boxcars `data.rs:103-107, 238-240, 253-254`). Delete it as part of S0.3 — do not defer to it.
>
> **Sequencing:** S0.1–S0.7 share `lib.rs` dispatch and `normalize.py` player construction. They run **sequentially in ONE Codex lane**, not fanned out.

### S0.1 Car angular velocity
- Rust: store per-car `angular_velocity` at `lib.rs:1237-1250` (already computed at `:1221`); emit in player dict (`lib.rs:1632-1697`).
- Python: add `angular_velocity: Vec3 | None` to `PlayerFrame` (`parser/types.py:165`); populate at PlayerFrame construction (`normalize.py:~694`, not `_parse_rotation`); expose to analyzers.
- Acceptance: real-replay smoke shows nonzero car ang-vel during flips; cheap physics invariant wired into the smoke test: |ang-vel| ≤ ~5.5 rad/s corpus-wide (V5 pull-forward); goldens updated.

### S0.2 Rigid-body `sleeping` (additive only)
- Emit `sleeping: bool` on ball and cars. **Keep `velocity`/`angular_velocity` non-optional Vec3 with zero-fill** (review P2-11: making them None ripples through every analyzer reading `ball.velocity`); `sleeping` + a provenance tag carry the "absent from stream" information (R5).
- Augment (don't replace) the `z <= 18.0` ground test (`lib.rs:1683`) with `sleeping` and car-local-up contact classification downstream. Full wheel-contact classification is S1 territory.

### S0.3 Driving inputs: throttle / steer / handbrake
- Extend the **existing `Attribute::Byte` arm** with object-name dispatch: `TAGame.Vehicle_TA:ReplicatedThrottle`/`ReplicatedSteer` route to per-player input state; all other bytes keep current component-active behavior. Add a Boolean arm for `bReplicatedHandbrake`.
- Emit per player per frame: `throttle`, `steer`, `handbrake` normalized to `[-1,1]`/bool, PLUS raw bytes under `_raw` (128-center convention is medium-confidence — R2).
- Delete the stale `lib.rs:1479-1481` comment (P1-2).

### S0.4 Component state: extend, don't re-add
- **Already implemented (extend, don't re-derive):** parity `%2==1` activation for jump/dodge/double-jump (`lib.rs:1295`); quaternion rotation (`lib.rs:1248, 1648-1660`); `is_jumping/is_dodging/is_double_jumping` on `PlayerFrame` (`parser/types.py:182`). V0 below validates this EXISTING behavior.
- New: `ReplicatedBoost` (grant_count + amount) alongside legacy `ReplicatedBoostAmount`; `boost_active` from the boost component's parity; emit **raw counters** per component alongside derived booleans (hedges R4).
- New: `DodgeTorque`, `DodgeImpulse`, `DoubleJumpImpulse` vectors via object-name dispatch inside the existing `Location` arm per the routing warning above; `AirActivateCount` (Int) and `bReplicatedHandbrake` (Boolean) need **new** arms — no `Int`/`Boolean` arm exists today. Surface as first-class `component_events` (activation edges + vectors), a **parser-authored event stream** parallel to `parser_touch_events`, not report-schema fields.
- New: `StatEvent`s as parser-authored events (save/epic-save labels for V-tier, R7). `Impulse`: investigate corpus presence first; LOW confidence; build nothing on it until confirmed.

### S0.5 Frame rate: declared vs measured (reframed per P2-5/P2-6)
- Measured rate already exists end-to-end as `recorded_frame_hz` (`report.py:355` → schema → `ui.py:41`, `report_markdown.py:162`) — reuse it, don't duplicate.
- New: surface header `RecordFPS` as `declared_record_fps` via the **header path** (not per-frame `_parser_meta`); document declared-vs-measured distinction.
- Audit residual 30Hz assumptions: `NetworkFrames.sample_rate=30.0` default (`parser/types.py:149`) + analyzer constants.
- Corpus scan (V-0a): RecordFPS + measured-rate distribution across the 202-replay corpus + Trey's own replays. If modern ranked replays record >30fps, S1 design consumes measured rate per replay.

### S0.6 Fixture builders + tests + schema
- Extend `tests/fixtures/builders.py`: `Rotation` (with quaternion), `angular_velocity`, component flags/counters/events, input channels; trajectory helpers (e.g., `with_flip_at(t, direction)`).
- **Byte-level parsing is not synthetically testable** (builders can't emit boxcars binaries — P2-9): every new signal MUST add an assertion to the CI-running committed-fixture smoke (`tests/parser/test_rust_adapter_smoke.py` on `Replay_files/0925.replay`), after confirming the fixture actually contains that attribute; pad-registry regression tests required for the Location-arm change.
- Schema scope (P3): `replay_report.schema.json` is the **aggregated report only** — per-frame fields do NOT go in it. Only `declared_record_fps`, `signal_provenance` (metadata has `additionalProperties:false` — schema edit + golden regen required), and later S4 event blocks.

### S0.7 Frame delta (NEW — review P1, S1 prerequisite)
- Emit boxcars `Frame.delta` (`boxcars src/network/models.rs:233-240`) per frame; thread through `rust_adapter.py` and `normalize.py`. S1 tick conversion consumes **accumulated deltas**, never rounded timestamps or a measured-FPS constant.

### V0 — ReplicatedActive empirical validation (inside S0)
- Correlate existing parity transitions for jump/dodge components against kinematic signatures (z-vel impulse, ang-vel steps) across ≥20 corpus replays. Publish agreement rate in the PR description. If parity interpretation fails, fall back to "any counter change = activation edge" (still event-grade).

**Sprint 0 exit criteria:** every R1–R7 signal + frame delta visible in `iter_frames` output on a real replay; V0 agreement number known; pad-registry regression suite green; smoke-fixture assertions in CI for each new signal; goldens/schema updated; gate green.

> **✅ S0 COMPLETE 2026-07-07** (branch `feat/sprint0-parser-signals`, 10 commits, merged to main). All exit criteria met; gate re-run at orchestrator level: ruff/black clean, pytest 656, cargo test 22, clippy clean. Opus adversarial review: FIX-THEN-MERGE → 1 iteration → CLEAN (P0:0, P1:1 contract-docs, P2:1, P3:4; all fixed or dispositioned).
>
> **Results recorded:**
> - **V-0a**: entire 202-replay corpus (2025-09→2026-01) is 30fps — declared 202/202 = 30.0 exactly, measured max 30.007. Zero >30fps replays. Gate criterion 2's ±1-tick branch is moot for this corpus; the 30Hz fallback (correct-interval ≥98%) is the operative timing criterion.
> - **V0**: parity (odd=active) HOLDS — forward agreement jump 84.7% (n=6244 edges), dodge 79.0% (n=7522), double-jump 67.1% (n=2471, dodge-like kinematic signature; vz-only was a methodology artifact). Inverse: kinematics-only produces 2.3–17× more candidates than real edges (parity does real disambiguation). Keep MEDIUM confidence; do not downgrade.
> - **DURABLE CONTRACT (review P1)**: `component_events.active` is an instantaneous parity sample, NOT a debounced edge — sub-frame activate+deactivate is invisible to it (0925: 119 double_jump_impulse vectors vs 43 active:true edges). Raw counters (u8, deltas mod 256) + per-activation vector events are the contract S1 builds on; derived booleans are convenience. Gate criterion 1's "component edges as ground truth" = edges reconstructed from raw-counter deltas + vector events.
> - `dodge_impulse` extraction UNVERIFIED (absent from all committed fixtures) — build nothing on it.
> - `Frame.delta` faithfully surfaces boxcars values incl. zeros (7/8621 on 0925, max gap 0.19s) — S1 accumulation must tolerate delta==0 and large gaps.
> - Latent bug fixed in passing: ball angular velocity now correctly ÷100-scaled (was ~100× large; nothing consumed it).

---

## 4. Sprint 1 — Input reconstruction spike (tick-lattice estimator) → DECISION GATE

Reimplement RLCIS *ideas* in Rust (R9/R10), scoped to what replays don't replicate: aerial pitch/yaw/roll, sub-frame flip timing, flip cancels, stalls. Everything else is read from S0 signals.

### S1.0 Discovery pre-task (NEW — review P1; timeboxed, blocks S1.2)
- **Build system**: there is no Cargo workspace today (`Makefile` builds via `cd parsers/rlreplay_rust` + maturin). Create a root/`parsers/` workspace accommodating `rlreplay_rust` + new `rlinput`; verify maturin + `make rust-dev` + CI still work.
- **rocketsim-rs verification**: pin an exact version; verify API surface hands-on (arena init, per-tick stepping, set/get full car state); document which RL physics patch it targets.
- **Collision-mesh assets**: RocketSim requires arena collision meshes at init — resolve sourcing, size, licensing, and CI availability *before* S1.2 (review P2-10). If untenable for CI, the simplified air-phase integrator becomes the CI objective and full-sim runs stay local.
- **Physics-patch drift**: map corpus replay builds → rocketsim compatibility; V1 metrics are segmented by replay build so version mismatch doesn't contaminate solver-accuracy numbers.

### S1.1 Crate layout
- New crate `parsers/rlinput/` in the S1.0 workspace (NOT inside `rlreplay_rust`): consumes normalized frame streams, depends on `rocketsim-rs` (feature-gated `sim` feature so the base parser crate stays dependency-light for open-source consumers).
- License note: MIT throughout; preserve RLCIS/RocketSim MIT notices for derived constants/formulas.

### S1.2 Estimator architecture
- **Stateful per-player tracker**: jump state, flip availability, flip start tick, cancel state, boost active, contact state — seeded by S0 component events (dodge activation edge tells us *which* interval contains the flip; `DodgeTorque` tells us direction — the solver only localizes timing within the interval and recovers analog air-control).
- **Tick lattice**: convert recorded intervals to integer 120Hz ticks from **accumulated S0.7 frame deltas** with proper rounding (never float-truncated timestamps — R9). Accumulate **per contact-free segment**, not globally — f32 deltas drift over a ~9000-frame match. Interval of N ticks → candidate event placements at each tick.
- **Segmentation (NEW — review P1)**: the solver operates on **contact-free segments**. Segment boundaries: ball touches, suspected car-car contact, demolitions/respawns (parser already emits demo events; add respawn edges to the normalized model), ground/wall contact transitions. Intervals crossing a boundary get ambiguity flags, are excluded from gate metrics, and are reported in a coverage statistic (so exclusion can't hide).
- **Forward-fit**: for candidate input hypotheses, forward-simulate the interval (rocketsim-rs; fallback: simplified rigid-body integration for air-only segments) and score against the observed next frame. Best fit wins; fit error → confidence.
- **Inverse aerial control** (Sam Mish model, from RLCIS `AirSolver.cpp:9-46`): closed-form recovery of pitch/yaw/roll from angular acceleration for non-flip air segments; validate against forward-fit on sample intervals.
- **Output boundary (review P2)**: `InputTimeline` per player is a **parallel per-player stream** attached at the normalized-timeline level (documented in `parser/types.py`), NOT extra fields stuffed into `PlayerFrame`. S2 consumes it through this documented surface; per-channel tags `{source: replicated|solved|inferred, confidence: 0-1}` + ambiguity flags (`collision_suspected`, `possible_partial_cancel`…).

### S1.3 Calibration oracle (built-in accuracy measurement)
- Run the solver **blind** on channels with replicated ground truth — throttle, steer, handbrake, boost-active, jump edges are withheld from the solver's inputs on calibration runs (review P1: reading them in S0 and "predicting" them is tautological). Score per replay/per player. Calibrates trust for unreplicated channels; ships as a public accuracy artifact.

### V1 — Resimulation harness (co-built; same machinery)
- Batch runner: for every **contact-free segment** of every corpus replay, resimulate with reconstructed inputs; report positional/rotational error distributions at 1-frame horizon vs a zero-input baseline, **segmented by replay build**; publish segment coverage alongside.

### DECISION GATE (end of Sprint 1)
**Threshold freeze protocol (review P1-3):** all numeric thresholds below are provisional until S1 kickoff, at which point they are frozen in this document *before any solver results are viewed*. Post-hoc changes require written justification recorded here and invalidate any already-viewed results for adjudication.

> **🔒 THRESHOLDS FROZEN 2026-07-07 at S1 kickoff** (V0 in hand: parity holds 84.7/79.0/67.1; zero solver results viewed). Binding interpretations: **criterion 1** ground truth = activation edges reconstructed from raw-counter deltas (mod 256) + per-activation vector events (`dodge_torque`, `double_jump_impulse`), NOT the `active` parity boolean (S0 review P1: parity sampling undercounts sub-frame activations up to ~64%); grade is interval-level per V0's MEDIUM-confidence parity. **Criterion 2** operative branch = the 30Hz fallback (correct-interval ≥98% + criterion 4) — V-0a found zero >30fps replays in the 202-replay corpus. All numeric values below stand as written. Any change from here on gets a dated written justification in this block.

Evaluate on a **holdout set** of ≥15 corpus replays never used during S1 development (+ all high-FPS replays found in S0.5), with the solver run **unseeded** (no component-event priors) so component activation edges are legitimate held-out ground truth:
1. **Flip detection (unseeded)**: interval-level flip presence vs component edges — F1 ≥ 0.95. Ground-truth grade is V0-contingent: freeze this criterion at S1 kickoff *with V0's result in hand* — if V0 downgraded parity to "any counter change = activation edge," this criterion is interval-grade accordingly.
2. **Flip timing**: on ≥60fps replays (if S0.5 finds any): solver flip tick within ±1 tick of the activation edge for ≥90% of flips. 30Hz-only fallback (review P1-4): flip assigned to the correct recorded interval ≥98% + criterion 4 below.
3. **Blind replicated channels**: boost/jump edge F1 ≥ 0.95; throttle sign agreement ≥90% of frames outside deadzone (|raw−128| > 13); steer within ±0.15 normalized for ≥85% of frames.
4. **Resim fit**: median 1-frame positional error on contact-free air segments ≤ 0.25× the zero-input baseline median (ratio, not absolute — baselines computed on a 10-replay dev set and frozen with the protocol above); p95 ≤ 0.5× baseline p95; no replay-build segment worse than 2× the corpus median (replaces "no blow-ups").
5. **Coverage**: ≥80% of air segments solvable at confidence ≥0.7 — below this, FULL is not viable regardless of accuracy.

Outcomes: **FULL** (detectors consume InputTimeline as primary), **HYBRID** (component events primary, solver for air-control channels only), or **FALLBACK** (component events only — still a massive upgrade). The gate result is written up and the S2 design notes updated before S2 begins.

---

## 5. Sprint 2 — Detector rebuild on clean signals

Rebuild `analysis/mechanics.py` detection *primitives*; keep the 26-type taxonomy and public output keys stable.

- Primitives first (per `MECHANICS_DETECTION.md` expert review): car-local transforms everywhere; jump/flip/double-jump from component events (not z-vel spikes); rotation rates from replicated angular velocity (kill Euler-diffing at `mechanics.py:544-546`).
- Each detector consumes, in priority order: InputTimeline (per gate) → component events → kinematics. The kinematic tier is retained as fallback for degraded/old replays; every emitted mechanic carries `confidence` + `signal_source`.
- Cross-wire kickoffs: `events/kickoffs.py:415` `_is_speedflip_kickoff` heuristic replaced by the real speedflip detector output.
- Consolidate duplicated threshold constants (`physics_constants.py` vs `mechanics.py` local copies) into one module with documented provenance.
- Regression discipline: goldens per detector on corpus replays *before* rebuild (pin current counts), then a diff-report of count changes with justification. Existing test suite stays green or is deliberately updated with rationale.

---

## 6. Sprint 3 — Attempt/failure modeling (the SSL differentiator)

New capability: detect *attempts*, classify outcomes.

**TAXONOMY FROZEN 2026-07-07 (Trey sign-off).** Rulings:
1. Wavedash success = **momentum retained** through landing (not raw gain) — supersonic stability dashes count. Direction-agnostic, explicitly including sideways/"cartwheel" wavedashes (Trey's technique).
2. Speedflip attempts **context-gated** to kickoffs + sustained straight-line boost runs. Attempt signature accepts **forward AND backward/diagonal-backward dodge torque** (Trey speedflips with backflip/diagonal-back variants — do not assume forward-diagonal).
3. `reset_unused` = neutral **"banked"**, never a failure.
4. Fast aerial gains `accidental_flip` failure mode (report label: **"sad flip"**) — second press produces dodge instead of double-jump; component distinction detects it directly.
5. v1 attempt/failure set: wavedash, speedflip, flip reset, half-flip, fast aerial, aerial-whiff. Ceiling shots/air dribbles/flicks stay success-count-only in v1.
6. Whiff detection **conservative** + `near_miss` bucket.

Note for S2/S3 test design: Trey's own replays are a stress corpus for the non-canonical variants (back-torque speedflips, cartwheel wavedashes) — validate against them before freezing detector thresholds.

Frozen defaults:

| Mechanic | Attempt signature | Success | Failure modes (classified) |
|---|---|---|---|
| Wavedash | dodge activation within landing window, car tilted into surface | forward speed gain ≥ threshold, clean contact | `too_early` (flip completed airborne), `too_late` (landed before dodge), `scrape` (speed lost), `bounce` |
| Speedflip | diagonal flip + boost during launch window | cancel within bucket ≤3 frames + forward accel spike | `late_cancel`, `no_cancel`, `wrong_diagonal`, `no_boost` |
| Flip reset | underside contact restoring dodge (component reset edge!) | reset acquired AND used within window | `touch_no_reset` (contact but no restore), `reset_unused`, `reset_whiffed` (used, no ball contact) |
| Half-flip | backflip + cancel + roll correction | heading reversal, wheels-down | `no_cancel` (full backflip), `incomplete_rotation` |
| Fast aerial | jump + boost-active + second jump | height/time targets | `slow_second_jump`, `no_boost_hold` |
| Aerial touch | committed aerial toward ball (boost+trajectory intersect) | ball contact | `whiff` (closest-approach miss) |

- Note: with S0 component events, flip-reset *acquisition* becomes near-ground-truth (dodge component becomes available mid-air = replicated state change) — huge accuracy win over the dot-product heuristic.
- Emit `MechanicAttempt` events: `{type, t, outcome: success|<failure_mode>, confidence, context}`; per-player aggregates gain `*_attempts`, `*_failed`, success rates.
- Whiff/attempt detection is genuinely inferential — ship with conservative confidence thresholds and a `near_miss` bucket rather than false precision.

---

## 7. Sprint 4 — Per-event timeline surfacing

### S4.0 Schema contract v2 FIRST (review P1 — sequenced before any new output lands)
- The report schema forbids unknown properties and validation runs pre-return (`report.py:553-568`, `schemas/replay_report.schema.json:126-168`); DB persists only a handful of mechanic counts (`db/models.py:169-175`, `db/writer.py:388-393`). S3/S4 outputs will fail validation or silently vanish without contract work.
- Design + review the v2 contract (schema version field, new event blocks, DB migration, API consumer impact incl. `ui.py`) **during S2/S3**, land it as S4.0. S3's attempt events stay internal (not in report output) until S4.0 is merged.

### S4.1 Surfacing
- Thread the per-event mechanics list into the report. Precise citation (review P2): `analyze_mechanics` *returns* its `events` list (`mechanics.py:2053-2055`); the drop happens in aggregation — `_analyze_player` selects only per-player counts (`analysis/__init__.py:313-315`) and report assembly never reads `cached_mechanics["events"]` (`report.py:326-552`). Fix is aggregation/report threading, not mechanics-module surgery. New schema block `player_mechanic_events[]` (timestamp, type, outcome, confidence, position, ball context).
- Report markdown: per-mechanic breakdowns with timestamps + game-clock, failure-mode tallies, "worst 5 moments" per mechanic.
- Timeline events: emit ROTATION_FLAG/WARNING types already reserved in schema (schema:228) or remove them — no phantom enum values.
- API/DB: persist events for cross-replay trend queries (tendencies/weaknesses modules can then consume mechanics trends, e.g. "speedflip success rate over last 50 replays").

---

## 8. Validation stack (V-track, parallel after S0)

| Tier | What | Ground truth source | Cost |
|---|---|---|---|
| V0 | ReplicatedActive parity vs kinematics | internal consistency | hours (in S0) |
| V1 | Forward resimulation error distributions, corpus-wide | physics consistency | co-built with S1 |
| V1b | Replicated-channel oracle | the replay itself | free with S1 |
| V2 | BakkesMod input logger: log real controller inputs + 120Hz state during Trey's freeplay/private sessions; diff vs reconstruction from the saved replay | real inputs | small C++ plugin (or existing input-viewer plugin if adequate) — separate mini-repo |
| V3 | RLBot scripted corpus: bots perform exact counts of mechanics incl. deliberate failures; detector must match counts+timestamps; runs as versioned fixture set in CI | labels by construction | moderate; community speedflip/wavedash code exists |
| V4 | Differential stats vs ballchasing API on overlapping metrics (goals, boost, positioning) across shared replays | independent implementation | script + API key |
| V5 | Physics-invariant property tests corpus-wide (boost drain 33.3/s while active, speed cap 2300, no teleports, ang-vel cap ~5.5) | physics constants | cheap, CI-friendly |
| V6 (last resort) | Human/video spot-checks (~20 clips) for face validity | eyeballs | only if V2/V3 leave gaps |

Deliverable: `docs/validation.md` with per-mechanic precision/recall and solver accuracy tables — the open-source credibility artifact.

---

## 9. Hygiene track (H)

- H1: migrate `Replay_files/*.replay` (6 binaries) to Git LFS under `assets/replays/` per repo policy. Corrected reference list (review P2, both lanes): `tests/test_rust_adapter.py`, `tests/test_report_end_to_end.py`, `tests/test_docs_parser_contract.py`, `tests/parser/test_rust_adapter_smoke.py`, and `docs/parser_adapter.md`. **CI checkout must add `lfs: true`** (ci.yml builds the Rust wheel and runs the real-replay smoke at ci.yml:79-83) — otherwise fixtures become LFS pointers and the only real-extraction CI coverage silently dies. H1 lands AFTER S0's smoke assertions exist, in one commit with all path updates + CI change.
- H2: archive stale plan docs (`codex/Plans/missing-mechanics.md` is fully implemented); mark this plan as the active roadmap in `AGENTS.md` task router.
- H3: root-level mechanics docs (`MECHANICS_SPEC.md`, `MECHANICS_DETECTION.md`, `MECHANICS_IMPLEMENTATION_PLAN*.md`) → consolidate/move under `codex/docs/` with a pointer, updating the 30Hz sections with the R6 RecordFPS finding.

---

## 10. Open questions for Trey

1. ~~Failure taxonomy sign-off~~ Resolved 2026-07-07 — frozen in §6 with Trey's rulings + technique notes.
2. **Open-source boundary**: recommendation = `rlreplay_rust` (pure extraction) + `rlinput` (solver, feature-gated sim dep) as the public crates; Python analysis stays product. Confirm.
3. **BakkesMod plugin scope** (V2): build our own minimal logger vs. adapt existing plugin — needs a quick look at what exists when we get there.
4. ~~Fable gates~~ Resolved: the orchestrating session runs on Fable; gate adjudication (S1 decision gate, plan review synthesis) happens natively in-session. Fable *subagents* are additionally budgeted for S1 estimator design and stuck-twice escalations per §2b.

## 11. Risks & mitigations

- **R4 parity wrong** → raw counters preserved; V0 catches it in Sprint 0, not Sprint 2.
- **rocketsim-rs integration friction** (version drift vs RL patches; arena collision-mesh assets: sourcing/size/licensing/CI) → S1.0 discovery pre-task resolves before S1.2; pin version; simplified air-phase integrator as fallback objective; sim dependency feature-gated.
- **Physics-patch drift contaminating V1 metrics** → segment all resim error distributions by replay build; document the build↔rocketsim mapping (S1.0).
- **Gate-threshold rationalization** (solo adjudicator, self-graded gate) → threshold freeze protocol in §4: numbers frozen in-doc before results are viewed; post-hoc changes recorded in writing.
- **30Hz ambiguity irreducible for some events** → confidence + ambiguity flags are first-class outputs; buckets not razors (already doctrine in `MECHANICS_DETECTION.md`); high-FPS replays (R6) may relax this for new recordings.
- **Detector rebuild churns counts** → pinned pre-rebuild goldens + justified diff report (S2).
- **Scope creep in S3** (whiff detection is unbounded) → conservative thresholds, `near_miss` bucket, taxonomy frozen at Trey's sign-off.
