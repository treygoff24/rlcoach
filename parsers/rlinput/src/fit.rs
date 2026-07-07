use serde::{Deserialize, Serialize};

use crate::{
    engine::{AirEngine, CarPhysState, Controls, TickEvent, TickEventKind, TickPlan},
    model::FitWeights,
    timeline::AmbiguityFlags,
};

#[derive(Clone, Copy, Debug, PartialEq, Serialize, Deserialize)]
pub enum HypothesisEvent {
    Null,
    JumpPress,
    JumpRelease,
    DoubleJump,
    Dodge { dir: [f32; 2] },
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct FitHypothesis {
    pub event: HypothesisEvent,
    pub tick_offset: u32,
    pub controls: Vec<Controls>,
}

impl FitHypothesis {
    pub fn null(controls: Vec<Controls>) -> Self {
        Self {
            event: HypothesisEvent::Null,
            tick_offset: 0,
            controls,
        }
    }

    pub fn event(event: HypothesisEvent, tick_offset: u32, controls: Vec<Controls>) -> Self {
        Self {
            event,
            tick_offset,
            controls,
        }
    }

    pub fn is_null(&self) -> bool {
        self.event == HypothesisEvent::Null
    }

    pub fn to_tick_plan(&self) -> TickPlan {
        let events = match self.event {
            HypothesisEvent::Null => Vec::new(),
            HypothesisEvent::JumpPress => vec![event(self.tick_offset, TickEventKind::JumpPress)],
            HypothesisEvent::JumpRelease => {
                vec![event(self.tick_offset, TickEventKind::JumpRelease)]
            }
            HypothesisEvent::DoubleJump => vec![event(self.tick_offset, TickEventKind::DoubleJump)],
            HypothesisEvent::Dodge { dir } => {
                vec![event(self.tick_offset, TickEventKind::Dodge { dir })]
            }
        };
        TickPlan {
            controls: self.controls.clone(),
            events,
        }
    }
}

#[derive(Clone, Debug, PartialEq)]
pub struct FitResult {
    pub hypothesis: FitHypothesis,
    pub sim_end: CarPhysState,
    pub energy: f64,
    pub probability: f64,
    pub confidence: f32,
    pub flags: AmbiguityFlags,
}

pub fn provisional_fit_weights() -> FitWeights {
    FitWeights::default()
}

pub fn placement_hypotheses(
    event: HypothesisEvent,
    interval_ticks: u32,
    controls: Vec<Controls>,
) -> Vec<FitHypothesis> {
    (0..interval_ticks)
        .map(|tick| FitHypothesis::event(event, tick, controls.clone()))
        .collect()
}

pub fn fit_interval<E: AirEngine>(
    engine: &mut E,
    state_k: &CarPhysState,
    hypotheses: &[FitHypothesis],
    observed_end: &CarPhysState,
    weights: &FitWeights,
    ticks: u32,
) -> Vec<FitResult> {
    if hypotheses.is_empty() {
        return Vec::new();
    }

    if let Some(null) = hypotheses.iter().find(|hypothesis| hypothesis.is_null()) {
        let null_result = evaluate(engine, state_k, null, observed_end, weights, ticks);
        if null_result.energy <= f64::from(weights.reject_threshold) {
            return rank_results(vec![null_result], weights);
        }
    }

    rank_results(
        hypotheses
            .iter()
            .map(|hypothesis| evaluate(engine, state_k, hypothesis, observed_end, weights, ticks))
            .collect(),
        weights,
    )
}

pub fn score(sim_end: &CarPhysState, observed_end: &CarPhysState, weights: &FitWeights) -> f64 {
    squared_norm(diff(sim_end.pos, observed_end.pos)) / sigma2(weights.position_sigma)
        + squared_norm(diff(sim_end.vel, observed_end.vel)) / sigma2(weights.velocity_sigma)
        + rotation_distance_rad(sim_end.rot, observed_end.rot).powi(2)
            / sigma2(weights.rotation_sigma)
        + squared_norm(diff(sim_end.ang_vel, observed_end.ang_vel))
            / sigma2(weights.angular_velocity_sigma)
}

pub fn rotation_distance_rad(a: [[f32; 3]; 3], b: [[f32; 3]; 3]) -> f64 {
    let trace = dot(col(a, 0), col(b, 0)) + dot(col(a, 1), col(b, 1)) + dot(col(a, 2), col(b, 2));
    ((f64::from(trace) - 1.0) * 0.5).clamp(-1.0, 1.0).acos()
}

fn evaluate<E: AirEngine>(
    engine: &mut E,
    state_k: &CarPhysState,
    hypothesis: &FitHypothesis,
    observed_end: &CarPhysState,
    weights: &FitWeights,
    ticks: u32,
) -> FitResult {
    let sim_end = engine.rollout(state_k, &hypothesis.to_tick_plan(), ticks);
    FitResult {
        hypothesis: hypothesis.clone(),
        energy: score(&sim_end, observed_end, weights),
        sim_end,
        probability: 0.0,
        confidence: 0.0,
        flags: AmbiguityFlags::empty(),
    }
}

fn rank_results(mut results: Vec<FitResult>, weights: &FitWeights) -> Vec<FitResult> {
    if results.is_empty() {
        return results;
    }

    let best = results
        .iter()
        .map(|result| result.energy)
        .fold(f64::INFINITY, f64::min);
    let normalizer: f64 = results
        .iter()
        .map(|result| (-(result.energy - best)).exp())
        .sum();

    let mut best_probability = 0.0;
    for result in &mut results {
        result.probability = (-(result.energy - best)).exp() / normalizer;
        result.confidence = result.probability as f32;
        best_probability = f64::max(best_probability, result.probability);
    }

    if best > f64::from(weights.reject_threshold) {
        for result in &mut results {
            result.confidence = result.confidence.min(0.3);
        }
    }
    if best_probability < f64::from(weights.low_margin_threshold) {
        for result in &mut results {
            result.flags |= AmbiguityFlags::LOW_MARGIN;
        }
    }

    results.sort_by(|a, b| a.energy.total_cmp(&b.energy));
    results
}

fn event(tick_offset: u32, kind: TickEventKind) -> TickEvent {
    TickEvent { tick_offset, kind }
}

fn sigma2(sigma: f32) -> f64 {
    f64::from(sigma).powi(2)
}

fn diff(a: [f32; 3], b: [f32; 3]) -> [f32; 3] {
    [a[0] - b[0], a[1] - b[1], a[2] - b[2]]
}

fn squared_norm(v: [f32; 3]) -> f64 {
    f64::from(v[0]).powi(2) + f64::from(v[1]).powi(2) + f64::from(v[2]).powi(2)
}

fn col(m: [[f32; 3]; 3], idx: usize) -> [f32; 3] {
    [m[0][idx], m[1][idx], m[2][idx]]
}

fn dot(a: [f32; 3], b: [f32; 3]) -> f32 {
    a[0] * b[0] + a[1] * b[1] + a[2] * b[2]
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::{convert::identity_rot_mat, engine::portable::PortableEngine};

    const TICKS: u32 = 4;

    #[test]
    fn score_matches_hand_computed_terms() {
        let weights = provisional_fit_weights();
        let start = state();
        let mut observed = start;
        observed.pos = [weights.position_sigma, 0.0, 0.0];
        observed.vel = [0.0, weights.velocity_sigma, 0.0];
        observed.rot = rot_z(weights.rotation_sigma);
        observed.ang_vel = [0.0, 0.0, weights.angular_velocity_sigma];

        assert!((score(&start, &observed, &weights) - 4.0).abs() < 1e-4);
    }

    #[test]
    fn confidence_caps_rejected_results_and_marks_low_margin() {
        let weights = provisional_fit_weights();
        let rejected = rank_results(
            vec![
                fake_result(30.0, HypothesisEvent::Null),
                fake_result(31.0, HypothesisEvent::DoubleJump),
            ],
            &weights,
        );
        assert!(rejected[0].confidence <= 0.3);

        let low_margin = rank_results(
            vec![
                fake_result(0.0, HypothesisEvent::Null),
                fake_result(0.1, HypothesisEvent::DoubleJump),
            ],
            &weights,
        );
        assert!(low_margin[0].probability < 0.6);
        assert!(low_margin[0].flags.contains(AmbiguityFlags::LOW_MARGIN));
    }

    #[test]
    fn null_fast_path_scores_only_quiet_interval_but_not_flip_interval() {
        let weights = provisional_fit_weights();
        let start = state();
        let controls = vec![Controls::default(); TICKS as usize];
        let hypotheses = vec![
            FitHypothesis::null(controls.clone()),
            FitHypothesis::event(
                HypothesisEvent::Dodge { dir: [1.0, 0.0] },
                0,
                controls.clone(),
            ),
        ];

        let quiet = PortableEngine::new().rollout(
            &start,
            &FitHypothesis::null(controls.clone()).to_tick_plan(),
            TICKS,
        );
        let quiet_results = fit_interval(
            &mut PortableEngine::new(),
            &start,
            &hypotheses,
            &quiet,
            &weights,
            TICKS,
        );
        assert_eq!(quiet_results.len(), 1);
        assert!(quiet_results[0].hypothesis.is_null());

        let flip = PortableEngine::new().rollout(
            &start,
            &FitHypothesis::event(HypothesisEvent::Dodge { dir: [1.0, 0.0] }, 0, controls)
                .to_tick_plan(),
            TICKS,
        );
        let flip_results = fit_interval(
            &mut PortableEngine::new(),
            &start,
            &hypotheses,
            &flip,
            &weights,
            TICKS,
        );
        assert!(flip_results.len() > 1);
        assert_eq!(
            flip_results[0].hypothesis.event,
            HypothesisEvent::Dodge { dir: [1.0, 0.0] }
        );
    }

    #[test]
    fn fit_is_deterministic() {
        let weights = provisional_fit_weights();
        let start = state();
        let controls = vec![Controls::default(); TICKS as usize];
        let hypotheses = placement_hypotheses(
            HypothesisEvent::Dodge { dir: [0.0, 1.0] },
            TICKS,
            controls.clone(),
        );
        let observed = PortableEngine::new().rollout(
            &start,
            &FitHypothesis::event(HypothesisEvent::Dodge { dir: [0.0, 1.0] }, 2, controls)
                .to_tick_plan(),
            TICKS,
        );

        let a = fit_interval(
            &mut PortableEngine::new(),
            &start,
            &hypotheses,
            &observed,
            &weights,
            TICKS,
        );
        let b = fit_interval(
            &mut PortableEngine::new(),
            &start,
            &hypotheses,
            &observed,
            &weights,
            TICKS,
        );
        assert_eq!(a, b);
    }

    #[test]
    fn benchmark_fit_primitives() {
        let weights = provisional_fit_weights();
        let start = state();
        let controls = vec![Controls::default(); TICKS as usize];
        let observed = PortableEngine::new().rollout(
            &start,
            &FitHypothesis::null(controls.clone()).to_tick_plan(),
            TICKS,
        );
        let null_hypotheses = vec![
            FitHypothesis::null(controls.clone()),
            FitHypothesis::event(HypothesisEvent::DoubleJump, 0, controls.clone()),
        ];
        let event_hypotheses: Vec<_> = (0..48)
            .map(|idx| {
                FitHypothesis::event(
                    HypothesisEvent::Dodge {
                        dir: dodge_dir(idx),
                    },
                    idx % TICKS,
                    controls.clone(),
                )
            })
            .collect();

        let iterations = 2_000;
        let started = std::time::Instant::now();
        for _ in 0..iterations {
            let _ = fit_interval(
                &mut PortableEngine::new(),
                &start,
                &null_hypotheses,
                &observed,
                &weights,
                TICKS,
            );
        }
        let null_sims = iterations as f64 / started.elapsed().as_secs_f64();

        let event_observed =
            PortableEngine::new().rollout(&start, &event_hypotheses[17].to_tick_plan(), TICKS);
        let started = std::time::Instant::now();
        for _ in 0..iterations {
            let _ = fit_interval(
                &mut PortableEngine::new(),
                &start,
                &event_hypotheses,
                &event_observed,
                &weights,
                TICKS,
            );
        }
        let event_sims =
            (iterations * event_hypotheses.len()) as f64 / started.elapsed().as_secs_f64();
        println!("benchmark,null_intervals_per_sec={null_sims:.0},event_short_sims_per_sec={event_sims:.0}");
        assert!(null_sims > 10_000.0);
        assert!(event_sims > 10_000.0);
    }

    fn fake_result(energy: f64, event: HypothesisEvent) -> FitResult {
        FitResult {
            hypothesis: FitHypothesis::event(event, 0, vec![Controls::default(); TICKS as usize]),
            sim_end: state(),
            energy,
            probability: 0.0,
            confidence: 0.0,
            flags: AmbiguityFlags::empty(),
        }
    }

    pub(crate) fn state() -> CarPhysState {
        CarPhysState {
            pos: [0.0; 3],
            vel: [0.0; 3],
            rot: identity_rot_mat(),
            ang_vel: [0.0; 3],
            boost: 100.0,
            is_boosting: false,
            boosting_time: 0.0,
            has_jumped: true,
            has_double_jumped: false,
            has_flipped: false,
            is_jumping: false,
            is_flipping: false,
            jump_time: 0.1,
            flip_time: 0.0,
            air_time_since_jump: 0.1,
            flip_rel_torque: [0.0; 3],
        }
    }

    fn dodge_dir(idx: u32) -> [f32; 2] {
        let angle = idx as f32 * 0.37;
        [angle.cos(), angle.sin()]
    }

    fn rot_z(angle: f32) -> [[f32; 3]; 3] {
        let c = angle.cos();
        let s = angle.sin();
        [[c, -s, 0.0], [s, c, 0.0], [0.0, 0.0, 1.0]]
    }
}

#[cfg(test)]
mod noise_floor {
    use super::*;
    use crate::{
        channels::{
            aerial::{solve_axis_from_observations, AerialAxis, AxisObservation},
            boost::{solve_boost, BoostObservation},
        },
        consts,
        convert::{identity_rot_mat, replay_quat_xyzw_to_rot_mat},
        engine::{portable::PortableEngine, CarPhysState, Controls, TickPlan},
        model::{
            BallSeries, ComponentStream, Kinematics, PlayerSeries, ReplaySeries, ReplicatedChannels,
        },
        segment::{segment_replay, PlayerSegmentation, SegmentKind},
        tracker::reconstruct_seeded_edges,
    };

    const QUIET_AIR_CONTROL_MAX: f32 = 0.12;
    const INPUT_DEADZONE_RAW: i16 = 13;

    #[test]
    fn quiet_interval_selection_accepts_gravity_only_air() {
        let start = measurement_state();
        let end =
            PortableEngine::new().rollout(&start, &TickPlan::constant(Controls::default()), 4);
        let series = synthetic_series(start, end);

        assert_eq!(quiet_interval_count(&series), 1);
    }

    #[test]
    fn quiet_interval_selection_rejects_boost_signature() {
        let start = measurement_state();
        let end = PortableEngine::new().rollout(
            &start,
            &TickPlan::constant(Controls {
                boost: true,
                ..Controls::default()
            }),
            4,
        );
        let series = synthetic_series(start, end);

        assert_eq!(quiet_interval_count(&series), 0);
    }

    fn quiet_interval_count(series: &ReplaySeries) -> usize {
        let segmented = segment_replay(series);
        segmented
            .players
            .iter()
            .filter_map(|segmented_player| {
                series
                    .players
                    .iter()
                    .find(|player| player.player_id == segmented_player.player_id)
                    .map(|player| (segmented_player, player))
            })
            .map(|(segmented_player, player)| {
                let component_edge_frames = component_edge_frames(player);
                segmented_player
                    .segments
                    .iter()
                    .filter(|segment| segment.kind == SegmentKind::Air)
                    .flat_map(|segment| &segment.lattice.intervals)
                    .filter(|interval| {
                        quiet_interval(
                            series,
                            player,
                            segmented_player,
                            &component_edge_frames,
                            interval,
                        )
                    })
                    .count()
            })
            .sum()
    }

    fn quiet_interval(
        series: &ReplaySeries,
        player: &PlayerSeries,
        segmented_player: &PlayerSegmentation,
        component_edge_frames: &[u32],
        interval: &crate::lattice::LatticeInterval,
    ) -> bool {
        let frame = interval.frame_index as usize;
        let Some(prev) = frame.checked_sub(1) else {
            return false;
        };
        let ticks = interval.tick_range.1.saturating_sub(interval.tick_range.0);
        let dt = delta_for(series, frame);
        if ticks == 0
            || ticks > u64::from(u32::MAX)
            || dt <= f32::EPSILON
            || !interval.flags.is_empty()
            || interval_flagged(segmented_player, interval.frame_index)
            || frame >= player.frames.pos.len()
            || !air_at(player, prev)
            || !air_at(player, frame)
        {
            return false;
        }

        !has_component_edge(component_edge_frames, frame)
            && neutral_replicated_inputs(player, prev, frame)
            && !has_boost_signature(player, prev, frame, dt)
            && angular_change_is_damping(player, prev, frame, ticks as u32, interval.tick_range)
    }

    fn interval_flagged(segmented_player: &PlayerSegmentation, frame: u32) -> bool {
        segmented_player.interval_flags.iter().any(|flags| {
            flags.frame_index == frame && (!flags.flags.is_empty() || !flags.causes.is_empty())
        })
    }

    fn component_edge_frames(player: &PlayerSeries) -> Vec<u32> {
        reconstruct_seeded_edges(&player.component)
            .into_iter()
            .map(|edge| edge.frame_index)
            .collect()
    }

    fn has_component_edge(component_edge_frames: &[u32], frame: usize) -> bool {
        component_edge_frames
            .iter()
            .any(|edge_frame| *edge_frame as usize == frame)
    }

    fn neutral_replicated_inputs(player: &PlayerSeries, prev: usize, frame: usize) -> bool {
        raw_neutral(player.replicated.throttle_raw.get(prev).copied())
            && raw_neutral(player.replicated.throttle_raw.get(frame).copied())
            && raw_neutral(player.replicated.steer_raw.get(prev).copied())
            && raw_neutral(player.replicated.steer_raw.get(frame).copied())
            && !bool_at(&player.replicated.handbrake, prev)
            && !bool_at(&player.replicated.handbrake, frame)
            && !bool_at(&player.replicated.boost_active_raw, prev)
            && !bool_at(&player.replicated.boost_active_raw, frame)
            && player.replicated.boost_amount_raw.get(prev)
                == player.replicated.boost_amount_raw.get(frame)
    }

    fn raw_neutral(value: Option<u8>) -> bool {
        value.is_some_and(|value| (i16::from(value) - 128).abs() <= INPUT_DEADZONE_RAW)
    }

    fn has_boost_signature(player: &PlayerSeries, prev: usize, frame: usize, dt: f32) -> bool {
        let delta_v = diff(player.frames.vel[frame], player.frames.vel[prev]);
        solve_boost(BoostObservation {
            tick: 0,
            dt,
            delta_v,
            nose: forward(replay_quat_xyzw_to_rot_mat(player.frames.quat_xyzw[prev])),
            grounded: false,
            forward_speed: 0.0,
            longitudinal_accel: 0.0,
        })
        .value
    }

    fn angular_change_is_damping(
        player: &PlayerSeries,
        prev: usize,
        frame: usize,
        ticks: u32,
        tick_range: (u64, u64),
    ) -> bool {
        let start = AxisObservation {
            rot: replay_quat_xyzw_to_rot_mat(player.frames.quat_xyzw[prev]),
            ang_vel: player.frames.ang_vel[prev],
        };
        let end = AxisObservation {
            rot: replay_quat_xyzw_to_rot_mat(player.frames.quat_xyzw[frame]),
            ang_vel: player.frames.ang_vel[frame],
        };
        [AerialAxis::Pitch, AerialAxis::Yaw, AerialAxis::Roll]
            .into_iter()
            .all(|axis| {
                let solved =
                    solve_axis_from_observations(axis, start, end, ticks, tick_range, None);
                solved.flags.is_empty() && solved.value.abs() <= QUIET_AIR_CONTROL_MAX
            })
    }

    fn air_at(player: &PlayerSeries, frame: usize) -> bool {
        !bool_at(&player.frames.on_ground, frame)
            && !bool_at(&player.frames.sleeping, frame)
            && !bool_at(&player.frames.demolished, frame)
    }

    fn bool_at(values: &[bool], frame: usize) -> bool {
        values.get(frame).copied().unwrap_or(false)
    }

    #[cfg(feature = "sim")]
    fn observed_state(player: &PlayerSeries, frame: usize) -> CarPhysState {
        CarPhysState {
            pos: player.frames.pos[frame],
            vel: player.frames.vel[frame],
            rot: replay_quat_xyzw_to_rot_mat(player.frames.quat_xyzw[frame]),
            ang_vel: player.frames.ang_vel[frame],
            boost: player
                .replicated
                .boost_amount_raw
                .get(frame)
                .copied()
                .map(f32::from)
                .unwrap_or(consts::BOOST_MAX)
                .min(consts::BOOST_MAX),
            is_boosting: bool_at(&player.replicated.boost_active_raw, frame),
            boosting_time: 0.0,
            has_jumped: true,
            has_double_jumped: false,
            has_flipped: false,
            is_jumping: false,
            is_flipping: false,
            jump_time: 0.1,
            flip_time: 0.0,
            air_time_since_jump: 0.1,
            flip_rel_torque: [0.0; 3],
        }
    }

    fn delta_for(series: &ReplaySeries, terminating_frame: usize) -> f32 {
        if series.deltas.len() > terminating_frame {
            series.deltas[terminating_frame]
        } else if terminating_frame > 0 && series.deltas.len() >= terminating_frame {
            series.deltas[terminating_frame - 1]
        } else {
            0.0
        }
    }

    fn forward(rot: [[f32; 3]; 3]) -> [f32; 3] {
        [rot[0][0], rot[1][0], rot[2][0]]
    }

    #[cfg(feature = "sim")]
    fn distance(a: [f32; 3], b: [f32; 3]) -> f32 {
        squared_norm(diff(a, b)).sqrt() as f32
    }

    fn measurement_state() -> CarPhysState {
        CarPhysState {
            pos: [0.0, 0.0, 1_000.0],
            vel: [500.0, 0.0, 100.0],
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
            jump_time: 0.1,
            flip_time: 0.0,
            air_time_since_jump: 0.1,
            flip_rel_torque: [0.0; 3],
        }
    }

    fn synthetic_series(start: CarPhysState, end: CarPhysState) -> ReplaySeries {
        ReplaySeries {
            tick_rate: 120.0,
            build_bucket: "synthetic".to_string(),
            players: vec![PlayerSeries {
                player_id: "p0".to_string(),
                frames: Kinematics {
                    pos: vec![start.pos, end.pos],
                    vel: vec![start.vel, end.vel],
                    quat_xyzw: vec![[0.0, 0.0, 0.0, 1.0]; 2],
                    ang_vel: vec![start.ang_vel, end.ang_vel],
                    on_ground: vec![false; 2],
                    sleeping: vec![false; 2],
                    demolished: vec![false; 2],
                },
                replicated: ReplicatedChannels {
                    throttle_raw: vec![128; 2],
                    steer_raw: vec![128; 2],
                    handbrake: vec![false; 2],
                    boost_amount_raw: vec![100; 2],
                    boost_active_raw: vec![false; 2],
                },
                component: ComponentStream {
                    jump_raw: vec![0; 2],
                    dodge_raw: vec![0; 2],
                    double_jump_raw: vec![0; 2],
                    boost_raw: vec![0; 2],
                    events: Vec::new(),
                },
            }],
            ball: BallSeries {
                pos: vec![[10_000.0, 10_000.0, 1_000.0]; 2],
                vel: vec![[0.0; 3]; 2],
            },
            deltas: vec![0.0, 1.0 / 30.0],
            demo_events: Vec::new(),
            touch_events: Vec::new(),
            kickoff_markers: Vec::new(),
        }
    }

    #[cfg(feature = "sim")]
    #[test]
    #[ignore = "local dev-set measurement; run: RLINPUT_DEV_SERIES_DIR=/path/to/series cargo test -p rlinput --features sim noise_floor_measurement -- --ignored --nocapture"]
    fn noise_floor_measurement() {
        use crate::engine::{rocketsim::RocketSimEngine, AirEngine};

        let dir = std::env::var("RLINPUT_DEV_SERIES_DIR")
            .expect("set RLINPUT_DEV_SERIES_DIR to the 10 exported dev-set JSON files");
        let mut paths: Vec<_> = std::fs::read_dir(&dir)
            .expect("read RLINPUT_DEV_SERIES_DIR")
            .map(|entry| entry.expect("read dir entry").path())
            .filter(|path| path.extension().is_some_and(|ext| ext == "json"))
            .collect();
        paths.sort();
        assert_eq!(
            paths.len(),
            10,
            "expected exactly the frozen 10 dev-set exports in {dir}"
        );

        let mut pooled = ResidualStats::default();
        for path in paths {
            let name = path
                .file_stem()
                .and_then(|stem| stem.to_str())
                .unwrap_or("unknown")
                .to_string();
            let json = std::fs::read_to_string(&path).expect("read exported ReplaySeries JSON");
            let series: ReplaySeries =
                serde_json::from_str(&json).expect("parse exported ReplaySeries JSON");
            let stats = measure_series(&series);
            println!("{}", stats.line(&name));
            pooled.extend(stats);
        }

        println!("{}", pooled.line("pooled"));
        println!(
            "sigma_choice,p68,pos={:.6},vel={:.6},rot={:.6},ang_vel={:.6}",
            pooled.pos.percentile(0.68),
            pooled.vel.percentile(0.68),
            pooled.rot.percentile(0.68),
            pooled.ang_vel.percentile(0.68),
        );
        assert!(
            pooled.len() >= 1_000,
            "pooled quiet interval count below acceptance floor: {}",
            pooled.len()
        );

        fn measure_series(series: &ReplaySeries) -> ResidualStats {
            let segmented = segment_replay(series);
            let mut engine = RocketSimEngine::new();
            let mut stats = ResidualStats::default();
            for segmented_player in &segmented.players {
                let Some(player) = series
                    .players
                    .iter()
                    .find(|player| player.player_id == segmented_player.player_id)
                else {
                    continue;
                };
                let component_edge_frames = component_edge_frames(player);
                for segment in segmented_player
                    .segments
                    .iter()
                    .filter(|segment| segment.kind == SegmentKind::Air)
                {
                    for interval in &segment.lattice.intervals {
                        if !quiet_interval(
                            series,
                            player,
                            segmented_player,
                            &component_edge_frames,
                            interval,
                        ) {
                            continue;
                        }
                        let frame = interval.frame_index as usize;
                        let Some(prev) = frame.checked_sub(1) else {
                            continue;
                        };
                        let ticks = (interval.tick_range.1 - interval.tick_range.0)
                            .min(u64::from(u32::MAX)) as u32;
                        let start = observed_state(player, prev);
                        let observed = observed_state(player, frame);
                        let simulated =
                            engine.rollout(&start, &TickPlan::constant(Controls::default()), ticks);
                        stats.push(&simulated, &observed);
                    }
                }
            }
            stats
        }
    }

    #[cfg(feature = "sim")]
    #[derive(Clone, Default)]
    struct ResidualStats {
        pos: Distribution,
        vel: Distribution,
        rot: Distribution,
        ang_vel: Distribution,
    }

    #[cfg(feature = "sim")]
    impl ResidualStats {
        fn push(&mut self, simulated: &CarPhysState, observed: &CarPhysState) {
            self.pos.push(distance(simulated.pos, observed.pos));
            self.vel.push(distance(simulated.vel, observed.vel));
            self.rot
                .push(rotation_distance_rad(simulated.rot, observed.rot) as f32);
            self.ang_vel
                .push(distance(simulated.ang_vel, observed.ang_vel));
        }

        fn extend(&mut self, other: Self) {
            self.pos.extend(other.pos);
            self.vel.extend(other.vel);
            self.rot.extend(other.rot);
            self.ang_vel.extend(other.ang_vel);
        }

        fn len(&self) -> usize {
            self.pos.values.len()
        }

        fn line(&self, name: &str) -> String {
            format!(
                "noise_floor,{name},count={},pos_p50={:.6},pos_p68={:.6},pos_p90={:.6},pos_p95={:.6},pos_p99={:.6},vel_p50={:.6},vel_p68={:.6},vel_p90={:.6},vel_p95={:.6},vel_p99={:.6},rot_p50={:.6},rot_p68={:.6},rot_p90={:.6},rot_p95={:.6},rot_p99={:.6},ang_vel_p50={:.6},ang_vel_p68={:.6},ang_vel_p90={:.6},ang_vel_p95={:.6},ang_vel_p99={:.6}",
                self.len(),
                self.pos.percentile(0.50),
                self.pos.percentile(0.68),
                self.pos.percentile(0.90),
                self.pos.percentile(0.95),
                self.pos.percentile(0.99),
                self.vel.percentile(0.50),
                self.vel.percentile(0.68),
                self.vel.percentile(0.90),
                self.vel.percentile(0.95),
                self.vel.percentile(0.99),
                self.rot.percentile(0.50),
                self.rot.percentile(0.68),
                self.rot.percentile(0.90),
                self.rot.percentile(0.95),
                self.rot.percentile(0.99),
                self.ang_vel.percentile(0.50),
                self.ang_vel.percentile(0.68),
                self.ang_vel.percentile(0.90),
                self.ang_vel.percentile(0.95),
                self.ang_vel.percentile(0.99),
            )
        }
    }

    #[cfg(feature = "sim")]
    #[derive(Clone, Default)]
    struct Distribution {
        values: Vec<f32>,
    }

    #[cfg(feature = "sim")]
    impl Distribution {
        fn push(&mut self, value: f32) {
            if value.is_finite() {
                self.values.push(value);
            }
        }

        fn extend(&mut self, other: Self) {
            self.values.extend(other.values);
        }

        fn percentile(&self, q: f32) -> f32 {
            if self.values.is_empty() {
                return f32::NAN;
            }
            let mut values = self.values.clone();
            values.sort_by(f32::total_cmp);
            values[((values.len() - 1) as f32 * q).round() as usize]
        }
    }
}

#[cfg(all(test, feature = "sim"))]
mod sim_tests {
    use super::*;
    use crate::{
        convert::identity_rot_mat,
        engine::{portable::PortableEngine, rocketsim::RocketSimEngine},
    };

    const TICKS: u32 = 4;
    const PROBE_SAMPLES: usize = 256;
    const BENCH_ITERATIONS: usize = 2_000;

    #[test]
    #[ignore = "expensive RocketSim probe; run: cargo test -p rlinput --features sim \
                discriminability_probe_dodges_and_double_jumps -- --ignored --nocapture"]
    fn discriminability_probe_dodges_and_double_jumps() {
        let dodge = probe(ProbeKind::Dodge, 0xD0D6E);
        let double_jump = probe(ProbeKind::DoubleJump, 0xD00B1E);
        println!("{}", dodge.line("dodge"));
        println!("{}", double_jump.line("double_jump"));
        assert!(dodge.clean_accuracy >= 0.95);
        assert!(dodge.noisy_accuracy >= 0.45);
        assert!(double_jump.clean_accuracy >= 0.90);
        // Measured WP6b position noise is far above the provisional 4 uu floor,
        // making sub-tick double-jump placement honestly near-degenerate.
        assert!(double_jump.noisy_accuracy >= 0.20);
    }

    #[test]
    #[ignore = "local throughput benchmark; run: cargo test -p rlinput --features sim \
                benchmark_reference_and_portable_fit_cycles -- --ignored --nocapture"]
    fn benchmark_reference_and_portable_fit_cycles() {
        let reference = benchmark_engine("RocketSimEngine", RocketSimEngine::new);
        let portable = benchmark_engine("PortableEngine", PortableEngine::new);
        println!("{}", reference.line());
        println!("{}", portable.line());
        assert!(reference.null_sims_per_sec > 1_000.0);
        assert!(reference.event_sims_per_sec > 1_000.0);
        assert!(portable.event_sims_per_sec > reference.event_sims_per_sec);
    }

    #[derive(Clone, Copy)]
    enum ProbeKind {
        Dodge,
        DoubleJump,
    }

    struct ProbeStats {
        clean_accuracy: f32,
        noisy_accuracy: f32,
        margins: Vec<f64>,
        shift_deltas: Vec<f32>,
    }

    impl ProbeStats {
        fn line(&self, name: &str) -> String {
            format!(
                "probe,{name},samples={PROBE_SAMPLES},clean_accuracy={:.3},noisy_accuracy={:.3},margin_p10={:.3},margin_p50={:.3},margin_p90={:.3},uu_shift_p10={:.3},uu_shift_p50={:.3},uu_shift_p90={:.3}",
                self.clean_accuracy,
                self.noisy_accuracy,
                percentile_f64(self.margins.clone(), 0.10),
                percentile_f64(self.margins.clone(), 0.50),
                percentile_f64(self.margins.clone(), 0.90),
                percentile_f32(self.shift_deltas.clone(), 0.10),
                percentile_f32(self.shift_deltas.clone(), 0.50),
                percentile_f32(self.shift_deltas.clone(), 0.90)
            )
        }
    }

    struct BenchStats {
        name: &'static str,
        null_sims_per_sec: f64,
        event_sims_per_sec: f64,
    }

    impl BenchStats {
        fn line(&self) -> String {
            let ten_k_seconds = 10_000.0 / self.event_sims_per_sec;
            let six_player_seconds = ten_k_seconds * 6.0;
            let k_one_second_player = (self.event_sims_per_sec / 200.0).floor();
            let k_ten_second_replay = (self.event_sims_per_sec * 10.0 / (6.0 * 200.0)).floor();
            format!(
                "benchmark,engine={},null_sims_per_sec={:.0},event_sims_per_sec={:.0},seconds_per_10k_player={:.3},seconds_per_6p_replay={:.3},affordable_k_1s_player={:.0},affordable_k_10s_6p_replay={:.0}",
                self.name,
                self.null_sims_per_sec,
                self.event_sims_per_sec,
                ten_k_seconds,
                six_player_seconds,
                k_one_second_player,
                k_ten_second_replay
            )
        }
    }

    fn probe(kind: ProbeKind, seed: u64) -> ProbeStats {
        let weights = provisional_fit_weights();
        let controls = vec![Controls::default(); TICKS as usize];
        let mut rng = Lcg::new(seed);
        let mut engine = RocketSimEngine::new();
        let mut clean_hits = 0;
        let mut noisy_hits = 0;
        let mut margins = Vec::new();
        let mut shift_deltas = Vec::new();

        for _ in 0..PROBE_SAMPLES {
            let start = random_state(&mut rng);
            let truth = rng.u32(0, TICKS);
            let event = match kind {
                ProbeKind::Dodge => HypothesisEvent::Dodge {
                    dir: random_dodge_dir(&mut rng),
                },
                ProbeKind::DoubleJump => HypothesisEvent::DoubleJump,
            };
            let hypotheses = placement_hypotheses(event, TICKS, controls.clone());
            let observed = engine.rollout(
                &start,
                &FitHypothesis::event(event, truth, controls.clone()).to_tick_plan(),
                TICKS,
            );
            let clean = fit_interval(&mut engine, &start, &hypotheses, &observed, &weights, TICKS);
            if clean[0].hypothesis.tick_offset == truth {
                clean_hits += 1;
            }
            margins.push(clean[1].energy - clean[0].energy);

            let noisy_observed = add_noise(observed, &weights, &mut rng);
            let noisy = fit_interval(
                &mut engine,
                &start,
                &hypotheses,
                &noisy_observed,
                &weights,
                TICKS,
            );
            if noisy[0].hypothesis.tick_offset == truth {
                noisy_hits += 1;
            }

            let ends: Vec<_> = hypotheses
                .iter()
                .map(|hypothesis| engine.rollout(&start, &hypothesis.to_tick_plan(), TICKS))
                .collect();
            for pair in ends.windows(2) {
                shift_deltas.push(dist(pair[0].pos, pair[1].pos));
            }
        }

        ProbeStats {
            clean_accuracy: clean_hits as f32 / PROBE_SAMPLES as f32,
            noisy_accuracy: noisy_hits as f32 / PROBE_SAMPLES as f32,
            margins,
            shift_deltas,
        }
    }

    fn benchmark_engine<E, F>(name: &'static str, make_engine: F) -> BenchStats
    where
        E: AirEngine,
        F: Fn() -> E,
    {
        let weights = provisional_fit_weights();
        let start = random_state(&mut Lcg::new(0xBEEFCACE));
        let controls = vec![Controls::default(); TICKS as usize];
        let null = FitHypothesis::null(controls.clone());
        let null_hypotheses = vec![
            null.clone(),
            FitHypothesis::event(HypothesisEvent::DoubleJump, 0, controls.clone()),
        ];
        let event_hypotheses = event_benchmark_hypotheses(controls);

        let mut engine = make_engine();
        let observed_null = engine.rollout(&start, &null.to_tick_plan(), TICKS);
        let started = std::time::Instant::now();
        for _ in 0..BENCH_ITERATIONS {
            let _ = fit_interval(
                &mut engine,
                &start,
                &null_hypotheses,
                &observed_null,
                &weights,
                TICKS,
            );
        }
        let null_sims_per_sec = BENCH_ITERATIONS as f64 / started.elapsed().as_secs_f64();

        let observed_event = engine.rollout(&start, &event_hypotheses[17].to_tick_plan(), TICKS);
        let started = std::time::Instant::now();
        for _ in 0..BENCH_ITERATIONS {
            let _ = fit_interval(
                &mut engine,
                &start,
                &event_hypotheses,
                &observed_event,
                &weights,
                TICKS,
            );
        }
        let event_sims_per_sec =
            (BENCH_ITERATIONS * event_hypotheses.len()) as f64 / started.elapsed().as_secs_f64();

        BenchStats {
            name,
            null_sims_per_sec,
            event_sims_per_sec,
        }
    }

    fn event_benchmark_hypotheses(controls: Vec<Controls>) -> Vec<FitHypothesis> {
        (0..12)
            .flat_map(|dir_idx| {
                let angle = dir_idx as f32 * std::f32::consts::TAU / 12.0;
                let event = HypothesisEvent::Dodge {
                    dir: [angle.cos(), angle.sin()],
                };
                let controls = controls.clone();
                (0..TICKS).map(move |tick| FitHypothesis::event(event, tick, controls.clone()))
            })
            .collect()
    }

    fn random_state(rng: &mut Lcg) -> CarPhysState {
        CarPhysState {
            pos: [
                rng.range(-50_000.0, 50_000.0),
                rng.range(-50_000.0, 50_000.0),
                rng.range(500.0, 50_000.0),
            ],
            vel: scale(
                normalize(random_vec(rng, -1.0, 1.0)),
                rng.range(0.0, 2300.0),
            ),
            rot: random_rot(rng),
            ang_vel: scale(normalize(random_vec(rng, -1.0, 1.0)), rng.range(0.0, 5.5)),
            boost: rng.range(0.0, 100.0),
            is_boosting: false,
            boosting_time: 0.0,
            has_jumped: true,
            has_double_jumped: false,
            has_flipped: false,
            is_jumping: false,
            is_flipping: false,
            jump_time: 0.1,
            flip_time: 0.0,
            air_time_since_jump: rng.range(0.05, 1.0),
            flip_rel_torque: [0.0; 3],
        }
    }

    fn add_noise(mut state: CarPhysState, weights: &FitWeights, rng: &mut Lcg) -> CarPhysState {
        for idx in 0..3 {
            state.pos[idx] += rng.gaussian() * weights.position_sigma;
            state.vel[idx] += rng.gaussian() * weights.velocity_sigma;
            state.ang_vel[idx] += rng.gaussian() * weights.angular_velocity_sigma;
        }
        state.rot = mat_mul(
            axis_angle(
                normalize(random_vec(rng, -1.0, 1.0)),
                rng.gaussian() * weights.rotation_sigma,
            ),
            state.rot,
        );
        state
    }

    fn random_dodge_dir(rng: &mut Lcg) -> [f32; 2] {
        let angle = rng.range(-std::f32::consts::PI, std::f32::consts::PI);
        [angle.cos(), angle.sin()]
    }

    fn random_rot(rng: &mut Lcg) -> [[f32; 3]; 3] {
        axis_angle(
            normalize(random_vec(rng, -1.0, 1.0)),
            rng.range(-std::f32::consts::PI, std::f32::consts::PI),
        )
    }

    fn axis_angle(axis: [f32; 3], angle: f32) -> [[f32; 3]; 3] {
        if norm(axis) <= f32::EPSILON {
            return identity_rot_mat();
        }
        let [x, y, z] = normalize(axis);
        let c = angle.cos();
        let s = angle.sin();
        let t = 1.0 - c;
        [
            [t * x * x + c, t * x * y - s * z, t * x * z + s * y],
            [t * x * y + s * z, t * y * y + c, t * y * z - s * x],
            [t * x * z - s * y, t * y * z + s * x, t * z * z + c],
        ]
    }

    fn mat_mul(a: [[f32; 3]; 3], b: [[f32; 3]; 3]) -> [[f32; 3]; 3] {
        let mut out = [[0.0; 3]; 3];
        for row in 0..3 {
            for col in 0..3 {
                out[row][col] =
                    a[row][0] * b[0][col] + a[row][1] * b[1][col] + a[row][2] * b[2][col];
            }
        }
        out
    }

    fn random_vec(rng: &mut Lcg, min: f32, max: f32) -> [f32; 3] {
        [
            rng.range(min, max),
            rng.range(min, max),
            rng.range(min, max),
        ]
    }

    fn dist(a: [f32; 3], b: [f32; 3]) -> f32 {
        norm([a[0] - b[0], a[1] - b[1], a[2] - b[2]])
    }

    fn norm(v: [f32; 3]) -> f32 {
        (v[0] * v[0] + v[1] * v[1] + v[2] * v[2]).sqrt()
    }

    fn normalize(v: [f32; 3]) -> [f32; 3] {
        let n = norm(v);
        if n <= f32::EPSILON {
            [1.0, 0.0, 0.0]
        } else {
            [v[0] / n, v[1] / n, v[2] / n]
        }
    }

    fn scale(v: [f32; 3], s: f32) -> [f32; 3] {
        [v[0] * s, v[1] * s, v[2] * s]
    }

    fn percentile_f32(mut values: Vec<f32>, q: f32) -> f32 {
        values.sort_by(f32::total_cmp);
        values[((values.len() - 1) as f32 * q).round() as usize]
    }

    fn percentile_f64(mut values: Vec<f64>, q: f32) -> f64 {
        values.sort_by(f64::total_cmp);
        values[((values.len() - 1) as f32 * q).round() as usize]
    }

    struct Lcg(u64);

    impl Lcg {
        fn new(seed: u64) -> Self {
            Self(seed)
        }

        fn next(&mut self) -> u32 {
            self.0 = self
                .0
                .wrapping_mul(6_364_136_223_846_793_005)
                .wrapping_add(1);
            (self.0 >> 32) as u32
        }

        fn f32(&mut self) -> f32 {
            self.next() as f32 / u32::MAX as f32
        }

        fn range(&mut self, min: f32, max: f32) -> f32 {
            min + (max - min) * self.f32()
        }

        fn u32(&mut self, min: u32, max_exclusive: u32) -> u32 {
            min + (self.next() % (max_exclusive - min))
        }

        fn gaussian(&mut self) -> f32 {
            let u1 = self.f32().max(1e-6);
            let u2 = self.f32();
            (-2.0 * u1.ln()).sqrt() * (2.0 * std::f32::consts::PI * u2).cos()
        }
    }
}
