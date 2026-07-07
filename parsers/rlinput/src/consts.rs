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
