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
    FitWeights {
        position_sigma: 4.0,
        velocity_sigma: 20.0,
        rotation_sigma: 0.05,
        angular_velocity_sigma: 0.15,
        reject_threshold: 25.0,
        low_margin_threshold: 0.6,
    }
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
        observed.pos = [4.0, 0.0, 0.0];
        observed.vel = [0.0, 20.0, 0.0];
        observed.rot = rot_z(0.05);
        observed.ang_vel = [0.0, 0.0, 0.15];

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
        assert!(double_jump.noisy_accuracy >= 0.35);
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
