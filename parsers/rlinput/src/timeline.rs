use bitflags::bitflags;
use serde::{Deserialize, Serialize};

#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
pub enum Source {
    Replicated,
    Solved,
    Inferred,
    Absent,
}

bitflags! {
    #[derive(Clone, Copy, Debug, Default, PartialEq, Eq, Hash, Serialize, Deserialize)]
    pub struct AmbiguityFlags: u32 {
        const COLLISION_SUSPECTED = 1 << 0;
        const CAR_PROXIMITY = 1 << 1;
        const BALL_PROXIMITY = 1 << 2;
        const POSSIBLE_PARTIAL_CANCEL = 1 << 3;
        const PITCHLOCK_ACTIVE = 1 << 4;
        const FLIP_TORQUE_ACTIVE = 1 << 5;
        const ANGVEL_SATURATED = 1 << 6;
        const LONG_GAP = 1 << 7;
        const DUPLICATE_FRAME = 1 << 8;
        const LOW_MARGIN = 1 << 9;
        const STALL_SUSPECTED = 1 << 10;
        const BOUNDARY_ADJACENT = 1 << 11;
        const SURFACE_PROXIMITY = 1 << 12;
    }
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct Channel<T> {
    pub value: T,
    pub source: Source,
    pub confidence: f32,
    pub flags: AmbiguityFlags,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct InputSample {
    pub frame_index: u32,
    pub tick_range: (u64, u64),
    pub time_range: (f64, f64),
    pub throttle: Channel<f32>,
    pub steer: Channel<f32>,
    pub pitch: Channel<f32>,
    pub yaw: Channel<f32>,
    pub roll: Channel<f32>,
    pub jump: Channel<bool>,
    pub boost: Channel<bool>,
    pub handbrake: Channel<bool>,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct CancelSummary {
    pub onset_tick: Option<u64>,
    pub peak_pitch: f32,
    pub full_cancel: bool,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub enum SolvedEventKind {
    JumpPress,
    JumpRelease,
    DoubleJump,
    Dodge {
        dir: [f32; 2],
        cancel: CancelSummary,
    },
    Stall,
    Liftoff,
    Landing,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct SolvedEvent {
    pub kind: SolvedEventKind,
    pub tick: u64,
    pub t: f64,
    pub frame_index: u32,
    pub confidence: f32,
    pub flags: AmbiguityFlags,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct InputTimeline {
    pub player_id: String,
    pub samples: Vec<InputSample>,
    pub events: Vec<SolvedEvent>,
    pub segments: Vec<SegmentSummary>,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct SegmentSummary {
    pub id: u32,
    pub tick_span: (u64, u64),
    pub boundary_causes: Vec<BoundaryCause>,
    pub confidence: f32,
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
pub enum BoundaryCause {
    BallTouch,
    BallProximity,
    CarContactSuspected,
    Demolition,
    Respawn,
    KickoffReset,
    Liftoff,
    Landing,
    SurfaceProximity,
    StreamEdge,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct SolveOutput {
    pub timelines: Vec<InputTimeline>,
    pub coverage: CoverageReport,
    pub diagnostics: SolveDiagnostics,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct CoverageReport {
    pub air_segments: u64,
    pub air_segments_confident: u64,
    pub coverage: f32,
    pub duration_weighted_coverage: f32,
    pub excluded_player_seconds_by_cause: Vec<ExclusionBreakdown>,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct ExclusionBreakdown {
    pub cause: BoundaryCause,
    pub player_seconds: f64,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct SolveDiagnostics {
    pub nonstandard_cadence: bool,
    pub lattice: Vec<LatticeDiagnostic>,
    pub warnings: Vec<String>,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct LatticeDiagnostic {
    pub kind: String,
    pub first_frame_index: u32,
    pub count: usize,
}

#[cfg(test)]
mod tests {
    use super::*;

    fn f32_channel(value: f32, source: Source) -> Channel<f32> {
        Channel {
            value,
            source,
            confidence: 0.75,
            flags: AmbiguityFlags::empty(),
        }
    }

    fn bool_channel(value: bool, source: Source) -> Channel<bool> {
        Channel {
            value,
            source,
            confidence: 1.0,
            flags: AmbiguityFlags::LOW_MARGIN,
        }
    }

    #[test]
    fn solve_output_serde_round_trip() {
        let output = SolveOutput {
            timelines: vec![InputTimeline {
                player_id: "player_0".to_string(),
                samples: vec![InputSample {
                    frame_index: 7,
                    tick_range: (28, 32),
                    time_range: (1.0, 1.0 + 1.0 / 30.0),
                    throttle: f32_channel(1.0, Source::Replicated),
                    steer: f32_channel(-0.5, Source::Replicated),
                    pitch: f32_channel(0.25, Source::Solved),
                    yaw: f32_channel(0.0, Source::Inferred),
                    roll: f32_channel(-0.25, Source::Solved),
                    jump: bool_channel(true, Source::Solved),
                    boost: bool_channel(false, Source::Absent),
                    handbrake: bool_channel(false, Source::Replicated),
                }],
                events: vec![SolvedEvent {
                    kind: SolvedEventKind::Dodge {
                        dir: [0.0, 1.0],
                        cancel: CancelSummary {
                            onset_tick: Some(30),
                            peak_pitch: 1.0,
                            full_cancel: true,
                        },
                    },
                    tick: 30,
                    t: 1.25,
                    frame_index: 9,
                    confidence: 0.9,
                    flags: AmbiguityFlags::POSSIBLE_PARTIAL_CANCEL,
                }],
                segments: vec![SegmentSummary {
                    id: 1,
                    tick_span: (28, 40),
                    boundary_causes: vec![BoundaryCause::Liftoff, BoundaryCause::StreamEdge],
                    confidence: 0.8,
                }],
            }],
            coverage: CoverageReport {
                air_segments: 10,
                air_segments_confident: 8,
                coverage: 0.8,
                duration_weighted_coverage: 0.75,
                excluded_player_seconds_by_cause: vec![ExclusionBreakdown {
                    cause: BoundaryCause::BallProximity,
                    player_seconds: 1.5,
                }],
            },
            diagnostics: SolveDiagnostics {
                nonstandard_cadence: true,
                lattice: vec![LatticeDiagnostic {
                    kind: "nonstandard_cadence".to_string(),
                    first_frame_index: 12,
                    count: 4,
                }],
                warnings: vec!["synthetic".to_string()],
            },
        };

        let json = serde_json::to_string(&output).expect("SolveOutput should serialize");
        let decoded: SolveOutput =
            serde_json::from_str(&json).expect("SolveOutput should deserialize");
        assert_eq!(decoded, output);
    }
}
