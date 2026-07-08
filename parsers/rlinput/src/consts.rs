pub const GRAVITY_Z: f32 = -650.0; // RocketSim `RLConst.h:12`.

pub const CAR_MAX_SPEED: f32 = 2300.0; // RocketSim `RLConst.h:53`.
pub const CAR_MAX_ANG_SPEED: f32 = 5.5; // RocketSim `RLConst.h:66`.

pub const BOOST_MAX: f32 = 100.0; // RocketSim `RLConst.h:56`, clamped at `Car.cpp:545`.
pub const BOOST_USED_PER_SECOND: f32 = BOOST_MAX / 3.0; // RocketSim `RLConst.h:57`, applied at `Car.cpp:530`.
pub const BOOST_ACCEL_GROUND: f32 = 2975.0 / 3.0; // RocketSim `RLConst.h:59`, applied at `Car.cpp:532`.
pub const BOOST_ACCEL_AIR: f32 = 3175.0 / 3.0; // RocketSim `RLConst.h:60`, applied at `Car.cpp:532`.
pub const BOOST_MIN_TIME: f32 = 0.1; // RocketSim `RLConst.h:58`, state machine at `Car.cpp:499-527`: once boosting starts it continues >= 0.1 s regardless of release.

pub const THROTTLE_AIR_ACCEL: f32 = 200.0 / 3.0; // RocketSim `RLConst.h:92`, applied at `Car.cpp:680-681`.

pub const JUMP_ACCEL: f32 = 4375.0 / 3.0; // RocketSim `RLConst.h:94`, applied at `Car.cpp:580-589`.
pub const JUMP_IMMEDIATE_FORCE: f32 = 875.0 / 3.0; // RocketSim `RLConst.h:95`, applied at `Car.cpp:573-574,775-776`.

// Press-liftoff discriminator: RocketSim applies `JUMP_IMMEDIATE_FORCE` along
// car-local up in the jump tick (`Car.cpp:573-574`). A fresh-anchored replicated
// frame can include gravity/hold noise, so require at least 90% of the impulse.
pub const JUMP_LIFTOFF_MIN_UP_VEL_STEP: f32 = JUMP_IMMEDIATE_FORCE * 0.9;
pub const JUMP_PRE_MIN_ACCEL_SCALE: f32 = 0.62; // RocketSim `Car.cpp:583-586`.
pub const JUMP_MIN_TIME: f32 = 0.025; // RocketSim `RLConst.h:96`, gate at `Car.cpp:561-562`.
pub const JUMP_MAX_TIME: f32 = 0.2; // RocketSim `RLConst.h:98`, gate at `Car.cpp:561-562`.
pub const DOUBLEJUMP_MAX_DELAY: f32 = 1.25; // RocketSim `RLConst.h:99`, gate at `Car.cpp:698-704`.

pub const DODGE_DEADZONE: f32 = 0.5; // RocketSim `CarConfig.h:36-37`, used at `Car.cpp:704-706`.
pub const DODGE_COMPONENT_DEADZONE: f32 = 0.1; // RocketSim `Car.cpp:731-742`.
pub const DODGE_BACKWARD_SPEED_THRESHOLD: f32 = 100.0; // RocketSim `Car.cpp:747-751`: below this |forward speed|, backward-dodge selection uses the dodge direction sign alone.

pub const FLIP_INITIAL_VEL_SCALE: f32 = 500.0; // RocketSim `RLConst.h:109`, applied at `Car.cpp:753`.
pub const FLIP_FORWARD_IMPULSE_MAX_SPEED_SCALE: f32 = 1.0; // RocketSim `RLConst.h:112`, applied at `Car.cpp:755-758`.
pub const FLIP_SIDE_IMPULSE_MAX_SPEED_SCALE: f32 = 1.9; // RocketSim `RLConst.h:113`, applied at `Car.cpp:759`.
pub const FLIP_BACKWARD_IMPULSE_MAX_SPEED_SCALE: f32 = 2.5; // RocketSim `RLConst.h:114`, applied at `Car.cpp:755-758`.
pub const FLIP_BACKWARD_IMPULSE_SCALE_X: f32 = 16.0 / 15.0; // RocketSim `RLConst.h:115`, applied at `Car.cpp:761-762`.

pub const FLIP_TORQUE_X: f32 = 260.0; // RocketSim `RLConst.h:110`, applied at `Car.cpp:630`.
pub const FLIP_TORQUE_Y: f32 = 224.0; // RocketSim `RLConst.h:111`, applied at `Car.cpp:630`.
pub const FLIP_TORQUE_TIME: f32 = 0.65; // RocketSim `RLConst.h:105`, gate at `Car.cpp:607,786`.
pub const FLIP_PITCHLOCK_EXTRA_TIME: f32 = 0.3; // RocketSim `RLConst.h:108`, gate at `Car.cpp:651-654`.
pub const FLIP_PITCHLOCK_END_TIME: f32 = FLIP_TORQUE_TIME + FLIP_PITCHLOCK_EXTRA_TIME; // RocketSim `RLConst.h:105,108`, gate at `Car.cpp:651-654`.

pub const FULL_CANCEL_PITCH: f32 = 1.0; // RocketSim cancel clamp at `Car.cpp:616-624`.

pub const FLIP_Z_DAMP_120: f32 = 0.35; // RocketSim `RLConst.h:102`, applied at `Car.cpp:786-788`.
pub const FLIP_Z_DAMP_START: f32 = 0.15; // RocketSim `RLConst.h:103`, gate at `Car.cpp:786-788`.
pub const FLIP_Z_DAMP_END: f32 = 0.21; // RocketSim `RLConst.h:104`, gate at `Car.cpp:786-788`.
pub const FLIP_Z_DAMP_TORQUE_END: f32 = FLIP_TORQUE_TIME; // RocketSim `RLConst.h:105`, gate at `Car.cpp:786-788`.

pub const CAR_TORQUE_SCALE: f32 = 2.0 * std::f32::consts::PI / 65_536.0 * 1000.0; // RocketSim `RLConst.h:124`, applied at `Car.cpp:677`.

pub const CAR_AIR_CONTROL_TORQUE_RAW: [f32; 3] = [130.0, 95.0, 400.0]; // RocketSim `RLConst.h:148-151`, applied at `Car.cpp:658-660`.
pub const CAR_AIR_CONTROL_DAMPING_RAW: [f32; 3] = [30.0, 20.0, 50.0]; // RocketSim `RLConst.h:148-151`, applied at `Car.cpp:668-671`.
pub const CAR_AIR_CONTROL_T: [f32; 3] = [
    CAR_AIR_CONTROL_TORQUE_RAW[0] * CAR_TORQUE_SCALE,
    CAR_AIR_CONTROL_TORQUE_RAW[1] * CAR_TORQUE_SCALE,
    CAR_AIR_CONTROL_TORQUE_RAW[2] * CAR_TORQUE_SCALE,
]; // RocketSim `RLConst.h:124,148-151`, applied at `Car.cpp:658-660,677`.
pub const CAR_AIR_CONTROL_D: [f32; 3] = [
    CAR_AIR_CONTROL_DAMPING_RAW[0] * CAR_TORQUE_SCALE,
    CAR_AIR_CONTROL_DAMPING_RAW[1] * CAR_TORQUE_SCALE,
    CAR_AIR_CONTROL_DAMPING_RAW[2] * CAR_TORQUE_SCALE,
]; // RocketSim `RLConst.h:124,148-151`, applied at `Car.cpp:668-671,677`.

// Community-measured ground model. Provenance: RLBot Useful Game Values
// (`https://wiki.rlbot.org/v5/botmaking/useful-game-values/`) mirrors Sam Mish's
// RLUtilities/ground-control notes (`https://www.smish.dev/rocket_league/ground_control/`):
// throttle falls from ~1600 uu/s² at rest to 0 at ~1410 uu/s, braking is
// ~3500 uu/s², coasting is ~525 uu/s², and max turn curvature is piecewise linear.
pub const GROUND_THROTTLE_ACCEL_ZERO: f32 = 1600.0;
pub const GROUND_THROTTLE_TRANSITION_SPEED: f32 = 1400.0;
pub const GROUND_THROTTLE_TRANSITION_ACCEL: f32 = 160.0;
pub const GROUND_THROTTLE_MAX_SPEED: f32 = 1410.0;
pub const GROUND_BRAKE_ACCEL: f32 = 3500.0;
pub const GROUND_COAST_ACCEL: f32 = 525.0;
pub const GROUND_THROTTLE_RAW_DEADZONE: u8 = 13;
pub const GROUND_HANDBRAKE_SLIP_ANGLE_RAD: f32 = 15.0_f32.to_radians();
pub const GROUND_MAX_CURVATURE_PIECES: [(f32, f32, f32); 5] = [
    (500.0, 0.006_900, -5.84e-6),
    (1000.0, 0.005_610, -3.26e-6),
    (1500.0, 0.004_300, -1.95e-6),
    (1750.0, 0.003_025, -1.10e-6),
    (2500.0, 0.001_800, -0.40e-6),
];

// Measured fit-score noise floors, p68 of fresh-anchored null-hypothesis
// residual norms. Provenance: frozen dev-set manifest `assets/s1_dev_set.json`
// (6 fixtures + 4 seeded 251202 replays), exported with
// `source /Users/treygoff/Code/rlcoach/.venv/bin/activate && python scripts/export_series_json.py`,
// measured 2026-07-07 via
// `RLINPUT_DEV_SERIES_DIR=/tmp/rlinput-dev-series-wp6b cargo test -p rlinput --features sim noise_floor_measurement -- --ignored --nocapture`.
// The first WP6b measurement (pos 73.69741, vel 21.666748, rot 0.013785,
// ang_vel 0.038623) was rejected by the design ruling as sample-held
// contamination; these values score only consecutive fresh RB-state anchors.
pub const FIT_SIGMA_POS_MEASURED: f32 = 36.285_175;
pub const FIT_SIGMA_VEL_MEASURED: f32 = 10.880_035;
pub const FIT_SIGMA_ROT_MEASURED: f32 = 0.006_366;
pub const FIT_SIGMA_ANG_VEL_MEASURED: f32 = 0.020_347;

// WP7b null-vs-event acceptance margin. Calibrated 2026-07-07 on the frozen
// dev-set exports at `/tmp/rlinput-dev-series-wp6b` after preserving null in
// reference re-score. Selected margin 256.0: quiet hallucinations 2456→1923
// versus margin 0, with one coalesced known-flip retention loss (1119→1118).
pub const FIT_NULL_EVENT_ACCEPT_MARGIN: f32 = 256.0;

// Confidence calibration maps fitted once from the regenerated dev-set oracle:
// `RLINPUT_DEV_SERIES_DIR=/tmp/rlinput-dev-series-wp6b cargo test -p rlinput exported_dev_set_oracle_report -- --ignored --nocapture`
// captured as `/tmp/rlcoach-waveCAL-oracle-before.out` on 2026-07-08.
// Inputs are raw solver confidences; outputs are isotonic empirical agreement
// by confidence family. The solver applies these as step functions at the upper
// raw-confidence bound of each fitted block; explicit empty segments bypass the
// map and remain zero.
//
// High-accuracy family: boost_active + handbrake + throttle_sign bins.
pub const CONFIDENCE_CALIBRATION_HIGH_ACCURACY: [(f32, f32); 3] = [
    (0.300_105, 0.834_025),
    (0.848_114, 0.879_783),
    (1.0, 0.951_819),
];

// Steer absolute-error family (`|steer_pred - steer_truth| <= 0.15`).
pub const CONFIDENCE_CALIBRATION_STEER: [(f32, f32); 4] = [
    (0.046_334, 0.397_668),
    (0.120_356, 0.408_149),
    (0.440_419, 0.492_289),
    (1.0, 0.773_189),
];

// Joint confidence family for segment/event confidence and channels without a
// channel-specific oracle curve: pooled high-accuracy + steer bins.
pub const CONFIDENCE_CALIBRATION_JOINT: [(f32, f32); 5] = [
    (0.120_356, 0.695_680),
    (0.210_441, 0.738_968),
    (0.440_419, 0.763_908),
    (0.848_114, 0.833_333),
    (1.0, 0.898_918),
];
