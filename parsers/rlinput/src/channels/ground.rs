use crate::{
    consts,
    timeline::{AmbiguityFlags, Channel, Source},
};

const COAST_THROTTLE: f32 = 0.01;
const SPEED_EPS: f32 = 1.0;
const ACCEL_LOW_MARGIN: f32 = 100.0;

#[derive(Clone, Copy, Debug, PartialEq)]
pub struct ThrottleObservation {
    pub forward_speed: f32,
    pub longitudinal_accel: f32,
    pub raw_throttle: Option<u8>,
}

#[derive(Clone, Copy, Debug, PartialEq)]
pub struct SteerObservation {
    pub speed_2d: f32,
    pub yaw_rate_z: f32,
}

#[derive(Clone, Copy, Debug, PartialEq)]
pub struct HandbrakeObservation {
    pub velocity_2d: [f32; 2],
    pub forward_2d: [f32; 2],
    pub yaw_rate_z: f32,
    pub steer: f32,
}

pub fn solve_throttle(obs: ThrottleObservation) -> Channel<f32> {
    let mut best = (-1.0, f32::INFINITY);
    for step in 0..=200 {
        let throttle = -1.0 + step as f32 * 0.01;
        let residual =
            (ground_longitudinal_accel(obs.forward_speed, throttle) - obs.longitudinal_accel).abs();
        if residual < best.1 {
            best = (throttle, residual);
        }
    }

    let mut flags = AmbiguityFlags::empty();
    if best.1 > ACCEL_LOW_MARGIN || obs.raw_throttle.is_some_and(raw_throttle_deadzone) {
        flags |= AmbiguityFlags::LOW_MARGIN;
    }

    Channel {
        value: if best.0.abs() <= COAST_THROTTLE {
            0.0
        } else {
            best.0
        },
        source: Source::Solved,
        confidence: if flags.is_empty() { 0.9 } else { 0.5 },
        flags,
    }
}

pub fn solve_steer(obs: SteerObservation) -> Channel<f32> {
    if obs.speed_2d.abs() < SPEED_EPS {
        return Channel {
            value: 0.0,
            source: Source::Inferred,
            confidence: 0.0,
            flags: AmbiguityFlags::LOW_MARGIN,
        };
    }
    let max_curvature = max_curvature(obs.speed_2d.abs());
    if max_curvature <= f32::EPSILON {
        return Channel {
            value: 0.0,
            source: Source::Inferred,
            confidence: 0.0,
            flags: AmbiguityFlags::LOW_MARGIN,
        };
    }
    Channel {
        value: (obs.yaw_rate_z / obs.speed_2d / max_curvature).clamp(-1.0, 1.0),
        source: Source::Solved,
        confidence: 0.85,
        flags: AmbiguityFlags::empty(),
    }
}

pub fn solve_handbrake(obs: HandbrakeObservation) -> Channel<bool> {
    let speed = norm2(obs.velocity_2d);
    let max_curvature = max_curvature(speed);
    let actual_curvature = if speed > SPEED_EPS {
        obs.yaw_rate_z / speed
    } else {
        0.0
    };
    let expected_curvature = obs.steer.clamp(-1.0, 1.0) * max_curvature;
    let slip = slip_angle(obs.velocity_2d, obs.forward_2d);
    let active = slip > consts::GROUND_HANDBRAKE_SLIP_ANGLE_RAD
        && (actual_curvature - expected_curvature).abs() > max_curvature.abs() * 0.35;

    Channel {
        value: active,
        source: Source::Solved,
        confidence: if active { 0.75 } else { 0.6 },
        flags: if slip > consts::GROUND_HANDBRAKE_SLIP_ANGLE_RAD * 0.8 {
            AmbiguityFlags::LOW_MARGIN
        } else {
            AmbiguityFlags::empty()
        },
    }
}

pub fn ground_longitudinal_accel(forward_speed: f32, throttle: f32) -> f32 {
    let throttle = throttle.clamp(-1.0, 1.0);
    if throttle.abs() <= COAST_THROTTLE {
        return if forward_speed.abs() < SPEED_EPS {
            0.0
        } else {
            -forward_speed.signum() * consts::GROUND_COAST_ACCEL
        };
    }
    if forward_speed.abs() >= SPEED_EPS && throttle.signum() != forward_speed.signum() {
        return throttle.signum() * consts::GROUND_BRAKE_ACCEL;
    }
    throttle * throttle_accel_at_speed(forward_speed.abs())
}

pub fn throttle_accel_at_speed(speed: f32) -> f32 {
    let speed = speed.abs();
    if speed >= consts::GROUND_THROTTLE_MAX_SPEED {
        0.0
    } else if speed < consts::GROUND_THROTTLE_TRANSITION_SPEED {
        consts::GROUND_THROTTLE_ACCEL_ZERO
            + (consts::GROUND_THROTTLE_TRANSITION_ACCEL - consts::GROUND_THROTTLE_ACCEL_ZERO)
                * speed
                / consts::GROUND_THROTTLE_TRANSITION_SPEED
    } else {
        consts::GROUND_THROTTLE_TRANSITION_ACCEL * (consts::GROUND_THROTTLE_MAX_SPEED - speed)
            / (consts::GROUND_THROTTLE_MAX_SPEED - consts::GROUND_THROTTLE_TRANSITION_SPEED)
    }
    .max(0.0)
}

pub fn max_curvature(speed: f32) -> f32 {
    let speed = speed.abs();
    for &(upper, intercept, slope) in &consts::GROUND_MAX_CURVATURE_PIECES {
        if speed < upper {
            return (intercept + slope * speed).max(0.0);
        }
    }
    0.0
}

pub fn raw_throttle_deadzone(raw: u8) -> bool {
    raw.abs_diff(128) <= consts::GROUND_THROTTLE_RAW_DEADZONE
}

fn slip_angle(velocity: [f32; 2], forward: [f32; 2]) -> f32 {
    let v = normalize2(velocity);
    let f = normalize2(forward);
    if v == [0.0, 0.0] || f == [0.0, 0.0] {
        return 0.0;
    }
    dot2(v, f).clamp(-1.0, 1.0).acos()
}

fn normalize2(v: [f32; 2]) -> [f32; 2] {
    let n = norm2(v);
    if n <= f32::EPSILON {
        [0.0, 0.0]
    } else {
        [v[0] / n, v[1] / n]
    }
}

fn norm2(v: [f32; 2]) -> f32 {
    dot2(v, v).sqrt()
}

fn dot2(a: [f32; 2], b: [f32; 2]) -> f32 {
    a[0] * b[0] + a[1] * b[1]
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn throttle_sign_recovers_synthetic_accel_profiles() {
        for (speed, throttle) in [(0.0, 1.0), (900.0, 1.0), (900.0, -1.0), (-700.0, 1.0)] {
            let accel = ground_longitudinal_accel(speed, throttle);
            let solved = solve_throttle(ThrottleObservation {
                forward_speed: speed,
                longitudinal_accel: accel,
                raw_throttle: None,
            });
            assert_eq!(
                solved.value.signum(),
                throttle.signum(),
                "{speed} {throttle}"
            );
        }

        let coast = solve_throttle(ThrottleObservation {
            forward_speed: 800.0,
            longitudinal_accel: ground_longitudinal_accel(800.0, 0.0),
            raw_throttle: Some(128),
        });
        assert_eq!(coast.value, 0.0);
        assert!(coast.flags.contains(AmbiguityFlags::LOW_MARGIN));
        assert!(raw_throttle_deadzone(
            128 + consts::GROUND_THROTTLE_RAW_DEADZONE
        ));
        assert!(!raw_throttle_deadzone(
            128 + consts::GROUND_THROTTLE_RAW_DEADZONE + 1
        ));
    }

    #[test]
    fn steer_is_curvature_over_speed_curve() {
        let speed = 1000.0;
        let steer = -0.6;
        let yaw_rate_z = steer * max_curvature(speed) * speed;
        let solved = solve_steer(SteerObservation {
            speed_2d: speed,
            yaw_rate_z,
        });
        assert!((solved.value - steer).abs() < 1e-5, "{solved:?}");
    }

    #[test]
    fn handbrake_requires_slip_and_curvature_mismatch() {
        let active = solve_handbrake(HandbrakeObservation {
            velocity_2d: [1000.0, 500.0],
            forward_2d: [1.0, 0.0],
            yaw_rate_z: 0.0,
            steer: 1.0,
        });
        assert!(active.value);

        let inactive = solve_handbrake(HandbrakeObservation {
            velocity_2d: [1000.0, 10.0],
            forward_2d: [1.0, 0.0],
            yaw_rate_z: max_curvature(1000.0) * 1000.0,
            steer: 1.0,
        });
        assert!(!inactive.value);
    }
}
