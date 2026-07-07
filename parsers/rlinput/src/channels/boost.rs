use crate::{
    consts,
    timeline::{AmbiguityFlags, Channel, Source},
};

pub const BOOST_ACCEL_THRESHOLD_AIR: f32 = consts::BOOST_ACCEL_AIR * 0.5;
pub const BOOST_ACCEL_THRESHOLD_GROUND: f32 = consts::BOOST_ACCEL_GROUND * 0.5;

#[derive(Clone, Copy, Debug, PartialEq)]
pub struct BoostObservation {
    pub tick: u64,
    pub dt: f32,
    pub delta_v: [f32; 3],
    pub nose: [f32; 3],
    pub grounded: bool,
    pub forward_speed: f32,
    pub longitudinal_accel: f32,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct BoostEdge {
    pub tick: u64,
    pub active: bool,
}

pub fn solve_boost(obs: BoostObservation) -> Channel<bool> {
    if obs.grounded {
        return solve_grounded(obs.forward_speed, obs.longitudinal_accel);
    }
    if obs.dt <= f32::EPSILON {
        return Channel {
            value: false,
            source: Source::Inferred,
            confidence: 0.0,
            flags: AmbiguityFlags::LOW_MARGIN,
        };
    }

    let specific_force = [
        obs.delta_v[0] / obs.dt,
        obs.delta_v[1] / obs.dt,
        obs.delta_v[2] / obs.dt - consts::GRAVITY_Z,
    ];
    let projected = dot(specific_force, normalize(obs.nose));
    boost_channel(projected, BOOST_ACCEL_THRESHOLD_AIR)
}

pub fn detect_boost_edges(samples: &[BoostObservation]) -> Vec<BoostEdge> {
    let mut edges = Vec::new();
    let mut active = false;
    let mut on_tick = None;
    let min_ticks = (consts::BOOST_MIN_TIME * 120.0).round() as u64;

    for sample in samples {
        let solved = solve_boost(*sample).value;
        if solved && !active {
            active = true;
            on_tick = Some(sample.tick);
            edges.push(BoostEdge {
                tick: sample.tick,
                active: true,
            });
        } else if !solved && active {
            active = false;
            let off_tick = on_tick.map_or(sample.tick, |tick| sample.tick.max(tick + min_ticks));
            edges.push(BoostEdge {
                tick: off_tick,
                active: false,
            });
            on_tick = None;
        }
    }

    edges
}

fn solve_grounded(forward_speed: f32, longitudinal_accel: f32) -> Channel<bool> {
    let unambiguous = forward_speed > consts::GROUND_THROTTLE_MAX_SPEED;
    let threshold = BOOST_ACCEL_THRESHOLD_GROUND;
    let active = longitudinal_accel > threshold;
    Channel {
        value: active,
        source: Source::Solved,
        confidence: if unambiguous { 0.9 } else { 0.55 },
        flags: if !unambiguous || (longitudinal_accel - threshold).abs() < 100.0 {
            AmbiguityFlags::LOW_MARGIN
        } else {
            AmbiguityFlags::empty()
        },
    }
}

fn boost_channel(projected_accel: f32, threshold: f32) -> Channel<bool> {
    Channel {
        value: projected_accel > threshold,
        source: Source::Solved,
        confidence: if (projected_accel - threshold).abs() < 100.0 {
            0.55
        } else {
            0.9
        },
        flags: if (projected_accel - threshold).abs() < 100.0 {
            AmbiguityFlags::LOW_MARGIN
        } else {
            AmbiguityFlags::empty()
        },
    }
}

fn normalize(v: [f32; 3]) -> [f32; 3] {
    let n = dot(v, v).sqrt();
    if n <= f32::EPSILON {
        [0.0, 0.0, 0.0]
    } else {
        [v[0] / n, v[1] / n, v[2] / n]
    }
}

fn dot(a: [f32; 3], b: [f32; 3]) -> f32 {
    a[0] * b[0] + a[1] * b[1] + a[2] * b[2]
}

#[cfg(test)]
mod tests {
    use super::*;

    fn airborne(tick: u64, accel: f32) -> BoostObservation {
        let dt = 1.0 / 30.0;
        BoostObservation {
            tick,
            dt,
            delta_v: [accel * dt, 0.0, consts::GRAVITY_Z * dt],
            nose: [1.0, 0.0, 0.0],
            grounded: false,
            forward_speed: 0.0,
            longitudinal_accel: 0.0,
        }
    }

    #[test]
    fn airborne_one_interval_tap_creates_min_time_off_edge() {
        let samples = [
            airborne(0, consts::BOOST_ACCEL_AIR),
            airborne(4, 0.0),
            airborne(8, 0.0),
        ];
        let edges = detect_boost_edges(&samples);
        assert_eq!(
            edges,
            vec![
                BoostEdge {
                    tick: 0,
                    active: true
                },
                BoostEdge {
                    tick: 12,
                    active: false
                },
            ]
        );
    }

    #[test]
    fn airborne_specific_force_projects_on_nose() {
        let active = solve_boost(airborne(0, consts::BOOST_ACCEL_AIR));
        assert!(active.value);
        assert!(active.confidence > 0.8);

        let inactive = solve_boost(airborne(0, consts::BOOST_ACCEL_AIR * 0.49));
        assert!(!inactive.value);
    }

    #[test]
    fn grounded_above_1410_is_unambiguous() {
        let solved = solve_boost(BoostObservation {
            tick: 0,
            dt: 1.0 / 30.0,
            delta_v: [0.0; 3],
            nose: [1.0, 0.0, 0.0],
            grounded: true,
            forward_speed: consts::GROUND_THROTTLE_MAX_SPEED + 50.0,
            longitudinal_accel: consts::BOOST_ACCEL_GROUND,
        });
        assert!(solved.value);
        assert!(solved.confidence > 0.8);
        assert!(solved.flags.is_empty());
    }
}
