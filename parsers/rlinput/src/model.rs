use bitflags::bitflags;
use serde::{Deserialize, Serialize};

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct ReplaySeries {
    pub tick_rate: f64,
    pub build_bucket: String,
    pub players: Vec<PlayerSeries>,
    pub ball: BallSeries,
    pub deltas: Vec<f32>,
    pub demo_events: Vec<DemoEventIn>,
    pub touch_events: Vec<TouchEventIn>,
    pub kickoff_markers: Vec<KickoffMarkerIn>,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct PlayerSeries {
    pub player_id: String,
    pub frames: Kinematics,
    pub replicated: ReplicatedChannels,
    pub component: ComponentStream,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct BallSeries {
    pub pos: Vec<[f32; 3]>,
    pub vel: Vec<[f32; 3]>,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct Kinematics {
    pub pos: Vec<[f32; 3]>,
    pub vel: Vec<[f32; 3]>,
    pub quat_xyzw: Vec<[f32; 4]>,
    pub ang_vel: Vec<[f32; 3]>,
    pub on_ground: Vec<bool>,
    pub sleeping: Vec<bool>,
    pub demolished: Vec<bool>,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct ReplicatedChannels {
    pub throttle_raw: Vec<u8>,
    pub steer_raw: Vec<u8>,
    pub handbrake: Vec<bool>,
    pub boost_amount_raw: Vec<u8>,
    pub boost_active_raw: Vec<bool>,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct ComponentStream {
    pub jump_raw: Vec<u8>,
    pub dodge_raw: Vec<u8>,
    pub double_jump_raw: Vec<u8>,
    pub boost_raw: Vec<u8>,
    pub events: Vec<ComponentEventIn>,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct ComponentEventIn {
    pub t: f64,
    pub frame_index: u32,
    pub component: ComponentKind,
    pub vector: Option<[f32; 3]>,
    pub raw_value: Option<u8>,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
pub enum ComponentKind {
    Jump,
    DodgeTorque,
    DoubleJumpImpulse,
    Boost,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct DemoEventIn {
    pub t: f64,
    pub frame_index: Option<u32>,
    pub victim_id: String,
    pub attacker_id: Option<String>,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct TouchEventIn {
    pub t: f64,
    pub frame_index: Option<u32>,
    pub player_id: String,
    pub team: Option<i32>,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct KickoffMarkerIn {
    pub t: f64,
    pub frame_index: Option<u32>,
    pub phase: String,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
pub enum Mode {
    Seeded,
    Unseeded,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
pub enum EnginePreference {
    PortableOnly,
    PreferReference,
}

bitflags! {
    #[derive(Clone, Copy, Debug, Default, PartialEq, Eq, Hash, Serialize, Deserialize)]
    pub struct WithheldChannels: u32 {
        const THROTTLE = 1 << 0;
        const STEER = 1 << 1;
        const HANDBRAKE = 1 << 2;
        const BOOST_ACTIVE = 1 << 3;
        const BOOST_AMOUNT = 1 << 4;
        const JUMP_EDGES = 1 << 5;
        const COMPONENT_EVENTS = 1 << 6;
    }
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct EstimatorConfig {
    pub mode: Mode,
    pub withhold: WithheldChannels,
    pub engine: EnginePreference,
    pub fit: FitWeights,
    pub thresholds: SolverThresholds,
}

#[derive(Clone, Copy, Debug, PartialEq, Serialize, Deserialize)]
pub struct FitWeights {
    pub position_sigma: f32,
    pub velocity_sigma: f32,
    pub angular_velocity_sigma: f32,
    pub rotation_sigma: f32,
    pub reject_threshold: f32,
    pub low_margin_threshold: f32,
}

#[derive(Clone, Copy, Debug, PartialEq, Serialize, Deserialize)]
pub struct SolverThresholds {
    pub long_gap_seconds: f64,
    pub cadence_fraction_tolerance: f64,
    pub cadence_persistence_intervals: usize,
    pub nominal_interval_ticks: u64,
    pub car_proximity_uu: f32,
    pub ball_proximity_uu: f32,
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn replay_series_serde_round_trip() {
        let series = ReplaySeries {
            tick_rate: 120.0,
            build_bucket: "251202.62834.504897".to_string(),
            players: vec![PlayerSeries {
                player_id: "player_0".to_string(),
                frames: Kinematics {
                    pos: vec![[1.0, 2.0, 3.0]],
                    vel: vec![[4.0, 5.0, 6.0]],
                    quat_xyzw: vec![[0.0, 0.0, 0.0, 1.0]],
                    ang_vel: vec![[0.1, 0.2, 0.3]],
                    on_ground: vec![false],
                    sleeping: vec![false],
                    demolished: vec![false],
                },
                replicated: ReplicatedChannels {
                    throttle_raw: vec![255],
                    steer_raw: vec![128],
                    handbrake: vec![false],
                    boost_amount_raw: vec![80],
                    boost_active_raw: vec![true],
                },
                component: ComponentStream {
                    jump_raw: vec![0],
                    dodge_raw: vec![2],
                    double_jump_raw: vec![4],
                    boost_raw: vec![6],
                    events: vec![ComponentEventIn {
                        t: 1.25,
                        frame_index: 12,
                        component: ComponentKind::DodgeTorque,
                        vector: Some([1.0, 0.0, 0.0]),
                        raw_value: Some(2),
                    }],
                },
            }],
            ball: BallSeries {
                pos: vec![[0.0, 0.0, 93.15]],
                vel: vec![[0.0, 0.0, 0.0]],
            },
            deltas: vec![1.0 / 30.0],
            demo_events: vec![DemoEventIn {
                t: 3.0,
                frame_index: Some(90),
                victim_id: "player_1".to_string(),
                attacker_id: Some("player_0".to_string()),
            }],
            touch_events: vec![TouchEventIn {
                t: 2.0,
                frame_index: Some(60),
                player_id: "player_0".to_string(),
                team: Some(0),
            }],
            kickoff_markers: vec![KickoffMarkerIn {
                t: 0.0,
                frame_index: Some(0),
                phase: "INITIAL".to_string(),
            }],
        };

        let json = serde_json::to_string(&series).expect("ReplaySeries should serialize");
        let decoded: ReplaySeries =
            serde_json::from_str(&json).expect("ReplaySeries should deserialize");
        assert_eq!(decoded, series);
    }

    #[test]
    fn estimator_config_serde_round_trip() {
        let config = EstimatorConfig {
            mode: Mode::Unseeded,
            withhold: WithheldChannels::BOOST_ACTIVE | WithheldChannels::JUMP_EDGES,
            engine: EnginePreference::PortableOnly,
            fit: FitWeights {
                position_sigma: 20.0,
                velocity_sigma: 40.0,
                angular_velocity_sigma: 0.2,
                rotation_sigma: 0.01,
                reject_threshold: 6.0,
                low_margin_threshold: 0.05,
            },
            thresholds: SolverThresholds {
                long_gap_seconds: 0.15,
                cadence_fraction_tolerance: 0.35,
                cadence_persistence_intervals: 3,
                nominal_interval_ticks: 4,
                car_proximity_uu: 350.0,
                ball_proximity_uu: 190.0,
            },
        };

        let json = serde_json::to_string(&config).expect("EstimatorConfig should serialize");
        let decoded: EstimatorConfig =
            serde_json::from_str(&json).expect("EstimatorConfig should deserialize");
        assert_eq!(decoded, config);
    }
}
