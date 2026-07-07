use super::{AirEngine, CarPhysState, Controls, TickEvent, TickEventKind, TickPlan, AIR_DT};
use crate::consts;

#[derive(Clone, Copy, Debug, Default)]
pub struct PortableEngine;

impl PortableEngine {
    pub fn new() -> Self {
        Self
    }

    fn step(&mut self, state: &mut CarPhysState, controls: Controls, events: &[TickEvent]) {
        let forward_speed = dot(state.vel, forward(state.rot));
        let mut accel = [0.0, 0.0, consts::GRAVITY_Z];
        let mut ang_accel = [0.0; 3];

        // RocketSim airborne order: air torque/throttle (`Car.cpp:124-125`, impl
        // `597-681`), jump (`130`, impl `548-595`), double-jump/flip + z-damp
        // (`133`, impl `684-789`), boost (`143`, impl `499-545`), then velocity
        // clamps in `_FinishPhysicsTick` (`178-203`).
        self.update_air_torque(state, controls, &mut accel, &mut ang_accel);
        let first_jump_started = self.update_jump(state, controls, events);
        self.update_double_jump_or_flip(state, controls, events, forward_speed, first_jump_started);
        self.update_boost(state, controls, &mut accel);

        let unclamped_ang_vel = add(state.ang_vel, mul(ang_accel, AIR_DT));
        let unclamped_vel = add(state.vel, mul(accel, AIR_DT));
        // Arena.cpp:718-722 steps Bullet, snapshots `rotMat` in `_PostTickUpdate`,
        // then clamps velocities in `Car::_FinishPhysicsTick` (`Car.cpp:178-203`).
        state.pos = add(state.pos, mul(unclamped_vel, AIR_DT));
        state.rot = integrate_rot(state.rot, unclamped_ang_vel);
        state.ang_vel = clamp_norm(unclamped_ang_vel, consts::CAR_MAX_ANG_SPEED);
        state.vel = clamp_norm(unclamped_vel, consts::CAR_MAX_SPEED);
        state.boost = state.boost.clamp(0.0, consts::BOOST_MAX);
    }

    fn update_air_torque(
        &mut self,
        state: &mut CarPhysState,
        controls: Controls,
        accel: &mut [f32; 3],
        ang_accel: &mut [f32; 3],
    ) {
        if state.is_flipping {
            state.is_flipping = state.has_flipped && state.flip_time < consts::FLIP_TORQUE_TIME;
        }

        let forward = forward(state.rot);
        let right = right(state.rot);
        let up = up(state.rot);
        let dir_pitch = mul(right, -1.0);
        let dir_yaw = up;
        let dir_roll = mul(forward, -1.0);

        let mut do_air_control = false;
        if state.is_flipping {
            let mut rel = state.flip_rel_torque;
            if norm_sq(rel) > 0.0 {
                if rel[1] != 0.0
                    && controls.pitch != 0.0
                    && rel[1].signum() == controls.pitch.signum()
                {
                    rel[1] *= 1.0 - controls.pitch.abs().min(consts::FULL_CANCEL_PITCH);
                    do_air_control = true;
                }
                *ang_accel = add(
                    *ang_accel,
                    add(
                        mul(forward, rel[0] * consts::FLIP_TORQUE_X),
                        mul(right, rel[1] * consts::FLIP_TORQUE_Y),
                    ),
                );
            } else {
                do_air_control = true;
            }
        } else {
            do_air_control = true;
        }

        if do_air_control {
            let pitch_torque_scale = if state.is_flipping
                || (state.has_flipped && state.flip_time < consts::FLIP_PITCHLOCK_END_TIME)
            {
                0.0
            } else {
                1.0
            };

            let torque = add(
                add(
                    mul(
                        dir_pitch,
                        controls.pitch * pitch_torque_scale * consts::CAR_AIR_CONTROL_T[0],
                    ),
                    mul(dir_yaw, controls.yaw * consts::CAR_AIR_CONTROL_T[1]),
                ),
                mul(dir_roll, controls.roll * consts::CAR_AIR_CONTROL_T[2]),
            );

            let damp_pitch = dot(dir_pitch, state.ang_vel)
                * consts::CAR_AIR_CONTROL_D[0]
                * (1.0 - (controls.pitch * pitch_torque_scale).abs());
            let damp_yaw = dot(dir_yaw, state.ang_vel)
                * consts::CAR_AIR_CONTROL_D[1]
                * (1.0 - controls.yaw.abs());
            let damp_roll = dot(dir_roll, state.ang_vel) * consts::CAR_AIR_CONTROL_D[2];
            let damping = add(
                add(mul(dir_yaw, damp_yaw), mul(dir_pitch, damp_pitch)),
                mul(dir_roll, damp_roll),
            );
            *ang_accel = add(*ang_accel, sub(torque, damping));
        }

        if controls.throttle != 0.0 {
            *accel = add(
                *accel,
                mul(forward, controls.throttle * consts::THROTTLE_AIR_ACCEL),
            );
        }
    }

    fn update_jump(
        &mut self,
        state: &mut CarPhysState,
        controls: Controls,
        events: &[TickEvent],
    ) -> bool {
        let jump_pressed = events
            .iter()
            .any(|event| matches!(event.kind, TickEventKind::JumpPress));
        let mut first_jump_started = false;

        if state.is_jumping {
            state.is_jumping = state.jump_time < consts::JUMP_MIN_TIME
                || (controls.jump && state.jump_time < consts::JUMP_MAX_TIME);
        } else if !state.has_jumped && jump_pressed {
            state.is_jumping = true;
            state.jump_time = 0.0;
            state.vel = add(state.vel, mul(up(state.rot), consts::JUMP_IMMEDIATE_FORCE));
            first_jump_started = true;
        }

        if state.is_jumping {
            state.has_jumped = true;
            let scale = if state.jump_time < consts::JUMP_MIN_TIME {
                consts::JUMP_PRE_MIN_ACCEL_SCALE
            } else {
                1.0
            };
            state.vel = add(
                state.vel,
                mul(up(state.rot), consts::JUMP_ACCEL * scale * AIR_DT),
            );
        }

        if state.is_jumping || state.has_jumped {
            state.jump_time += AIR_DT;
        }

        first_jump_started
    }

    fn update_double_jump_or_flip(
        &mut self,
        state: &mut CarPhysState,
        controls: Controls,
        events: &[TickEvent],
        forward_speed: f32,
        first_jump_started: bool,
    ) {
        if state.has_jumped && !state.is_jumping {
            state.air_time_since_jump += AIR_DT;
        } else {
            state.air_time_since_jump = 0.0;
        }

        if !first_jump_started && state.air_time_since_jump < consts::DOUBLEJUMP_MAX_DELAY {
            for event in events {
                match event.kind {
                    TickEventKind::DoubleJump => {
                        self.double_jump(state);
                        break;
                    }
                    TickEventKind::Dodge { dir } => {
                        self.start_dodge(state, dir, forward_speed);
                        break;
                    }
                    TickEventKind::JumpPress if state.has_jumped => {
                        if self.controls_are_flip(controls) {
                            let dir = [-controls.pitch, controls.yaw + controls.roll];
                            self.start_dodge(state, dir, forward_speed);
                        } else {
                            self.double_jump(state);
                        }
                        break;
                    }
                    TickEventKind::JumpPress | TickEventKind::JumpRelease => {}
                }
            }
        }

        if state.is_flipping {
            state.flip_time += AIR_DT;
            if state.flip_time <= consts::FLIP_Z_DAMP_TORQUE_END
                && state.flip_time >= consts::FLIP_Z_DAMP_START
                && (state.vel[2] < 0.0 || state.flip_time < consts::FLIP_Z_DAMP_END)
            {
                state.vel[2] *= 1.0 - consts::FLIP_Z_DAMP_120;
            }
        } else if state.has_flipped {
            state.flip_time += AIR_DT;
        }
    }

    fn controls_are_flip(&self, controls: Controls) -> bool {
        controls.yaw.abs() + controls.pitch.abs() + controls.roll.abs() >= consts::DODGE_DEADZONE
    }

    fn double_jump(&self, state: &mut CarPhysState) {
        if state.has_double_jumped || state.has_flipped {
            return;
        }
        state.vel = add(state.vel, mul(up(state.rot), consts::JUMP_IMMEDIATE_FORCE));
        state.has_double_jumped = true;
    }

    fn start_dodge(&self, state: &mut CarPhysState, dir: [f32; 2], forward_speed: f32) {
        if state.has_double_jumped || state.has_flipped {
            return;
        }

        state.flip_time = 0.0;
        state.has_flipped = true;
        state.is_flipping = true;

        // Car.cpp:733-737: when BOTH raw components are inside the 0.1 deadzone the
        // dodge direction is zeroed BEFORE normalization (a stall), never normalized up.
        let dir = if dir[0].abs() < consts::DODGE_COMPONENT_DEADZONE
            && dir[1].abs() < consts::DODGE_COMPONENT_DEADZONE
        {
            [0.0, 0.0]
        } else {
            dir
        };
        let mut dodge_dir = normalize2(dir);
        state.flip_rel_torque = [-dodge_dir[1], dodge_dir[0], 0.0];

        if dodge_dir[0].abs() < consts::DODGE_COMPONENT_DEADZONE {
            dodge_dir[0] = 0.0;
        }
        if dodge_dir[1].abs() < consts::DODGE_COMPONENT_DEADZONE {
            dodge_dir[1] = 0.0;
        }
        if dodge_dir == [0.0, 0.0] {
            return;
        }

        let forward_speed_ratio = (forward_speed.abs() / consts::CAR_MAX_SPEED).min(1.0);
        let should_dodge_backwards = if forward_speed.abs() < consts::DODGE_BACKWARD_SPEED_THRESHOLD
        {
            dodge_dir[0] < 0.0
        } else {
            (dodge_dir[0] >= 0.0) != (forward_speed >= 0.0)
        };
        let max_speed_scale_x = if should_dodge_backwards {
            consts::FLIP_BACKWARD_IMPULSE_MAX_SPEED_SCALE
        } else {
            consts::FLIP_FORWARD_IMPULSE_MAX_SPEED_SCALE
        };
        let mut impulse_x = dodge_dir[0]
            * consts::FLIP_INITIAL_VEL_SCALE
            * (((max_speed_scale_x - 1.0) * forward_speed_ratio) + 1.0);
        let impulse_y = dodge_dir[1]
            * consts::FLIP_INITIAL_VEL_SCALE
            * (((consts::FLIP_SIDE_IMPULSE_MAX_SPEED_SCALE - 1.0) * forward_speed_ratio) + 1.0);
        if should_dodge_backwards {
            impulse_x *= consts::FLIP_BACKWARD_IMPULSE_SCALE_X;
        }

        let forward_2d = normalize2([forward(state.rot)[0], forward(state.rot)[1]]);
        let right_2d = [-forward_2d[1], forward_2d[0]];
        state.vel[0] += impulse_x * forward_2d[0] + impulse_y * right_2d[0];
        state.vel[1] += impulse_x * forward_2d[1] + impulse_y * right_2d[1];
    }

    // Car.cpp:499-527 boosting state machine: with boost in the tank, boosting starts
    // on press and CONTINUES while held or until boosting_time reaches BOOST_MIN_TIME —
    // a tap always delivers >= 0.1 s of boost.
    fn update_boost(&mut self, state: &mut CarPhysState, controls: Controls, accel: &mut [f32; 3]) {
        if state.boost > 0.0 {
            if state.is_boosting {
                state.is_boosting = controls.boost || state.boosting_time < consts::BOOST_MIN_TIME;
            } else {
                state.is_boosting = controls.boost;
            }
        } else {
            state.is_boosting = false;
        }

        if state.is_boosting {
            state.boosting_time += AIR_DT;
            state.boost = (state.boost - consts::BOOST_USED_PER_SECOND * AIR_DT).max(0.0);
            *accel = add(*accel, mul(forward(state.rot), consts::BOOST_ACCEL_AIR));
        } else {
            state.boosting_time = 0.0;
        }
    }
}

impl AirEngine for PortableEngine {
    fn rollout(&mut self, state: &CarPhysState, plan: &TickPlan, ticks: u32) -> CarPhysState {
        let mut state = *state;
        for tick in 0..ticks {
            let mut controls = plan.controls_at(tick);
            let events: Vec<_> = plan
                .events
                .iter()
                .copied()
                .filter(|event| event.tick_offset == tick)
                .collect();
            for event in &events {
                apply_event_controls(&mut controls, *event);
            }
            self.step(&mut state, controls, &events);
        }
        state
    }
}

fn apply_event_controls(controls: &mut Controls, event: TickEvent) {
    match event.kind {
        TickEventKind::JumpPress => controls.jump = true,
        TickEventKind::JumpRelease => controls.jump = false,
        TickEventKind::DoubleJump => {
            controls.jump = true;
            controls.pitch = 0.0;
            controls.yaw = 0.0;
            controls.roll = 0.0;
        }
        TickEventKind::Dodge { dir } => {
            controls.jump = true;
            if dir[0].abs() <= f32::EPSILON && dir[1].abs() <= f32::EPSILON {
                // RocketSim stalls use yaw+roll inside the component deadzone so
                // the edge is a flip input but `Car.cpp:731-737` zeroes dodgeDir.
                controls.pitch = 0.0;
                controls.yaw = 0.3;
                controls.roll = -0.3;
            } else {
                controls.pitch = -dir[0];
                controls.yaw = dir[1];
                controls.roll = 0.0;
            }
        }
    }
}

fn forward(rot: [[f32; 3]; 3]) -> [f32; 3] {
    [rot[0][0], rot[1][0], rot[2][0]]
}

fn right(rot: [[f32; 3]; 3]) -> [f32; 3] {
    [rot[0][1], rot[1][1], rot[2][1]]
}

fn up(rot: [[f32; 3]; 3]) -> [f32; 3] {
    [rot[0][2], rot[1][2], rot[2][2]]
}

fn add(a: [f32; 3], b: [f32; 3]) -> [f32; 3] {
    [a[0] + b[0], a[1] + b[1], a[2] + b[2]]
}

fn sub(a: [f32; 3], b: [f32; 3]) -> [f32; 3] {
    [a[0] - b[0], a[1] - b[1], a[2] - b[2]]
}

fn mul(v: [f32; 3], scalar: f32) -> [f32; 3] {
    [v[0] * scalar, v[1] * scalar, v[2] * scalar]
}

fn dot(a: [f32; 3], b: [f32; 3]) -> f32 {
    a[0] * b[0] + a[1] * b[1] + a[2] * b[2]
}

fn cross(a: [f32; 3], b: [f32; 3]) -> [f32; 3] {
    [
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    ]
}

fn norm_sq(v: [f32; 3]) -> f32 {
    dot(v, v)
}

fn norm(v: [f32; 3]) -> f32 {
    norm_sq(v).sqrt()
}

fn normalize2(v: [f32; 2]) -> [f32; 2] {
    let len = (v[0] * v[0] + v[1] * v[1]).sqrt();
    if len < f32::EPSILON {
        [0.0, 0.0]
    } else {
        [v[0] / len, v[1] / len]
    }
}

fn clamp_norm(v: [f32; 3], max: f32) -> [f32; 3] {
    let len = norm(v);
    if len > max {
        mul(v, max / len)
    } else {
        v
    }
}

fn integrate_rot(rot: [[f32; 3]; 3], ang_vel: [f32; 3]) -> [[f32; 3]; 3] {
    // Bullet integrates orientation with an exponential-map delta quaternion
    // premultiplied onto the current transform (`btTransformUtil.h:46-77`,
    // called from `btRigidBody.cpp:99-106`), not with Euler axis drift.
    let angle = norm(ang_vel) * AIR_DT;
    if angle <= f32::EPSILON {
        return rot;
    }

    let axis = mul(ang_vel, 1.0 / norm(ang_vel));
    let f = rotate_axis_angle(forward(rot), axis, angle);
    let r = rotate_axis_angle(right(rot), axis, angle);
    let u = rotate_axis_angle(up(rot), axis, angle);
    [[f[0], r[0], u[0]], [f[1], r[1], u[1]], [f[2], r[2], u[2]]]
}

fn rotate_axis_angle(v: [f32; 3], axis: [f32; 3], angle: f32) -> [f32; 3] {
    let sin = angle.sin();
    let cos = angle.cos();
    add(
        add(mul(v, cos), mul(cross(axis, v), sin)),
        mul(axis, dot(axis, v) * (1.0 - cos)),
    )
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::convert::identity_rot_mat;
    use crate::engine::{TickEventKind, TickPlan};

    const EPS: f32 = 1e-4;

    fn base_state() -> CarPhysState {
        CarPhysState {
            pos: [0.0; 3],
            vel: [0.0; 3],
            rot: identity_rot_mat(),
            ang_vel: [0.0; 3],
            boost: consts::BOOST_MAX,
            is_boosting: false,
            boosting_time: 0.0,
            has_jumped: true,
            has_double_jumped: false,
            has_flipped: false,
            is_jumping: false,
            is_flipping: false,
            jump_time: 0.0,
            flip_time: 0.0,
            air_time_since_jump: 0.1,
            flip_rel_torque: [0.0; 3],
        }
    }

    fn rollout_one(
        state: CarPhysState,
        controls: Controls,
        events: Vec<TickEvent>,
    ) -> CarPhysState {
        PortableEngine::new().rollout(
            &state,
            &TickPlan {
                controls: vec![controls],
                events,
            },
            1,
        )
    }

    fn event(kind: TickEventKind) -> TickEvent {
        TickEvent {
            tick_offset: 0,
            kind,
        }
    }

    fn assert_close(actual: f32, expected: f32) {
        assert!(
            (actual - expected).abs() < EPS,
            "expected {expected}, got {actual}"
        );
    }

    fn assert_vec_close(actual: [f32; 3], expected: [f32; 3]) {
        for (actual, expected) in actual.into_iter().zip(expected) {
            assert_close(actual, expected);
        }
    }

    #[test]
    fn z_damp_window_and_velocity_condition_match_rocketsim_edges() {
        let controls = Controls::default();
        let mut before_start = base_state();
        before_start.is_flipping = true;
        before_start.has_flipped = true;
        before_start.flip_time = consts::FLIP_Z_DAMP_START - (AIR_DT * 2.0);
        before_start.vel[2] = 100.0;
        assert_close(
            rollout_one(before_start, controls, vec![]).vel[2],
            100.0 + consts::GRAVITY_Z * AIR_DT,
        );

        let mut at_start = before_start;
        at_start.flip_time = consts::FLIP_Z_DAMP_START - AIR_DT;
        assert_close(
            rollout_one(at_start, controls, vec![]).vel[2],
            100.0 * (1.0 - consts::FLIP_Z_DAMP_120) + consts::GRAVITY_Z * AIR_DT,
        );

        let mut at_end = at_start;
        at_end.flip_time = consts::FLIP_Z_DAMP_END - AIR_DT;
        at_end.vel[2] = 100.0;
        assert_close(
            rollout_one(at_end, controls, vec![]).vel[2],
            100.0 + consts::GRAVITY_Z * AIR_DT,
        );

        let mut falling_after_end = at_end;
        falling_after_end.vel[2] = -100.0;
        assert_close(
            rollout_one(falling_after_end, controls, vec![]).vel[2],
            -100.0 * (1.0 - consts::FLIP_Z_DAMP_120) + consts::GRAVITY_Z * AIR_DT,
        );

        let mut torque_end = falling_after_end;
        torque_end.flip_time = consts::FLIP_TORQUE_TIME;
        assert_close(
            rollout_one(torque_end, controls, vec![]).vel[2],
            -100.0 + consts::GRAVITY_Z * AIR_DT,
        );
    }

    #[test]
    fn flip_cancel_scales_pitch_torque_and_side_flips_do_not_cancel() {
        let mut forward_flip = base_state();
        forward_flip.has_flipped = true;
        forward_flip.is_flipping = true;
        forward_flip.flip_rel_torque = [0.0, 1.0, 0.0];
        let out = rollout_one(
            forward_flip,
            Controls {
                pitch: 0.5,
                ..Controls::default()
            },
            vec![],
        );
        assert_close(out.ang_vel[1], consts::FLIP_TORQUE_Y * 0.5 * AIR_DT);

        let mut side_flip = base_state();
        side_flip.has_flipped = true;
        side_flip.is_flipping = true;
        side_flip.flip_rel_torque = [-1.0, 0.0, 0.0];
        side_flip.ang_vel = [0.0, 1.0, 0.0];
        let out = rollout_one(
            side_flip,
            Controls {
                pitch: 1.0,
                yaw: 1.0,
                roll: 1.0,
                ..Controls::default()
            },
            vec![],
        );
        assert_close(out.ang_vel[0], -consts::FLIP_TORQUE_X * AIR_DT);
        assert_close(out.ang_vel[1], 1.0);
        assert_close(out.ang_vel[2], 0.0);
    }

    #[test]
    fn pitchlock_suppresses_pitch_torque_until_extra_window_ends() {
        let mut locked = base_state();
        locked.has_flipped = true;
        locked.flip_time = consts::FLIP_TORQUE_TIME;
        let controls = Controls {
            pitch: 1.0,
            ..Controls::default()
        };
        assert_close(rollout_one(locked, controls, vec![]).ang_vel[1], 0.0);

        let mut unlocked = locked;
        unlocked.flip_time = consts::FLIP_PITCHLOCK_END_TIME;
        assert_close(
            rollout_one(unlocked, controls, vec![]).ang_vel[1],
            -consts::CAR_AIR_CONTROL_T[0] * AIR_DT,
        );
    }

    #[test]
    fn jump_hold_uses_pre_min_scale_and_continues_after_early_release() {
        let mut jumping = base_state();
        jumping.is_jumping = true;
        jumping.jump_time = 0.0;
        let released = Controls::default();
        let out = rollout_one(jumping, released, vec![]);
        assert!(out.is_jumping);
        assert_close(
            out.vel[2],
            (consts::JUMP_ACCEL * consts::JUMP_PRE_MIN_ACCEL_SCALE + consts::GRAVITY_Z) * AIR_DT,
        );

        let after_min = PortableEngine::new().rollout(
            &jumping,
            &TickPlan {
                controls: vec![released; 4],
                events: vec![],
            },
            4,
        );
        assert!(!after_min.is_jumping);

        let mut held_after_min = jumping;
        held_after_min.jump_time = consts::JUMP_MIN_TIME;
        let out = rollout_one(
            held_after_min,
            Controls {
                jump: true,
                ..Controls::default()
            },
            vec![],
        );
        assert_close(
            out.vel[2],
            (consts::JUMP_ACCEL + consts::GRAVITY_Z) * AIR_DT,
        );
    }

    #[test]
    fn first_and_double_jump_impulses_are_numeric() {
        let mut first = base_state();
        first.has_jumped = false;
        let out = rollout_one(
            first,
            Controls {
                jump: true,
                ..Controls::default()
            },
            vec![event(TickEventKind::JumpPress)],
        );
        assert!(out.has_jumped);
        assert_close(
            out.vel[2],
            consts::JUMP_IMMEDIATE_FORCE
                + consts::JUMP_ACCEL * consts::JUMP_PRE_MIN_ACCEL_SCALE * AIR_DT
                + consts::GRAVITY_Z * AIR_DT,
        );

        let out = rollout_one(
            base_state(),
            Controls::default(),
            vec![event(TickEventKind::DoubleJump)],
        );
        assert!(out.has_double_jumped);
        assert_close(
            out.vel[2],
            consts::JUMP_IMMEDIATE_FORCE + consts::GRAVITY_Z * AIR_DT,
        );
    }

    #[test]
    fn dodge_impulse_scales_forward_side_and_backward_with_speed() {
        let controls = Controls::default();
        let forward = rollout_one(
            base_state(),
            controls,
            vec![event(TickEventKind::Dodge { dir: [1.0, 0.0] })],
        );
        assert_close(forward.vel[0], consts::FLIP_INITIAL_VEL_SCALE);

        let side = rollout_one(
            base_state(),
            controls,
            vec![event(TickEventKind::Dodge { dir: [0.0, 1.0] })],
        );
        assert_close(side.vel[1], consts::FLIP_INITIAL_VEL_SCALE);

        let backward = rollout_one(
            base_state(),
            controls,
            vec![event(TickEventKind::Dodge { dir: [-1.0, 0.0] })],
        );
        assert_close(
            backward.vel[0],
            -consts::FLIP_INITIAL_VEL_SCALE * consts::FLIP_BACKWARD_IMPULSE_SCALE_X,
        );

        let mut fast = base_state();
        fast.vel[0] = consts::CAR_MAX_SPEED - 1.0;
        let fast_side = rollout_one(
            fast,
            controls,
            vec![event(TickEventKind::Dodge { dir: [0.0, 1.0] })],
        );
        let unclamped_fast_side = [
            consts::CAR_MAX_SPEED - 1.0,
            consts::FLIP_INITIAL_VEL_SCALE
                * (1.0
                    + (consts::FLIP_SIDE_IMPULSE_MAX_SPEED_SCALE - 1.0)
                        * ((consts::CAR_MAX_SPEED - 1.0) / consts::CAR_MAX_SPEED)),
            consts::GRAVITY_Z * AIR_DT,
        ];
        assert_vec_close(
            fast_side.vel,
            clamp_norm(unclamped_fast_side, consts::CAR_MAX_SPEED),
        );

        let fast_back = rollout_one(
            fast,
            controls,
            vec![event(TickEventKind::Dodge { dir: [-1.0, 0.0] })],
        );
        assert_close(
            fast_back.vel[0],
            fast.vel[0]
                - consts::FLIP_INITIAL_VEL_SCALE
                    * (1.0
                        + (consts::FLIP_BACKWARD_IMPULSE_MAX_SPEED_SCALE - 1.0)
                            * ((consts::CAR_MAX_SPEED - 1.0) / consts::CAR_MAX_SPEED))
                    * consts::FLIP_BACKWARD_IMPULSE_SCALE_X,
        );
    }

    #[test]
    fn boost_drains_tank_and_accelerates_along_nose() {
        let mut state = base_state();
        state.boost = 10.0;
        let out = rollout_one(
            state,
            Controls {
                boost: true,
                ..Controls::default()
            },
            vec![],
        );
        assert_close(out.boost, 10.0 - consts::BOOST_USED_PER_SECOND * AIR_DT);
        assert_vec_close(
            out.vel,
            [
                consts::BOOST_ACCEL_AIR * AIR_DT,
                0.0,
                consts::GRAVITY_Z * AIR_DT,
            ],
        );
    }

    #[test]
    fn boost_tap_continues_for_min_time_then_stops() {
        // Press boost for exactly one tick, then release for the rest.
        let min_ticks = (consts::BOOST_MIN_TIME / AIR_DT).round() as u32; // 12 at 120Hz
        let mut controls = vec![Controls {
            boost: true,
            ..Controls::default()
        }];
        controls.resize(2 * min_ticks as usize, Controls::default());
        let plan = TickPlan {
            controls,
            events: vec![],
        };
        let out = PortableEngine::new().rollout(&base_state(), &plan, 2 * min_ticks);
        // Tank drained for exactly BOOST_MIN_TIME despite the 1-tick tap (Car.cpp:499-527).
        assert_close(
            out.boost,
            consts::BOOST_MAX - consts::BOOST_USED_PER_SECOND * consts::BOOST_MIN_TIME,
        );
        assert!(!out.is_boosting);
        assert_close(out.boosting_time, 0.0);
        // Velocity carries the full min-time of boost accel.
        assert_close(out.vel[0], consts::BOOST_ACCEL_AIR * consts::BOOST_MIN_TIME);
    }

    #[test]
    fn clamps_linear_and_angular_velocity() {
        let mut fast = base_state();
        fast.boost = consts::BOOST_MAX;
        fast.vel = [consts::CAR_MAX_SPEED - 1.0, 0.0, 0.0];
        let out = rollout_one(
            fast,
            Controls {
                boost: true,
                ..Controls::default()
            },
            vec![],
        );
        assert_close(norm(out.vel), consts::CAR_MAX_SPEED);

        let mut spinning = base_state();
        spinning.has_flipped = true;
        spinning.is_flipping = true;
        spinning.flip_rel_torque = [0.0, 1.0, 0.0];
        spinning.ang_vel = [0.0, consts::CAR_MAX_ANG_SPEED - 0.1, 0.0];
        let out = rollout_one(spinning, Controls::default(), vec![]);
        assert_close(norm(out.ang_vel), consts::CAR_MAX_ANG_SPEED);
    }

    #[test]
    fn free_air_control_torque_and_damping_match_single_tick_formula() {
        let mut state = base_state();
        state.ang_vel = [1.2, -2.0, 0.5];
        let controls = Controls {
            pitch: 0.5,
            yaw: -0.25,
            roll: 0.75,
            throttle: 1.0,
            ..Controls::default()
        };
        let out = rollout_one(state, controls, vec![]);

        let dir_pitch = [0.0, -1.0, 0.0];
        let dir_yaw = [0.0, 0.0, 1.0];
        let dir_roll = [-1.0, 0.0, 0.0];
        let torque = add(
            add(
                mul(dir_pitch, controls.pitch * consts::CAR_AIR_CONTROL_T[0]),
                mul(dir_yaw, controls.yaw * consts::CAR_AIR_CONTROL_T[1]),
            ),
            mul(dir_roll, controls.roll * consts::CAR_AIR_CONTROL_T[2]),
        );
        let damping = add(
            add(
                mul(
                    dir_yaw,
                    dot(dir_yaw, state.ang_vel)
                        * consts::CAR_AIR_CONTROL_D[1]
                        * (1.0 - controls.yaw.abs()),
                ),
                mul(
                    dir_pitch,
                    dot(dir_pitch, state.ang_vel)
                        * consts::CAR_AIR_CONTROL_D[0]
                        * (1.0 - controls.pitch.abs()),
                ),
            ),
            mul(
                dir_roll,
                dot(dir_roll, state.ang_vel) * consts::CAR_AIR_CONTROL_D[2],
            ),
        );
        assert_vec_close(
            out.ang_vel,
            add(state.ang_vel, mul(sub(torque, damping), AIR_DT)),
        );
        assert_close(
            out.vel[0],
            (consts::THROTTLE_AIR_ACCEL + consts::GRAVITY_Z * 0.0) * AIR_DT,
        );
    }

    #[test]
    fn same_state_and_plan_are_bit_identical() {
        let state = base_state();
        let plan = TickPlan {
            controls: vec![
                Controls {
                    pitch: 0.25,
                    yaw: -0.5,
                    roll: 0.75,
                    throttle: 1.0,
                    boost: true,
                    ..Controls::default()
                };
                8
            ],
            events: vec![TickEvent {
                tick_offset: 2,
                kind: TickEventKind::Dodge { dir: [0.5, 1.0] },
            }],
        };
        let a = PortableEngine::new().rollout(&state, &plan, 8);
        let b = PortableEngine::new().rollout(&state, &plan, 8);
        assert_eq!(a, b);
        assert_eq!(a.vel.map(f32::to_bits), b.vel.map(f32::to_bits));
        assert_eq!(a.ang_vel.map(f32::to_bits), b.ang_vel.map(f32::to_bits));
    }
}
