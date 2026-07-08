# S1.2 Tick-Lattice Estimator — Design

Date: 2026-07-07
Status: DESIGN — governs S1 implementation work packages (WP1–WP10 below)
Prereqs: plan §4 (`codex/Plans/2026-07-07-max-extraction-input-reconstruction-plan.md`), S1.0 discovery (`codex/docs/2026-07-07-s1-discovery.md`), S0 signal contracts (`src/rlcoach/parser/types.py`)

## Physics ground truth used throughout

All constants and mechanics below were read directly from the vendored RocketSim v2.2.1 source shipped inside the pinned `rocketsim_rs = "=0.37.0"` crate (`RocketSim/src/RLConst.h`, `RocketSim/src/Sim/Car/Car.cpp` at crate rev `c7623a1`, RocketSim rev `f80f9d90`). They are the solver's model of the game. Key facts:

- Gravity `-650` uu/s²; car speed cap `2300`; angular speed cap `5.5` rad/s.
- Boost accel: ground `2975/3 ≈ 991.67`, air `3175/3 ≈ 1058.33` uu/s²; drain `100/3` /s. **Boost min-time** (`RLConst.h:58`, `Car.cpp:499-527`, found post-ratification 2026-07-07): once boosting starts it continues for a minimum of `0.1` s regardless of release — solved boost-off edges can never sit closer than 0.1 s after the on-edge, and short taps deliver the full 0.1 s of accel (~106 uu/s Δv). Air throttle accel `200/3 ≈ 66.67` uu/s².
- Jump (`Car.cpp:548-596`): immediate impulse `875/3 ≈ 291.67` uu/s along car-up; hold accel `4375/3 ≈ 1458.33` uu/s², scaled by `JUMP_PRE_MIN_ACCEL_SCALE = 0.62` (≈ `904.17` uu/s²) while `jump_time < 0.025` s (`Car.cpp:583-587`). `is_jumping` cannot end before `0.025` s regardless of release (`Car.cpp:562`) and persists while held up to `0.2` s. Double jump: another `291.67` up-impulse, no torque. `air_time_since_jump` accrues only once `has_jumped && !is_jumping` (`Car.cpp:698`) — the `1.25` s second-action window is anchored to jump END (`clamp(release, press+0.025 s, press+0.2 s)`), not to release.
- Dodge (from `Car.cpp:704-775`): direction `dodgeDir = normalize(-pitch, yaw+roll)` (car-local 2D, deadzone `0.5` on `|yaw|+|pitch|+|roll|`, per-component `0.1` zeroing); `flipRelTorque = (-dodgeDir.y, dodgeDir.x, 0)`; torque scale `(X=260, Y=224)` applied while `flip_time < 0.65` s; initial velocity impulse `500` uu/s in the dodge direction with speed-ratio scaling (side ×1.9 max, backward ×2.5 max ×16/15, forward ×1.0).
- Flip z-damp signature: while flipping and `0.15 ≤ flip_time ≤ 0.65` and (`vz < 0` or `flip_time < 0.21`): `vz *= (1-0.35)^(tick/120)` per tick.
- Flip cancel (`Car.cpp:616-628`): pitch input with the SAME sign as `flipRelTorque.y` scales pitch flip torque by `(1 - |pitch|)` — **partial cancels are native**; a full cancel is `|pitch| = 1`. Cancelling also re-enables the air-control block. The cancel branch requires `flipRelTorque.y ≠ 0` (`Car.cpp:616`) — **pure side flips are never pitch-cancellable** and get no air control or angular damping for the whole torque phase.
- Air control (`Car.cpp:597-680`): active only when zero wheels have contact, and during a flip only if cancelling (or stalling). Effective angular acceleration (after `CAR_TORQUE_SCALE = 2π/65536·1000 ≈ 0.0958738` and the inertia-normalizing `applyTorque`):
  - torque `T = (pitch 12.464, yaw 9.108, roll 38.350)` rad/s² (`(130, 95, 400) × scale`)
  - damping `D = (pitch 2.876, yaw 1.917, roll 4.794)` s⁻¹ (`(30, 20, 50) × scale`), pitch/yaw damping scaled by `(1 - |input|)`, roll damping unconditional.
  - **During a non-cancelled flip there is no air-control torque AND no angular damping.**
  - Pitch torque is locked while flipping and until `flip_time ≥ 0.65 + 0.3 = 0.95` s (`FLIP_PITCHLOCK_EXTRA_TIME`); in that window pitch input is physically unobservable except through cancel scaling.
- `CarState` (rust wrapper `src/sim/car_state.rs:52`) exposes everything needed for mid-air state injection: `pos, rot_mat, vel, ang_vel, is_on_ground, wheels_with_contact, has_jumped, has_double_jumped, has_flipped, flip_rel_torque, jump_time, flip_time, is_flipping, is_jumping, air_time, air_time_since_jump, boost, is_boosting, handbrake_val, is_demoed, last_controls, …`.

DEVIATION (constants): the brief cites Sam Mish's fitted constants `T = (roll -36.08, pitch -12.15, yaw 8.92)`, `D = (-4.47, -2.80, -1.89)`. Those are empirical fits from RLUtilities and differ from RocketSim's by 2–6% per axis (e.g. roll 36.08 vs 38.35). The estimator uses **RocketSim's constants** because the forward-fit engine IS RocketSim — solver and scorer must share one physics model or inverse-vs-forward cross-validation measures our constant mismatch instead of solve quality. Drift between RocketSim and the actual game is exactly what V1 buckets measure. Attribution: model *form* credited to Sam Mish (RLUtilities, MIT); constants transcribed from RocketSim `RLConst.h` (MIT, ZealanL); approach informed by RLCarInputSolver (MIT). Ideas reimplemented, no code ported (plan R9).

---

## 1. Crate architecture

### 1.1 Layout

```
Cargo.toml                      # existing root workspace (+ rlinput_py member)
parsers/
  rlinput/                      # core crate — pure Rust, publishable, MIT
    Cargo.toml                  # default features: []; feature "sim" -> rocketsim_rs
    NOTICE.md                   # RocketSim / RLUtilities / RLCIS attribution
    src/
      lib.rs
      consts.rs                 # physics constants, provenance comments per value
      model.rs                  # INPUT contract: ReplaySeries, PlayerSeries, events
      timeline.rs               # OUTPUT contract: InputTimeline, channels, provenance
      convert.rs                # UE replay <-> RocketSim frames: quat->RotMat, axes, units
      lattice.rs                # per-segment tick lattice from accumulated deltas
      segment.rs                # segmentation + coverage statistics
      tracker.rs                # stateful per-player state machine
      channels/
        aerial.rs               # inverse aerial control (closed form + root-find)
        ground.rs               # analytic throttle/steer/handbrake solvers
        boost.rs                # blind boost-edge detection
      engine/
        mod.rs                  # trait AirEngine (step-state-in/out)
        portable.rs             # always-on 120Hz air-phase integrator
        rocketsim.rs            # #[cfg(feature = "sim")] TheVoid reference engine
      fit.rs                    # hypothesis enumeration, scoring, confidence
      solver.rs                 # orchestration: segments -> tracker -> fit -> timeline
      calib.rs                  # channel withholding + oracle scoring (S1.3)
  rlinput_py/                   # thin pyo3 wrapper crate -> maturin wheel "rlinput_py"
    Cargo.toml                  # depends on rlinput; feature "sim" passthrough
    src/lib.rs                  # solve_timeline(payload, config) -> dict
src/rlcoach/input_timeline.py   # Python adapter + dataclasses + aggregator cache hook
```

`rlinput` stays free of pyo3 and of any mandatory C++ build: **default features build pure Rust**. The `sim` feature pulls `rocketsim_rs` (cxx + C++ compile) and enables the reference engine plus cross-check tests. This preserves the open-source ambition: the crate is `cargo add`-able without a C++ toolchain, and the full solver (portable engine, all channels, oracle) works without `sim`.

### 1.2 Python boundary — recommendation: separate maturin wheel `rlinput_py`

Options considered:

1. **Extend the existing `rlreplay_rust` wheel** — rejected: couples the dependency-light extraction crate to the solver (plan §S1.1 explicitly wants the parser crate light), and drags solver rebuilds into parser CI.
2. **Subprocess CLI + JSON** — rejected as the primary boundary: a binary still has to ship inside a Python package (same packaging problem, worse error surface). The `model.rs` input contract is serde-serializable, so a `rlinput-cli` bin target can be added later for non-Python OSS users at near-zero cost; documented, not built in S1.
3. **Separate pyo3 crate `parsers/rlinput_py` → wheel `rlinput_py`** — chosen. Mirrors the existing maturin pattern (`make rust-dev` gains a second target), keeps `rlinput` publishable, and the wheel can be built with or without `sim`.

Data flow: Python normalizes (as today) → `input_timeline.py` builds a **columnar** payload (per player: flat `f32` arrays for pos/vel/quat/ang-vel + `delta` array + event lists) → one pyo3 call per replay → `SolveOutput` returned as plain dicts/lists → Python dataclasses. No JSON on the hot path; pyo3 native conversion of ~1M floats per replay is well under the perf budget (≤ 2 s/replay portable engine, target not gate). The solver is optional at runtime: if `rlinput_py` is not importable or `RLCOACH_INPUT_SOLVER=off`, the adapter returns `None` and the pipeline behaves exactly as today.

### 1.3 Core types (Rust sketches)

```rust
// model.rs — input contract (all fields from S0 signals; serde on everything)
pub struct ReplaySeries {
    pub tick_rate: f64,                    // 120.0
    pub build_bucket: String,              // e.g. "251202.62834.504897"
    pub players: Vec<PlayerSeries>,
    pub ball: BallSeries,                  // pos/vel per frame (proximity checks only)
    pub deltas: Vec<f32>,                  // Frame.delta verbatim, zeros included
    pub demo_events: Vec<DemoEventIn>,
    pub touch_events: Vec<TouchEventIn>,
    pub kickoff_markers: Vec<KickoffMarkerIn>,
}
pub struct PlayerSeries {
    pub player_id: String,
    pub frames: Kinematics,                // columnar: pos, vel, quat, ang_vel, on_ground, sleeping, demolished
    pub replicated: ReplicatedChannels,    // throttle_raw, steer_raw, handbrake, boost_amount_raw, boost_active_raw
    pub component: ComponentStream,        // raw u8 counters per component + vector events (dodge_torque, double_jump_impulse)
}

// config
pub enum Mode { Seeded, Unseeded }
pub struct EstimatorConfig {
    pub mode: Mode,
    pub withhold: WithheldChannels,        // bitflags; empty in production, set by oracle
    pub engine: EnginePreference,          // PortableOnly | PreferReference
    pub fit: FitWeights,                   // sigma normalizers + reject threshold
    pub thresholds: SolverThresholds,      // every tunable, serde-loadable for calibration
}

// timeline.rs — output contract
pub enum Source { Replicated, Solved, Inferred, Absent }
bitflags! pub struct AmbiguityFlags: u32 {
    const COLLISION_SUSPECTED    = 1 << 0;
    const CAR_PROXIMITY          = 1 << 1;
    const BALL_PROXIMITY         = 1 << 2;
    const POSSIBLE_PARTIAL_CANCEL= 1 << 3;
    const PITCHLOCK_ACTIVE       = 1 << 4;   // pitch physically unobservable
    const FLIP_TORQUE_ACTIVE     = 1 << 5;   // yaw/roll unobservable (no cancel)
    const ANGVEL_SATURATED       = 1 << 6;   // 5.5 rad/s clamp engaged
    const LONG_GAP               = 1 << 7;   // interval delta > 0.15 s
    const DUPLICATE_FRAME        = 1 << 8;   // delta == 0 merge
    const LOW_MARGIN             = 1 << 9;   // near-tie between hypotheses
    const STALL_SUSPECTED        = 1 << 10;
    const BOUNDARY_ADJACENT      = 1 << 11;
    const SURFACE_PROXIMITY      = 1 << 12;
}
pub struct Channel<T> { pub value: T, pub source: Source, pub confidence: f32, pub flags: AmbiguityFlags }
pub struct InputSample {                    // one per recorded interval [k, k+1)
    pub frame_index: u32,
    pub tick_range: (u64, u64),             // segment-lattice ticks [start, end)
    pub time_range: (f64, f64),             // absolute replay seconds for the same bounds
    pub throttle: Channel<f32>, pub steer: Channel<f32>,
    pub pitch: Channel<f32>,    pub yaw: Channel<f32>,   pub roll: Channel<f32>,
    pub jump: Channel<bool>,    pub boost: Channel<bool>, pub handbrake: Channel<bool>,
}
pub struct CancelSummary {                  // S2 needs cancel timing, not just presence
    pub onset_tick: Option<u64>,            // first tick with same-signed pitch ≥ 0.1; None = never cancelled
    pub peak_pitch: f32,                    // max |pitch| during the torque phase (1.0 = full cancel)
    pub full_cancel: bool,                  // peak_pitch ≥ 0.95 within the torque window
}
pub enum SolvedEventKind {
    JumpPress, JumpRelease, DoubleJump,
    Dodge { dir: [f32; 2], cancel: CancelSummary },
    Stall,
    Liftoff, Landing,                       // contact transitions, kinematic-sourced, for S2 windows
}
pub struct SolvedEvent { pub kind: SolvedEventKind, pub tick: u64, pub t: f64,  // segment-lattice tick + absolute replay seconds
                         pub frame_index: u32, pub confidence: f32, pub flags: AmbiguityFlags }
pub struct InputTimeline { pub player_id: String, pub samples: Vec<InputSample>,
                           pub events: Vec<SolvedEvent>, pub segments: Vec<SegmentSummary> }
pub struct SolveOutput { pub timelines: Vec<InputTimeline>, pub coverage: CoverageReport,
                         pub diagnostics: SolveDiagnostics }
```

Seeded vs unseeded is **one code path**: priors (component events, replicated channels) enter only as (a) candidate narrowing in hypothesis generation and (b) evidence weights in tracker transitions. `Mode::Unseeded` asserts the prior streams are empty. The oracle's `WithheldChannels` is the same mechanism at per-channel granularity. There is no fork.

Python-side mirror (`src/rlcoach/input_timeline.py`): frozen dataclasses `InputTimeline`, `InputSample`, `ChannelValue`, `SolvedEvent` documented in `parser/types.py`'s module docs as the S2 consumption surface. Attachment point: computed lazily and cached at the aggregator level in `analysis/__init__.py` (same pattern as other expensive analyzers), keyed by player id — NOT fields on `PlayerFrame`, NOT in the report schema (S4.0 owns any externalization).

---

## 2. Segmentation

The solver operates on per-player **contact-free segments**. A segment is a maximal run of recorded frames for one player during which the car's dynamics are believed to be free of unmodeled external forces (ball, other cars, arena surfaces beyond the modeled ground state).

### 2.1 Boundary causes (each recorded, machine-readable, on both adjacent segments)

| Cause | Detection (all from S0 signals) |
|---|---|
| `BallTouch` | `parser_touch_events` for this player at/inside the interval |
| `BallProximity` | interpolated car–ball distance `< 190` uu (`91.25 + 74.7 + 25` margin); boundary if accompanied by a velocity kink, else flag only |
| `CarContactSuspected` | see §2.2 |
| `Demolition` / `Respawn` | `parser_demo_events`, `is_demolished` edges; respawn = teleport (`‖Δpos‖ > 500` uu in one interval) |
| `KickoffReset` | `parser_kickoff_markers`, goal-reset teleports |
| `Liftoff` / `Landing` | `is_on_ground` edges (S0 augmented test), `sleeping` edges |
| `SurfaceProximity` | conservative arena-plane test, §2.3 |
| `StreamEdge` | replay start/end, parser gaps |

### 2.2 "Suspected car-car contact" at 30Hz — operational definition

Cars close at up to ~4600 uu/s relative speed, i.e. ~153 uu per 33ms interval — endpoint distances alone can miss a bump. Definition:

1. Interpolate both cars' positions across the shared interval with cubic Hermite (position + velocity known at both endpoints), sampled on the 120Hz lattice.
2. `d_min` = minimum center distance over the interval. Octane bounding sphere is `√(59.0² + 42.1² + 18.1²) ≈ 74.7` uu.
3. `d_min < 170` uu (two spheres + 20 uu interpolation margin) → `CarContactSuspected`: hard boundary for **both** players at that interval.
4. `170 ≤ d_min < 350` uu → `CAR_PROXIMITY` flag on the interval (confidence multiplier ×0.8, no split).
5. **Retroactive upgrade**: if the best hypothesis for an interval leaves an unexplained velocity residual `> 150` uu/s AND another car was within `500` uu at either endpoint, upgrade to `CarContactSuspected`, split the segment there, and re-solve both halves.

### 2.3 Airborne / surface classification (meshless-safe)

CI has no collision meshes, so segment classification must never require sim contact queries. Conservative closed-form planes (standard Soccar):

- floor: `z < 40` uu; ceiling: `z > 2044 − 40`; side walls: `|x| > 4096 − 40`; back walls: `|y| > 5120 − 40`; corner bevels: `|x| + |y| > 8064 − 60`;
- floor–wall transition arcs: `z < 256` AND (`4096 − |x| < 256` OR `5120 − |y| < 256`).

A frame is **AIR** iff: not `is_on_ground`, not `sleeping`, not demolished, and outside all proximity zones. A segment is an AIR segment iff every frame in it is AIR (the liftoff interval itself is included, with jump-hold force modeled — §5). Frames in proximity zones but not grounded get `SURFACE_PROXIMITY` and terminate AIR segments. Everything else is GROUND (analytic channels only, §7) or EXCLUDED.

These exclusions are deliberately conservative; the cost is coverage, which gate criterion 5 measures — so the tradeoff is visible, not hidden.

### 2.4 Coverage statistic (gate criterion 5)

Emitted per replay by `segment.rs`, aggregated by V1:

```
coverage = |{AIR segments with segment_confidence ≥ 0.7}| / |{AIR segments}|
```

Also reported (informational, not gate): duration-weighted coverage, and the share of player-seconds excluded by each boundary cause (so conservative exclusion can't game the denominator — plan §4 requirement). **Adjudication guard (non-gate)**: if excluded airborne player-seconds — all exclusion causes combined, measured against total not-on-ground player-seconds — exceed **10%** on the holdout, the gate writeup MUST include the exclusion-cause breakdown and an explicit argument that the exclusions are physically warranted before criterion 5 is adjudicated. **Frozen definitions, recorded before any solver results are viewed**: an AIR segment is as defined in §2.3; `segment_confidence` is the minimum over the segment's intervals of the winning joint-hypothesis confidence (§5.4). Orchestrator should ratify both definitions at dispatch (open decision #3, §10).

## 3. Stateful per-player tracker

A product state, not a flat FSM:

```rust
pub struct CarTracker {
    contact: ContactState,   // Grounded { since_tick } | Airborne { liftoff_tick } | Demolished { until }
    jump: JumpState,         // Idle | Holding { press_tick } | Released { press_tick, release_tick }
    second: SecondAction,    // Available { deadline_tick }         // = jump_end + 1.25 s; jump_end = clamp(release, press+0.025 s, press+0.2 s)
                             // | UsedDodge(FlipPhase) | UsedDoubleJump { tick } | Expired
    boost: BoostTracker,     // active: bool, amount_estimate: f32
}
pub struct FlipPhase {
    start_tick: u64,
    rel_torque: [f32; 2],    // flipRelTorque.(x,y); zero => stall
    cancel: CancelProfile,   // per-interval solved pitch during torque phase
    // derived windows: torque ends start+0.65s·120; pitchlock ends start+0.95s·120;
    // z-damp active [start+0.15s, start+0.65s)
}
```

Legality rules enforced (mirroring `Car.cpp`): a dodge or double jump requires `Airborne`, `second == Available`, and `now < deadline`; dodge requires flip input magnitude ≥ deadzone (0.5) — below it the same press is a double jump; a dodge with per-component inputs under 0.1 that normalize to zero is a **stall** (torque-free flip: z-damp fires, no angular step). Jump hold: `is_jumping` runs a minimum of 0.025 s — early release does not end it (`Car.cpp:562`) — and a maximum of 0.2 s; hold accel is 0.62-scaled before 0.025 s and full 1458.33 uu/s² after. The `Available` deadline clock (`DOUBLEJUMP_MAX_DELAY = 1.25` s) starts when `is_jumping` ends: `jump_end = clamp(release, press+0.025 s, press+0.2 s)`. A second press edge is accepted while airborne even before `jump_end` — RocketSim gates on `airTimeSinceJump < 1.25`, which is held at 0 while jumping (`Car.cpp:698-704`).

Transition evidence by mode:

| Transition | Seeded evidence | Unseeded evidence |
|---|---|---|
| Grounded→Airborne (jump) | jump raw-counter delta (mod 256) at interval; `is_on_ground` drop | `is_on_ground` drop + car-up Δv ≥ ~250 uu/s (30Hz-decayed 291.67 impulse) |
| JumpRelease | jump counter parity/delta | up-accel residual profile: ~904 uu/s² (0.62×) before 0.025 s then 1458 uu/s² while held; release = interval where the hold signature ends, never placed before press+0.025 s; else assumed at 0.2 s cap with flag |
| Dodge | dodge counter delta + `dodge_torque` vector (direction!) | ang-vel step on flip axis + z-damp signature + 500 uu/s planar Δv; adjudicated by forward-fit |
| DoubleJump | double-jump counter delta + `double_jump_impulse` vector | up Δv ≈ 291.67 with **no** angular step |
| Stall | dodge counter delta with near-zero `dodge_torque` | z-damp signature without torque step |
| Landing | `is_on_ground` rise / `sleeping` | same (kinematic channel, never withheld) |
| Demolition/Respawn | demo events / teleport | same |

Ground truth for counters follows the S0 durable contract exactly (`parser/types.py:255` docstring): edges are reconstructed from **raw-counter deltas mod 256** — any change ⇒ ≥1 toggle; odd delta ⇒ net flip; nonzero even delta ⇒ ≥2 sub-frame toggles — preferring per-activation vector events where present. The `active` parity boolean is never used as ground truth. `dodge_impulse` is not consumed anywhere.

The tracker is exact given correct events (seeded). Unseeded, it carries **hypothesis branches**: candidate transitions proposed from kinematic anomalies stay open until forward-fit adjudicates the interval, then the winner collapses the branch (beam width ≤ 4 branches; deeper ties resolve within ≤ 2 intervals because flip signatures are strong at 30Hz — z-damp + torque are visible over multiple frames).

---

## 4. Tick lattice + event placement

### 4.1 Lattice construction

Per segment (never global — f32 drift over ~9000 frames; plan R9/S0.7):

```
acc: f64 = 0                      // tick 0 = segment's first frame
for each frame k in segment[1..]:
    acc += f64(delta[k])           // boxcars Frame.delta verbatim, zeros included
    tick[k] = round_half_even(acc * 120.0)
```

- `delta == 0` (7/8621 on 0925.replay): `tick[k] == tick[k-1]` → merge, keep the later observation, flag `DUPLICATE_FRAME`.
- Large gaps (max observed 0.19 s → 23 ticks): tolerated; interval flagged `LONG_GAP` when `delta > 0.15 s`; hypothesis placement prunes via signatures (§4.3) and confidence is reduced. Gaps never abort a segment.
- Cadence guard: if `|acc·120 − round(acc·120)| > 0.35` persistently, emit a `nonstandard_cadence` diagnostic (corpus is verified 30Hz — V-0a — but the code must not silently assume it).
- Nominal case: `1/30 s → exactly 4.0` ticks per interval.
- Sub-tick alignment error (recorded frames need not land exactly on physics-tick boundaries) is bounded by half a tick and absorbed into the fit noise floor σ (§5.3).

### 4.2 Candidate event placement

For an interval spanning ticks `[t_k, t_{k+1})`, `N = t_{k+1} − t_k` (typically 4): discrete events legal per the tracker (at most: one jump press OR one second-action, plus one jump release) may be placed at any of the `N` ticks. Everything else — direction, cancel profile, analog channels — is **continuous** and solved by inverse models inside a fixed discrete skeleton, so the discrete space never explodes.

**`LONG_GAP` intervals are the exception**: a ~23-tick gap can legally contain a composite sequence (press → release → second action) that the one-event skeleton forbids. Policy: composite skeletons are **allowed** on `LONG_GAP` intervals — bounded to one press + one release + one second action, legality-ordered per §3, enumerated with signature pruning (endpoint Δv decomposition, z-damp presence) and hard-capped at 256 hypotheses; past the cap the interval is emitted `Inferred` + `LONG_GAP`. Solved composites carry a confidence ceiling of 0.5. These intervals are **not excluded from gate criteria 1–2**: flip-presence signatures (z-damp, impulse) span the gap and "correct recorded interval" remains well-defined, so exclusion would be an unnecessary post-freeze reinterpretation of the gate; the 0.5 ceiling instead makes them count honestly against criterion 5. Rationale for allowing rather than excluding: gaps are rare (≤ 0.08% of frames on 0925.replay), but a forbidden-by-construction skeleton would silently mis-solve real composite actions into single events.

### 4.3 Hypothesis-space size and pruning

- **Null-hypothesis fast path**: if the interval shows no kinematic anomaly (angular velocity change explained by damping alone; Δv explained by gravity + current boost/throttle estimate; no z-damp signature), no event hypotheses are generated at all. The null hypothesis is scored once. This covers the overwhelming majority of intervals.
- **Event intervals**: ≤ N placements × ≤ 2 legal event kinds = ≤ 8 discrete hypotheses. For dodges, direction warm-starts from evidence: seeded = replicated `dodge_torque`; unseeded = the observed Δω axis (flip torque dominates the angular step, so the axis estimate is strong). Continuous refinement (direction ± cancel onset) uses ≤ 6 forward-sim evaluations per surviving placement (coordinate descent, converges in ≤ 3 rounds because the objective is near-quadratic in direction angle).
- **Bound**: ≤ 8 × 6 = 48 short sims (≤ interval length) per event interval, plus one verification sim per ordinary interval. A generous 200 event intervals per player per replay ⇒ ~10k sims of ≤ 78 ticks ≈ 8×10⁵ car-ticks/player — sub-second in either engine, ~seconds per replay for 6 players.
- **Timing discriminability** (why placement is solvable at all): shifting a dodge by one tick shifts the 500 uu/s impulse by 8.33 ms ⇒ ~4.2 uu of end-of-interval position difference, plus torque-integration differences in ω and the z-damp onset. boxcars decodes positions at 0.01 uu resolution (`Vector3f::decode` divides raw ints by 100, boxcars `src/network/models.rs:15-17`) — three orders of magnitude below the 4.2 uu margin. WP6 includes a synthetic discriminability probe that measures this margin empirically before any real-replay claims are made.

---

## 5. Forward-fit engine

### 5.1 Engine abstraction

```rust
pub trait AirEngine {
    /// Advance `state` by `ticks` at 120Hz applying `controls` and pending events.
    fn rollout(&mut self, state: &CarPhysState, plan: &TickPlan, ticks: u32) -> CarPhysState;
}
```

Two implementations:

- **`PortableEngine`** (always-on, no C++): semi-implicit Euler at 120Hz implementing the *airborne subset* of the physics model in the doc header: gravity; boost accel along nose + tank drain + 0.1 s min-boost state machine; air throttle; jump hold force (0.62× before 0.025 s, full 1458.33 uu/s² after; 0.025 s minimum / 0.2 s maximum jump duration); jump/double-jump/dodge impulses; flip torque with cancel scaling, pitchlock, z-damp; air-control torque + damping with the exact gating (no torque & no damping during non-cancelled flips); 2300 and 5.5 clamps. Integration order copied from RocketSim's update sequence.
- **`RocketSimEngine`** (`feature = "sim"`): `GameMode::TheVoid` arena at 120Hz per the verified `parsers/rlinput/src/sim.rs` pattern — `init_from_mem(&[], &[])`, `Arena::new(TheVoid, default, 120)`, one persistent arena, `set_car(id, CarState)` per hypothesis (full mid-air state injection incl. `is_flipping`, `flip_rel_torque`, `flip_time`, `air_time_since_jump`), `set_car_controls` per tick via the tick-by-tick `step(1)` loop, `get_car` per observation tick. Ball parked at a fixed far position with zero velocity on every reset so it can never interact. AIR segments are contact-free by construction, so meshlessness is immaterial.

DEVIATION (engine roles): the plan names rocketsim-rs as the forward-fit engine with a simplified integrator as *fallback*. This design promotes the portable integrator to the **default inner-loop engine** with RocketSim TheVoid as the **reference engine**: `EnginePreference::PreferReference` re-scores each winning hypothesis on TheVoid and is used for all gate-facing numbers (locally and in `sim`-featured CI); `PortableOnly` is what a meshless/toolchain-light environment gets. Rationale: (a) CI is meshless anyway and the wheel should not require a C++ toolchain for OSS consumers; (b) the inner loop wants thousands of cheap rollouts; (c) correctness is protected by a mandatory cross-check suite — random air states + control sequences stepped through both engines; acceptance p99 position divergence < 1 uu and ang-vel divergence < 0.02 rad/s over 0.5 s rollouts. If the cross-check can't reach tolerance, the reference engine becomes mandatory for scoring (the trait makes this a config change, not a redesign) and the gate is unaffected.

### 5.2 Fit cycle per interval

```
state ← observed state at frame k (convert.rs: quat→RotMat, axis conventions)
for each hypothesis h:                     # discrete skeleton + continuous fill
    plan ← TickPlan(h, continuous channels from inverse models §6/§7)
    sim  ← engine.rollout(state, plan, N)
    E(h) ← score(sim, observed state at frame k+1)
select h* = argmin E; refine continuous params (≤3 rounds); update tracker; emit
```

Multi-frame segments chain teacher-forced: each interval restarts from the *observed* frame-k state, so per-interval errors are independent (this is also V1's 1-frame-horizon definition). A full-segment free rollout is additionally scored as a diagnostic.

### 5.3 Scoring function

```
E(h) = ‖p_sim − p_obs‖²/σ_p² + ‖v_sim − v_obs‖²/σ_v² + θ(q_sim, q_obs)²/σ_θ² + ‖ω_sim − ω_obs‖²/σ_ω²
```

with `θ(·,·)` the geodesic rotation angle. Initial normalizers — chosen so one "unit" of error corresponds to the smallest physically meaningful discrepancy at 30Hz:

| term | σ initial | rationale |
|---|---|---|
| position | 4 uu | one-tick dodge-impulse displacement (§4.3) — the timing discriminator |
| velocity | 20 uu/s | ~½ tick of gravity + quantization headroom |
| rotation | 0.05 rad | one tick of mid-rate flip torque integration |
| ang-vel | 0.15 rad/s | ~½ tick of air-control torque at full input |

These are **provisional**: WP6 measures actual replicated-state noise floors on the frozen 10-replay dev set (null-hypothesis residuals on quiet coasting intervals) and replaces the σ values before any gate-facing run; final values recorded in `consts.rs` with provenance. Velocity and ang-vel dominate event *detection*; position dominates event *placement* — the σ choices encode that deliberately.

### 5.4 Confidence mapping

Treat E as a squared-error log-likelihood: raw posterior over the hypothesis set `p_i = exp(−E_i/2) / Σ_j exp(−E_j/2)`; `conf_raw = p_best`, with two overrides:

- absolute rejection: `E_best > E_reject` (config; initial 25 ≈ 5σ joint) ⇒ the interval is emitted `Inferred` with the tracker's prior expectation and confidence ≤ 0.3;
- near-tie: `p_best < 0.6` ⇒ `LOW_MARGIN` flag.

`conf_raw` then passes through a **calibration map** (piecewise-linear/isotonic fit produced by the S1.3 oracle, §7.3, stored as constants) so emitted confidence ≈ empirical accuracy. Channel confidence = `min(channel-specific confidence, interval joint confidence)`; segment confidence = min over intervals (§2.4). Ambiguity flags apply fixed multiplicative haircuts (config) so flagged intervals can't silently carry top confidence.

### 5.5 When the portable integrator substitutes

Per §5.1: it *is* the inner loop everywhere; it is also the **only** engine in default CI (meshless, no C++ needed) and for OSS consumers without the `sim` feature. TheVoid re-scoring runs locally and in the `sim`-featured CI job. If TheVoid stepping itself proved unsuitable (it has not — verified in `sim.rs`), the portable engine carries the whole load, which the plan sanctions for air segments.

---

## 6. Inverse aerial control

### 6.1 Model and closed-form inversion

For airborne, non-flip-torque intervals, in car-local axes with per-axis constants from the doc header (`T = (12.464, 9.108, 38.350)`, `D = (2.876, 1.917, 4.794)`; pitch, yaw, roll):

```
α = T·u − D·ω_L·(1 − |u|)        for pitch and yaw
α = T·u − D·ω_L                  for roll (damping unconditional)
```

where `ω_L = R⊤ω_world` and `α` is the per-tick car-local angular acceleration. Signs of each axis (which local direction is "positive pitch input") are pinned by round-trip property tests against the engine (`solve(rollout(u)) == u`), not by documentation — that kills the classic convention-bug class at the source.

Single-step closed form per axis (pitch/yaw), branching on the sign of `u`:

```
u ≥ 0:  α = u(T + Dω) − Dω   ⇒  u = (α + Dω) / (T + Dω)
u < 0:  α = u(T − Dω) − Dω   ⇒  u = (α + Dω) / (T − Dω)
roll:                            u = (α + Dω) / T
```

Compute both branches, keep sign-consistent roots, clamp to `[−1, 1]`. Both-consistent ⇒ smaller `|u|` + `LOW_MARGIN`; neither ⇒ clamp to the nearer boundary + flag. **Degeneracy is real and symmetric per branch**: the `u ≥ 0` denominator `T + Dω` crosses zero at `ω = −T/D` and the `u < 0` denominator `T − Dω` at `ω = +T/D` — pitch `±4.33 rad/s`, yaw `±4.75 rad/s`, both inside the 5.5 cap (roll damping is not input-scaled, so roll is always well-conditioned). Near-degenerate denominators (`|T ± Dω| < 2`) fall back to forward-fit refinement on that axis, flagged.

Multi-tick composition: over an interval, `u` is assumed constant (the 30Hz resolution limit — per-tick input variation inside an interval is unobservable; stated as a documented contract, "buckets not razors"). The exact discrete map `ω_{t+1} = clamp_{5.5}(ω_t + α(u, ω_t)/120)` composed N times is **not globally monotone in `u`**: `∂α/∂u = T ± Dω` flips sign when `ω` crosses `∓T/D` (pitch ±4.33, yaw ±4.75 rad/s), and the composed trajectory can cross that line mid-interval. Recovery is therefore **branch-wise and orientation-aware**: solve `u ∈ [0, 1]` and `u ∈ [−1, 0]` independently; within each branch, evaluate the end-of-interval residual on a coarse grid (9 points) to bracket every sign change, then bisect each bracket (≤ 20 iterations, single-step closed form as initializer). Multiple roots ⇒ smallest `|u|` + `LOW_MARGIN`; no root in either branch ⇒ nearer boundary + flag. `ANGVEL_SATURATED` intervals (clamp engaged) are ill-posed ⇒ inverse skipped, forward-fit only, confidence haircut.

### 6.2 Observability windows (from the verified gating in `Car.cpp`)

| phase | pitch | yaw / roll |
|---|---|---|
| free air | invertible | invertible |
| flip, `flipRelTorque.y ≠ 0`, no cancel input | only via cancel scaling (none active) — flip torque only | **no physical effect** (`doAirControl == false`) ⇒ `Inferred`, conf 0, `FLIP_TORQUE_ACTIVE` |
| flip, `flipRelTorque.y ≠ 0`, cancelling | recovered from flip-torque scaling `(1−|pitch|)` on the flip-pitch axis ⇒ **partial cancels measurable** (`POSSIBLE_PARTIAL_CANCEL` when 0 < |pitch| < 1). Air-control pitch torque stays zero (`pitchTorqueScale = 0` while flipping) — pitch is observable ONLY through cancel scaling | invertible (air control re-enabled) |
| pure side flip (`flipRelTorque.y == 0`) | **never cancellable** — the cancel branch requires `relDodgeTorque.y() != 0` (`Car.cpp:616`); `doAirControl` stays false ⇒ `Inferred`, conf 0, `FLIP_TORQUE_ACTIVE` | **no physical effect** for the whole torque phase ⇒ `Inferred`, conf 0, `FLIP_TORQUE_ACTIVE` |
| pitchlock tail (0.65–0.95 s, all flips incl. stalls) | **no physical effect** (`pitchTorqueScale = 0`, `Car.cpp:651-654`) ⇒ `Inferred`, conf 0, `PITCHLOCK_ACTIVE` | invertible |
| stall (torque-free flip, 0–0.65 s) | **no physical effect** — `doAirControl == true` but `pitchTorqueScale = 0` while `isFlipping` (`Car.cpp:649-650`), and pitch damping is input-independent at scale 0 ⇒ `Inferred`, conf 0, `PITCHLOCK_ACTIVE` | invertible (air control active) |

Honest unobservability is a first-class output: channels the physics cannot expose are emitted as `Inferred` with zero confidence, never guessed with false precision.

### 6.3 Cross-validation with forward-fit

On every non-flip AIR interval the inverse solution is cheap; the forward engine then replays `u_inv` and the residual must sit at the σ noise floor. V1 publishes the distribution of inverse-vs-forward disagreement (per bucket); intervals disagreeing beyond 3σ get re-solved by forward-fit search and flagged. This mutually validates the integrator, the inversion, and the constants — and it is the plan's S1.2 "validate against forward-fit on sample intervals" requirement, running corpus-wide for free.

---

## 7. Calibration oracle (S1.3)

### 7.1 Blind-channel protocol

Per replay, per player: run the solver with `mode = Unseeded` and `withhold = {throttle, steer, handbrake, boost_active, boost_amount, jump_edges}` — the withheld set is exactly the replicated ground truth being predicted, so scoring is non-tautological (plan's S1.3 requirement). Component counters/vectors are already absent in Unseeded mode.

**Interpretation freeze (needs orchestrator ratification before any results are viewed — open decision #2):** `boost_amount` is withheld along with `boost_active`, because amount-drain makes boost-active trivially derivable and would inflate criterion 3. The amount-derived edge accuracy is additionally reported as a separate diagnostic row.

Blind solvers used (all always-on, no sim feature, hence CI-runnable):

- **boost edges** (`channels/boost.rs`): specific-force residual `a_res = Δv/Δt − g` projected on the nose direction; airborne threshold `> 0.5 × 1058.33 = 529 uu/s²` (signal-to-threshold margin is enormous at 30Hz); grounded: joint throttle+boost disambiguation via the longitudinal model — unambiguous above 1410 uu/s (throttle contributes zero accel there), jointly solved below with reduced confidence.
- **jump edges**: liftoff kinematics + car-up Δv ≈ 291.67 impulse + 1458.33 hold signature; double jump per §3.
- **throttle** (`channels/ground.rs`): longitudinal accel residual vs the community-measured throttle curve (~1600 uu/s² at 0 speed → 0 at 1410; braking 3500; coast 525 — pinned in `consts.rs` with provenance and validated by this very oracle). Scored on sign agreement per the gate.
- **steer**: yaw-rate + speed → curvature `κ = ω_z/v`; `steer = κ/κ_max(v)` using the measured max-curvature-vs-speed piecewise curve. Emitted with reduced confidence when slip angle is high (see handbrake).
- **handbrake**: sustained slip angle `β = ∠(v_2D, forward_2D) > ~15°` plus curvature-model mismatch. No frozen gate number exists for handbrake; reported informationally.

### 7.2 Metrics (gate criterion 3, frozen)

| channel | metric | frozen bar |
|---|---|---|
| boost, jump edges | event F1, ±1-interval tolerance | ≥ 0.95 |
| throttle | sign agreement on frames outside deadzone (|raw−128| > 13) | ≥ 90% |
| steer | |solved − true| ≤ 0.15 (normalized) share of frames | ≥ 85% of frames |
| handbrake | F1 | informational only |

Steer is scored over **all** frames per the frozen text; a powerslide/non-powerslide split is reported alongside for diagnosis but adjudication uses the all-frames number.

### 7.3 Calibration output

The oracle produces, per channel: reliability data (predicted confidence vs empirical accuracy in 10 confidence bins) fitted to a monotone piecewise-linear map. That map is committed as constants and applied to **unreplicated** channels' confidence (§5.4), on the argument that margin→accuracy behavior transfers across channels solved by the same machinery — this transfer assumption is stated in the public accuracy artifact rather than hidden. Oracle results are the artifact (per replay, per player, per bucket JSON + markdown), shipped with the repo as the measured-accuracy credibility deliverable.

---

## 8. V1 resim harness

### 8.1 Runner

`scripts/v1_resim.py` (local; CI variant below):

1. Iterate a corpus directory; parse + normalize through the existing pipeline.
2. Call `rlinput_py.solve_timeline` (config: Unseeded for gate runs, Seeded for production-mode diagnostics; `PreferReference` engine locally).
3. The Rust side computes, in the same pass, per AIR-segment per interval: `E_solved` (1-frame teacher-forced positional error under solved inputs) and `E_zero` (identical rollout with all-zero inputs: no boost, no torque, gravity only) — the zero-input baseline is *defined* as that rollout.
4. Write one JSONL per replay (per-segment records: bucket, duration, ticks, flags, confidences, `E_solved`, `E_zero`, inverse-vs-forward disagreement) and an aggregate report: median / p95 of `E_solved` and `E_zero`, the criterion-4 ratios, per **build bucket** (`250811 ×5`, `250909 ×1`, `251202 ×196`), plus coverage per §2.4 and the excluded-duration breakdown.

### 8.2 Frozen dev set and baselines

Dev set = 10 replays: the 6 committed `Replay_files/*.replay` fixtures (already de facto development data; they cover buckets 250811 and 250909) + 4 from the 251202 bucket selected by seeded deterministic draw. **Sequencing is load-bearing**: the seed and resulting GUIDs are committed as a manifest in WP1 (`assets/s1_dev_set.json`) and appended to the plan's frozen block BEFORE any σ, threshold, or confidence-map tuning exists anywhere in the codebase — the dev set must not be chosen with tuning knowledge in hand. **Per-fixture thresholds are forbidden**: every tunable lives in the global `SolverThresholds`/`FitWeights` config; nothing may key on replay identity. Baseline medians/p95s (`E_zero` distributions) are computed on the dev set once, committed as a JSON artifact, and never recomputed — criterion 4 compares holdout `E_solved` medians against these frozen numbers (median ≤ 0.25×, p95 ≤ 0.5×, no bucket worse than 2× corpus median). The ≥15-replay holdout is drawn by the orchestrator **only after all tuning is locked** (final thresholds committed and declared frozen), from replays untouched during S1.

### 8.3 CI variant

`pytest` marker `resim_smoke` + `cargo test`: portable engine only, the 6 committed fixtures, asserting sanity envelopes (solver improves on zero-input baseline; coverage above a loose floor; no NaN/panic; baseline regression within tolerance) — deliberately NOT the gate thresholds, which are adjudicated locally on the holdout with the reference engine. The engine cross-check suite (§5.1) runs in the `sim`-featured CI job.

---

## 9. Work-package decomposition (ordered; Codex lanes)

Every WP: rust-engineer skill mandated; gate = `ruff` + `black --check` + `pytest` + `cargo test` + `cargo clippy --all-targets` (+ `--all-features` where `sim` is touched); tests mirror source tree; no WP touches another WP's owned files.

| # | Scope | Owned files | Acceptance criteria | Proves | Size |
|---|---|---|---|---|---|
| **WP1** | Model + output types, conversions, lattice, dev-set freeze | `rlinput/src/{model,timeline,convert,lattice,consts}.rs`, `assets/s1_dev_set.json` | serde round-trips; quat→RotMat golden tests on known orientations; lattice unit tests: delta-zero merge, 0.19 s gap, f64 accumulation (9000-frame synthetic drifts < 0.5 tick within segments), cadence guard; **dev-set manifest committed** (6 fixtures + 4 seeded-draw 251202 GUIDs per §8.2) before any σ/threshold tuning exists anywhere | foundations for all criteria | S |
| **WP2** | Segmentation + coverage | `rlinput/src/segment.rs` | synthetic boundary tests per §2.1 cause; Hermite car-car min-distance tests; coverage stats emitted; pinned segment/coverage counts on 0925 fixture | criterion 5 denominator | M |
| **WP3** | Tracker + edge reconstruction | `rlinput/src/tracker.rs` | mod-256 delta edge recovery incl. wrap (254→2) and even-delta sub-frame cases; legality property tests (no dodge without window etc.); on 0925: reconstructed dodge edges consistent with 378 vector events, double-jump with 119; `dodge_torque` axis/magnitude convention verified empirically here | criterion 1 ground-truth side | M |
| **WP4** | Portable air engine | `rlinput/src/engine/{mod,portable}.rs` | implements full §5.1 airborne subset; unit tests per mechanic (z-damp window, cancel scaling, pitchlock, impulse scaling vs speed); update order documented against `Car.cpp` | criterion 4 machinery | M |
| **WP5** | Channel solvers | `rlinput/src/channels/{aerial,ground,boost}.rs` | inverse-aerial round-trip vs portable engine (`solve(rollout(u)) ≈ u`, p99 < 0.02 input units, degenerate zones excluded+flagged) with dense cases at `ω ∈ {±4.33, ±4.75, ±5.5}` rad/s and both `u` signs (non-monotone + saturated regimes per §6.1); branch-wise bracketing recovers all roots on constructed multi-root cases; ground-model unit tests; boost-edge synthetic tests | criteria 3, 6 cross-val | M |
| **WP6** | Forward-fit + confidence + RocketSim engine | `rlinput/src/fit.rs`, `rlinput/src/engine/rocketsim.rs` | engine cross-check suite (§5.1 tolerances); **synthetic discriminability probe** (built on fit primitives over synthetic single intervals — no `solver.rs` dependency): dodges injected at known ticks in TheVoid, re-solved, tick-placement accuracy + margin distribution reported; noise-floor measurement on the WP1-frozen dev set replaces provisional σ; null-hypothesis fast path benchmarked | criteria 1, 2, 4 | **L** |
| **WP7** | Solver orchestration + unseeded candidates + mode plumbing | `rlinput/src/solver.rs` (sole owner — WP6 does not touch it), `tracker.rs` (branch extensions; ownership handed off from WP3, which completes first) | segments→tracker→fit pipeline assembled; seeded/unseeded single-code-path assertion; unseeded flip detection on synthetic + fixture data; beam-width bound tests | criteria 1, 2 | M |
| **WP8** | pyo3 boundary + Python attachment | `parsers/rlinput_py/*`, `src/rlcoach/input_timeline.py`, `parser/types.py` docs, `Makefile`, `.github/workflows/ci.yml`, `tests/input_timeline/*` | wheel builds via maturin from workspace (CI path per S1.0 note); adapter degrades to `None` without wheel; aggregator cache wiring; perf: full 0925 solve ≤ 2 s portable | integration surface | M |
| **WP9** | Calibration oracle + V1 harness | `rlinput/src/calib.rs`, `scripts/v1_resim.py`, baseline artifact, CI `resim_smoke` | withholding config honored (tautology guard test: withheld channel never read — enforced by type-level masking); oracle metrics per §7.2 emitted; consumes the WP1-frozen dev-set manifest (no reselection permitted); frozen baseline JSON committed; bucket-segmented reports | criteria 3, 4, 5 | M |
| **WP10** | Gate evaluation tooling + docs | `scripts/s1_gate_eval.py`, `docs/validation.md` skeleton, `rlinput/NOTICE.md` | one command produces the criterion-by-criterion holdout report (holdout list as input, chosen by orchestrator); attribution notices land; no thresholds embedded that disagree with the plan's frozen block | gate adjudication | S |

Dependencies: after WP1, WP2/WP3/WP4 may run in parallel (disjoint files). WP5 requires WP4 — its round-trip acceptance runs against the portable engine. WP6 requires WP4+WP5 (engines + channel fills) and WP2 (segmentation for the dev-set noise-floor measurement). WP7 requires WP3+WP6. WP8 can start once WP1's contracts stabilize. WP9 requires WP7+WP8; WP10 last.

**Riskiest package: WP6.** It carries the three ways the whole sprint can fail at once: (a) 30Hz tick-placement discriminability could sit below the real noise floor — the synthetic probe is sequenced *first inside the WP* so this is known before any real-data claims; (b) portable-vs-RocketSim divergence could exceed tolerance, forcing the reference engine into the scoring path; (c) the σ/confidence calibration feeds gate criteria 1, 2, 4 and 5 simultaneously, so an error here contaminates every number the decision gate reads. It gets the full 3-iteration cross-family review loop and a mid-WP orchestrator checkpoint after the discriminability probe, before the solver touches any corpus replay.

---

## 10. Design risks + open decisions for the orchestrator

### Risks

1. **Discriminability below noise floor (WP6-a).** Mitigation: probe-first sequencing; the frozen gate's timing criterion is interval-level (≥98% correct interval), which survives even if sub-frame placement is weak — placement confidence reports honestly low and criterion 2's operative branch is unaffected.
2. **Portable-engine drift vs RocketSim (WP6-b).** Bounded by the cross-check suite; config-level fallback to reference-engine scoring; worst case CI keeps portable with looser envelopes (sanctioned by plan).
3. **Axis/quaternion convention bugs** — the classic silent killer here. Structural mitigation: all conventions pinned by golden and round-trip tests (WP1/WP5), never by comment claims.
4. **Coverage shortfall (criterion 5)** from conservative surface-proximity exclusion. Visible, not hidden: excluded-duration share is a first-class report column; if coverage lands < 80%, the gate decision (HYBRID vs FULL) has the data to say *why*.
5. **Replicated-state noise floors unknown** until WP6 measures them; provisional σ values could misrank hypotheses early. No gate exposure: gate-facing runs occur only after the dev-set noise-floor calibration replaces them.
6. **TheVoid semantics**: gravity/air physics in TheVoid are arena-geometry-independent and the stepping path is verified (`sim.rs`), but WP6's probe implicitly re-verifies (synthetic flips must resolve correctly *in TheVoid itself*).

### Open decisions (recommendation attached; none block WP1–WP5)

1. **Python boundary = separate `rlinput_py` maturin wheel** (§1.2). Ratify.
2. **Strict-blind boost protocol** — withhold `boost_amount` alongside `boost_active` for criterion 3 scoring, amount-derived edges reported as diagnostic (§7.1). This is an interpretation freeze on gate wording; per the freeze protocol it should be recorded in the plan's frozen block *now*, before any solver results exist. Ratify.
3. **Criterion-5 definitions freeze** — AIR-segment definition (§2.3) and `segment_confidence = min over intervals of joint-hypothesis confidence` (§2.4). Same reasoning; record in the frozen block. Ratify.
4. **Collision meshes**: not needed for any S1 gate criterion (air-only + analytic ground). Recommend acquiring a mesh dump on Trey's Windows machine via `ZealanL/RLArenaCollisionDumper` before S2, wired local-only through `RLCOACH_ROCKETSIM_MESH_DIR`, to unlock wall/ceiling segments and sim-validated ground physics later. Not an S1 dependency.
5. **Steer scoring under powerslide**: frozen text says all frames; we adjudicate on all frames and publish the split. No action needed — noted so nobody "fixes" it post-hoc.
6. **`dodge_torque` vector semantics** (unit direction vs torque-scaled) are verified empirically in WP3 before any seeded-mode reliance; unseeded gate runs never touch it, so gate exposure is zero either way.

---

## Orchestrator ratification (2026-07-07, Fable main session)

- **DEVIATION (RocketSim constants over Sam Mish fits): APPROVED.** Solver and scorer must share one physics model; game-vs-model drift is V1's job to measure, not the inverse solver's to absorb.
- **DEVIATION (portable engine as inner loop, RocketSim TheVoid as reference oracle): APPROVED**, with the §5.1 cross-check suite (p99 pos < 1 uu, ang-vel < 0.02 rad/s over 0.5 s) as a NON-NEGOTIABLE WP6 acceptance criterion. If tolerance is missed, reference-engine scoring becomes mandatory via config per the design.
- **Open decision 1 (rlinput_py wheel): RATIFIED.**
- **Open decision 2 (strict-blind boost): RATIFIED** — recorded in the plan's frozen block same-day, before any solver output exists.
- **Open decision 3 (criterion-5 definitions): RATIFIED** — recorded in the plan's frozen block same-day.
- **Open decisions 4–6: noted;** mesh dump requested from Trey (not an S1 dependency); steer all-frames stands; dodge_torque semantics land in WP3.
- **WP6 mid-package checkpoint** (after discriminability probe, before corpus contact) is a standing orchestration requirement.

### Fix-pass ratification (2026-07-07, iteration 2)

Cross-family review findings P0-1..3, P1-1..3, P2-1..3 fixed via designer deltas; all 9 verified against the vendored RocketSim source, none contested. Orchestrator ratifies the two designer judgment calls made where the findings offered options:

- **LONG_GAP composite skeletons: ALLOWED** (§4.2) — bounded composite enumeration (one press + one release + one second action), 256-hypothesis cap, 0.5 confidence ceiling; intervals remain in gate criteria 1–2. Freeze-safe: adds constraints before any solver results exist.
- **Excluded-airborne adjudication guard: 10%** (§2.4) — non-gate procedural guard requiring an exclusion-cause breakdown + physical justification before criterion 5 is adjudicated if combined airborne exclusions exceed 10% on the holdout.

Verification bonuses folded in beyond the findings: pure side flips are never pitch-cancellable (cancel branch gated on `relDodgeTorque.y() != 0`, `Car.cpp:616`); a second press edge is accepted while `is_jumping` is still true (the 1.25 s window reads `airTimeSinceJump`, pinned at 0 during the jump) — availability START is airborne + distinct press edge, deadline anchors to jump end.

### WP6a checkpoint ruling (2026-07-07): reference-engine scoring mandatory

The §5.1 cross-check suite FAILED at first measurement: p99 position 3.41 uu / ang-vel 0.261 rad/s (bars: 1 uu / 0.02 rad/s), flip classes dominant, boost taps clean, conventions round-trip verified — full table in `codex/docs/2026-07-07-s1-wp6a-probe.md`. Per the §5.1 sanctioned fallback, **RocketSimEngine (TheVoid) is now mandatory for all gate-facing scoring**; the portable engine remains the CI/OSS default with documented looser envelopes and serves as hypothesis pre-ranker only. The cross-check test stays in-tree as `#[ignore]` and the tolerance is unchanged — a portable-fix track is open (leading hypothesis: rotation integration method — Bullet quaternion exponential map vs orthonormalized Euler — plus a possible one-tick event-alignment offset in the harness, DoubleJump signature ≈ exactly 291.67/120 uu). If the fix lands and the suite passes at tolerance, the portable engine may be restored to the inner loop by config; the gate is unaffected either way.

**RESOLVED same day**: the fix track landed all three hypotheses (Bullet-style exponential-map rotation integration; same-tick event/control overlay semantics; clamp-after-transform ordering) and the suite PASSES at the frozen tolerance — max class p99 0.391 uu / 0.000012 rad/s (orchestrator re-verified). The `#[ignore]` flag is removed; the cross-check runs in every `--features sim` test pass. Portable is restored as the trusted inner-loop pre-ranker; `PreferReference` (RocketSim re-score of surviving hypotheses) remains the gate-facing scoring mode. Probe results (WP6a2, reference engine): dodge placement 100% clean / 99.6% noisy with margin p50 155 and measured 4.67 uu per tick shift; double-jump noisy sub-tick placement 44.5% (near-degenerate as physics dictates — interval-level placement per criterion 2's 30Hz branch is unaffected; LOW_MARGIN reports it honestly); reference-scoring throughput ~1.9 s per 6-player replay (debug profile), within budget.

### WP6b checkpoint ruling (2026-07-07): sample-held observations — fresh-anchored scoring mandatory

The first noise-floor measurement (σ_pos 73.697 uu, σ_vel 21.667 uu/s at pooled p68, n=1047) is **REJECTED as contaminated**. The verify lane's phase probes plus orchestrator analysis established the mechanism, and it is a property of the observation stream, not of the physics or the harness:

- **`TAGame.RBActor_TA:ReplicatedRBState` is one atomic attribute and is NOT resent every recorded frame.** During quiet coasting the server withholds updates; the normalizer forward-fills, so recorded frames carry bit-identical stale kinematics. Measured directly on 0925 exports: **52.6% of airborne frames are full-tuple bit-identical holds** (runs of 1: 4393, runs of 2: 2018, runs of 3: 4; partial-field holds 0.4% — atomicity confirmed).
- The contaminated σ was therefore measuring *physics motion against frozen samples*: velocity residual exactly g·Δt (21.667 = 650/30), position residual ∝ |v|·Δt (slope 0.86, r 0.95 in the dominant bucket), multi-interval holds explaining the 1.5×g·Δt tail. On genuinely fresh, phase-aligned pairs the residual collapses to **quantization scale (position p68 ≈ 0.02 uu, n=16)**.
- Fresh/held frames *alternate* during quiet stretches (run-1 dominant), which is why no uniform ±1-tick re-pairing collapsed the residuals — the cadence assumption itself is wrong, not the offset.

**Ruling — observation-model amendment to §5.2/§5.3:**

1. **Freshness mask.** A frame is FRESH iff its full RB tuple (pos, vel, quat, ang_vel) differs bit-wise from the previous frame's; first frame of a segment is fresh. Computed at series load in `model.rs`; all consumers share it. Rationale for bit-identity over a parser-level flag: ReplicatedRBState is atomic (0.4% partial-field coincidences measured), and a moving airborne car cannot legitimately repeat a quantized tuple (vel changes by g·Δt ≫ 0.01 uu quantization per interval). Ceiling documented: if ground-fit ever needs freshness for parked cars, expose `updated_actors` from the parser instead.
2. **Fresh-anchored teacher forcing.** Residual terms exist ONLY at fresh frames. Rollouts anchor consecutive-fresh → consecutive-fresh (spanning held frames; typically 1–3 recorded frames, ≤0.1 s, below the LONG_GAP threshold — no policy interaction). Held frames contribute no scoring terms anywhere (fit, solver, σ measurement).
3. **Event-placement impact is minimal by construction**: state-changing events (dodge, flip, boost, bump) force replication, so signal-bearing frames are fresh. Holds occur precisely when nothing happens.
4. **σ re-measurement** (WP6c) re-runs the WP6b harness fresh-anchored on the frozen dev set. Expected floors near quantization scale; if fresh-anchored residuals still show sub-interval phase structure (the low_vel bucket hypothesis), the lane reports distributions and the orchestrator decides whether per-anchor sub-tick offset modeling enters the design — not the lane.
5. **Prediction on record** (falsifiable): with fresh-anchored scoring and corrected σ, the 0925 unseeded-vs-seeded flip agreement (0.108 at WP7 merge, E_reject blowout ⇒ event hallucination) should rise dramatically. If it stays ~0.1 after this fix, the failure is in WP7 candidate generation and gets its own investigation.

First-measurement numbers stay in `codex/docs/2026-07-07-s1-wp6b-noise-floor.md` as an audit-trail record with the STOP verdict; they never become gate-facing constants.

### WP7c/WP9 synthesis ruling (2026-07-07): unseeded deficits are concrete scope/recall defects — Wave A ordered

First full oracle readout (dev set, tuning-visible; `codex/docs/2026-07-07-s1-wp9-oracle.md`) plus the WP7c taxonomy (`codex/docs/2026-07-07-s1-wp7c-miss-taxonomy.md`) localize the criterion misses to four concrete defects, none of which is "30Hz observability is insufficient":

1. **Unseeded jump-press inference does not exist** (recall 0/539). First presses occur at ground→air liftoff boundaries; the air solver never proposes them. Fix: liftoff-implied press events (jump impulse ≈ 292 uu/s vertical step discriminates press-liftoff from drive-off), emitted at segment boundaries, seeding tracker jump state into the AIR segment.
2. **Kinematic candidate generation misses 62% of component-known flips** (NO_CANDIDATE 1185/1900) despite flip signatures being the largest in the system. Diagnose (thresholds vs corrected σ; span-dilution of end-to-end deltas; signature-shape blind spots) and fix; a further 31% are OUTSCORED_BY_NULL — likely mis-parameterized candidates (direction/tick), same investigation.
3. **Hallucinations (1923) are NOT missing-truth artifacts** (all in full component coverage) — lead suspect is real non-flip dynamics leaking into AIR segments (surface contact via conservative-plane-test gaps, car-car bumps). Audit ordered (position vs nearest surface / other-car distance at hallucination intervals).
4. **Two oracle numbers are measurement plumbing, not solver verdicts**: coverage 0.0045 (confidence constants unwired into solver output) and V1 ratio 0.983 (Python one-frame approximation ceiling; Rust same-pass metric is the design instrument — deferred to after Wave A).

Sub-tick δ modeling (WP6c residual phase structure, σ_pos 36 uu) remains DEFERRED; revisit at the post-Wave-A oracle re-run.

Pre-registered predictions (falsifiable, same discipline as the WP6b ruling): (P1) liftoff-implied presses lift jump edge F1 from 0.059 to ≥ 0.8; (P2) candidate-gen + outscoring fixes lift flip recall from 0.37 to ≥ 0.8 without hallucinations growing (trade curve required in the report); (P3) the hallucination audit finds concentration near surfaces/other cars. Failures of these predictions are design information, not lane failures.

## Wave A5 synthesis ruling (orchestrator, 2026-07-08)

Evidence: Wave A4 adjacency probe (killed: 10.3% of misses) and Wave A5 three-cause forensic (`codex/docs/2026-07-07-s1-waveA.md`). Facts adopted: (a) 1573/1784 scoped misses show the angular-velocity effect +1..+8 frames after the component edge, concentrated +1..+3, all on FRESH anchors — held-run blindness falsified; only 144 effect-intervals produced any solved flip. (b) `second_available` failures are dominated by `Expired` window state (320/481); hallucinated-prior cascades are marginal (35). (c) `segment_is_air` failures sit at surface margin p50 ≈ −23 uu, far from any raw liftoff (551/615).

### Rulings

1. **Event-time convention (ratified).** The component edge frame remains the truth key for all rulers; solver events keep kinematic placement; NO re-timing of emitted events. Flip matching stays exact coalesced-key as the PRIMARY metric (A4 killed the tolerance story); ±1-interval is retained as a diagnostic column only. Press matching convention is ratified as coalesced key with ±2-frame tolerance (per Wave A2 mechanics argument).
2. **Lookahead evidence horizon (Wave A6 work).** The lag population is an evidence-locality problem: a flip onset near an interval terminator has ~no in-interval evidence; its kinematic signature lands in the next 1–3 fresh anchors. Candidate enumeration and scoring for interval N may draw evidence from a bounded lookahead of up to 3 subsequent consecutive-fresh anchors (flag-stamped on the interval; no change to truth keys or event placement). A plain frame-shift of candidate anchors is KNOWN BAD (A5 attempt: recall 0.370→0.309, reverted).
3. **Surface-contact mechanics (Wave A6 work).** The Expired + far-from-liftoff populations are unmodeled game mechanics, not bugs: flip resets (four-wheel surface contact restores the second action) and wavedashes (dodge at/near surface contact). Tracker gains a contact-driven second-action restore; dodge candidates become legal in a narrow surface-contact window (|surface margin| ≤ threshold with contact geometry), NOT a broad Ground allowance (would fight the A4 air-only hallucination guard).

### Pre-registered predictions

- **P-A6a (lookahead):** pooled unseeded flip recall ≥ 0.55 (from 0.370) at margin 256 with hallucinations ≤ 900 and dodge probe 1.000/1.000. If recall lands < 0.45, the lookahead model is wrong — stop, don't tune.
- **P-A6b (surface contact):** ≥ 60% of the Expired-320 + far-551 miss population becomes candidate-eligible; recall contribution ≥ +0.08; hallucination count grows ≤ 10%.
- **P-A6c (joint):** if both land, pooled recall ≥ 0.63 — within reach of the 0.647 emission ceiling measured in A4, at which point the remaining gap is OUTSCORED_BY_NULL scoring work, not enumeration.
