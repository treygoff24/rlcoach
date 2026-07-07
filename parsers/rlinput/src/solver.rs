use std::collections::{HashMap, HashSet};

use crate::{
    channels::{
        aerial::{solve_axis_from_observations, AerialAxis, AxisObservation},
        boost::{solve_boost, BoostObservation},
        ground::{
            solve_handbrake, solve_steer, solve_throttle, HandbrakeObservation, SteerObservation,
            ThrottleObservation,
        },
    },
    convert::{identity_rot_mat, replay_quat_xyzw_to_rot_mat, RotationMatrix},
    engine::{
        portable::PortableEngine, AirEngine, CarPhysState, Controls, TickEvent, TickEventKind,
        TickPlan,
    },
    fit::{provisional_fit_weights, score},
    lattice::LatticeInterval,
    model::{
        ComponentKind, ComponentStream, EnginePreference, EstimatorConfig, FitWeights, Mode,
        PlayerSeries, ReplaySeries, SolverThresholds, WithheldChannels,
    },
    segment::{
        segment_replay_with_splits_and_confidences, split_segment_at, RetroactiveSplit, Segment,
        SegmentKind,
    },
    timeline::{
        AmbiguityFlags, CancelSummary, Channel, InputSample, InputTimeline, LatticeDiagnostic,
        SolveDiagnostics, SolveOutput, SolvedEvent, SolvedEventKind, Source,
    },
    tracker::{
        classify_dodge_torque_vector, BranchingTracker, CarTracker, ContactState, JumpState,
        ReconstructedEdge, SecondAction, SecondActionClass,
    },
};

const CONFIDENT_SEGMENT_THRESHOLD: f32 = 0.7;
const RETRO_VELOCITY_RESIDUAL_UU_PER_S: f32 = 150.0;
const RETRO_CAR_PROXIMITY_UU: f32 = 500.0;
const LONG_GAP_CONFIDENCE_CAP: f32 = 0.5;
const HYPOTHESIS_CAP: usize = 256;
#[cfg(feature = "sim")]
const REFERENCE_SURVIVORS: usize = 2;

#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash)]
struct SegmentKey {
    player_index: usize,
    segment_id: u32,
    frame_span: (u32, u32),
}

#[derive(Clone, Debug)]
struct PlayerSolved {
    player_id: String,
    samples: Vec<InputSample>,
    events: Vec<SolvedEvent>,
}

#[derive(Clone, Debug)]
struct SolvePass {
    output: SolveOutput,
    retro_splits: Vec<RetroactiveSplit>,
}

#[derive(Clone, Debug)]
struct SeededHints {
    edges: HashMap<u32, Vec<ReconstructedEdge>>,
}

#[derive(Clone, Copy, Debug, PartialEq)]
enum CandidateEvent {
    JumpPress,
    JumpRelease,
    DoubleJump,
    Dodge { dir: [f32; 2] },
    Stall,
}

impl CandidateEvent {
    fn tick_kind(self) -> TickEventKind {
        match self {
            CandidateEvent::JumpPress => TickEventKind::JumpPress,
            CandidateEvent::JumpRelease => TickEventKind::JumpRelease,
            CandidateEvent::DoubleJump => TickEventKind::DoubleJump,
            CandidateEvent::Dodge { dir } => TickEventKind::Dodge { dir },
            CandidateEvent::Stall => TickEventKind::Dodge { dir: [0.0, 0.0] },
        }
    }
}

#[derive(Clone, Debug, PartialEq)]
struct CandidateAction {
    tick_offset: u32,
    event: CandidateEvent,
}

#[derive(Clone, Debug, PartialEq)]
struct Candidate {
    actions: Vec<CandidateAction>,
    controls: Vec<Controls>,
    flags: AmbiguityFlags,
    confidence_cap: f32,
}

impl Candidate {
    fn null(controls: Vec<Controls>, flags: AmbiguityFlags) -> Self {
        Self {
            actions: Vec::new(),
            controls,
            flags,
            confidence_cap: 1.0,
        }
    }

    fn to_tick_plan(&self) -> TickPlan {
        TickPlan {
            controls: self.controls.clone(),
            events: self
                .actions
                .iter()
                .map(|action| TickEvent {
                    tick_offset: action.tick_offset,
                    kind: action.event.tick_kind(),
                })
                .collect(),
        }
    }

    fn is_null(&self) -> bool {
        self.actions.is_empty()
    }
}

#[derive(Clone, Debug)]
struct ScoredCandidate {
    candidate: Candidate,
    sim_end: CarPhysState,
    energy: f64,
    probability: f64,
    confidence: f32,
    flags: AmbiguityFlags,
}

#[derive(Clone, Debug)]
struct IntervalSolve {
    sample: InputSample,
    events: Vec<SolvedEvent>,
    confidence: f32,
    retro_split: Option<RetroactiveSplit>,
    branch_options: Vec<BranchOption>,
}

#[derive(Clone, Debug)]
struct BranchOption {
    candidate: Candidate,
    score: f64,
}

#[derive(Clone, Debug)]
struct CandidateSet {
    candidates: Vec<Candidate>,
}

pub fn default_estimator_config() -> EstimatorConfig {
    EstimatorConfig {
        mode: Mode::Seeded,
        withhold: WithheldChannels::empty(),
        engine: EnginePreference::PortableOnly,
        fit: provisional_fit_weights(),
        thresholds: SolverThresholds {
            long_gap_seconds: 0.15,
            cadence_fraction_tolerance: 0.35,
            cadence_persistence_intervals: 3,
            nominal_interval_ticks: 4,
            car_proximity_uu: 350.0,
            ball_proximity_uu: 190.0,
        },
    }
}

pub fn solve_series(series: &ReplaySeries, config: &EstimatorConfig) -> SolveOutput {
    let masked = masked_series_for_solving(series, config);
    if config.mode == Mode::Unseeded {
        assert!(
            prior_streams_empty(&masked),
            "Mode::Unseeded must enter the solver with prior streams stripped"
        );
    }

    let first = solve_pass(&masked, config, &[], true);
    if first.retro_splits.is_empty() {
        first.output
    } else {
        solve_pass(&masked, config, &first.retro_splits, false).output
    }
}

pub fn masked_series_for_solving(series: &ReplaySeries, config: &EstimatorConfig) -> ReplaySeries {
    let mut masked = series.clone();
    for player in &mut masked.players {
        let len = player.frames.pos.len();
        if config.mode == Mode::Unseeded
            || config
                .withhold
                .intersects(WithheldChannels::JUMP_EDGES | WithheldChannels::COMPONENT_EVENTS)
        {
            player.component = empty_component_stream(len);
        } else if config.withhold.contains(WithheldChannels::COMPONENT_EVENTS) {
            player.component.events.clear();
        }
        if config.mode == Mode::Unseeded || config.withhold.contains(WithheldChannels::THROTTLE) {
            player.replicated.throttle_raw = vec![128; len];
        }
        if config.mode == Mode::Unseeded || config.withhold.contains(WithheldChannels::STEER) {
            player.replicated.steer_raw = vec![128; len];
        }
        if config.mode == Mode::Unseeded || config.withhold.contains(WithheldChannels::HANDBRAKE) {
            player.replicated.handbrake = vec![false; len];
        }
        if config.mode == Mode::Unseeded || config.withhold.contains(WithheldChannels::BOOST_ACTIVE)
        {
            player.replicated.boost_active_raw = vec![false; len];
            player.component.boost_raw = vec![0; len];
        }
        if config.mode == Mode::Unseeded || config.withhold.contains(WithheldChannels::BOOST_AMOUNT)
        {
            player.replicated.boost_amount_raw = vec![0; len];
        }
    }
    masked
}

fn solve_pass(
    series: &ReplaySeries,
    config: &EstimatorConfig,
    retro_splits: &[RetroactiveSplit],
    allow_retro_upgrades: bool,
) -> SolvePass {
    let segmentation = segment_replay_with_splits_and_confidences(
        series,
        retro_splits,
        CONFIDENT_SEGMENT_THRESHOLD,
        |_player_id, _segment| None,
    );
    let frame_times = frame_times(series);
    let player_index_by_id: HashMap<_, _> = series
        .players
        .iter()
        .enumerate()
        .map(|(idx, player)| (player.player_id.as_str(), idx))
        .collect();

    let mut solved_by_player: HashMap<String, PlayerSolved> = HashMap::new();
    let mut confidence_by_segment = HashMap::new();
    let mut splits = Vec::new();
    let mut warnings = vec!["rlinput_solver_path=single".to_string()];
    if config.engine == EnginePreference::PreferReference && !reference_engine_available() {
        warnings.push("reference_engine_unavailable_portable_used".to_string());
    }

    for segmented_player in &segmentation.players {
        let Some(&player_index) = player_index_by_id.get(segmented_player.player_id.as_str())
        else {
            continue;
        };
        let player = &series.players[player_index];
        let solved = solve_player(
            series,
            player_index,
            player,
            &segmented_player.segments,
            &frame_times,
            config,
            allow_retro_upgrades,
            &mut confidence_by_segment,
            &mut splits,
        );
        solved_by_player.insert(solved.player_id.clone(), solved);
    }

    let segmentation = segment_replay_with_splits_and_confidences(
        series,
        retro_splits,
        CONFIDENT_SEGMENT_THRESHOLD,
        |player_id, segment| {
            player_index_by_id
                .get(player_id)
                .and_then(|player_index| {
                    confidence_by_segment.get(&SegmentKey {
                        player_index: *player_index,
                        segment_id: segment.summary.id,
                        frame_span: segment.frame_span,
                    })
                })
                .copied()
        },
    );

    let mut timelines = Vec::with_capacity(segmentation.players.len());
    for segmented_player in &segmentation.players {
        let solved = solved_by_player
            .remove(&segmented_player.player_id)
            .unwrap_or_else(|| PlayerSolved {
                player_id: segmented_player.player_id.clone(),
                samples: Vec::new(),
                events: Vec::new(),
            });
        timelines.push(InputTimeline {
            player_id: segmented_player.player_id.clone(),
            samples: solved.samples,
            events: solved.events,
            segments: segmented_player
                .segments
                .iter()
                .map(|segment| segment.summary.clone())
                .collect(),
        });
    }

    let mut diagnostics = segmentation_diagnostics(&segmentation.players);
    diagnostics.warnings.extend(warnings);

    SolvePass {
        output: SolveOutput {
            timelines,
            coverage: segmentation.coverage,
            diagnostics,
        },
        retro_splits: dedupe_splits(splits),
    }
}

#[allow(clippy::too_many_arguments)]
fn solve_player(
    series: &ReplaySeries,
    player_index: usize,
    player: &PlayerSeries,
    segments: &[Segment],
    frame_times: &[f64],
    config: &EstimatorConfig,
    allow_retro_upgrades: bool,
    confidence_by_segment: &mut HashMap<SegmentKey, f32>,
    splits: &mut Vec<RetroactiveSplit>,
) -> PlayerSolved {
    let hints = SeededHints::new(&player.component);
    let mut samples = Vec::new();
    let mut events = Vec::new();
    let mut reference = ReferenceScorer::new();

    for segment in segments {
        let mut tracker = tracker_for_segment(player, segment, series.tick_rate);
        let mut branching = BranchingTracker::new(tracker.clone());
        let mut segment_confidence = 1.0f32;
        let mut prev_frame = segment.frame_span.0.saturating_sub(1);
        let segment_base_time = frame_times
            .get(prev_frame as usize)
            .copied()
            .unwrap_or_default();

        for interval in &segment.lattice.intervals {
            let start_frame = prev_frame;
            let end_frame = interval.frame_index;
            prev_frame = end_frame;
            if frame_out_of_bounds(player, start_frame) || frame_out_of_bounds(player, end_frame) {
                continue;
            }

            let mut interval_tracker = if config.mode == Mode::Unseeded {
                branching.best_tracker().clone()
            } else {
                tracker.clone()
            };
            let solved = solve_interval(
                series,
                player_index,
                player,
                &mut interval_tracker,
                interval,
                (start_frame, end_frame),
                segment.kind,
                segment_base_time,
                &hints,
                config,
                &mut reference,
                allow_retro_upgrades,
            );
            segment_confidence = segment_confidence.min(solved.confidence);
            samples.push(solved.sample);
            events.extend(solved.events);
            if let Some(split) = solved.retro_split {
                splits.push(split);
            }
            if config.mode == Mode::Unseeded {
                apply_branch_options(
                    &mut branching,
                    &solved.branch_options,
                    interval.tick_range.0,
                );
                tracker = branching.best_tracker().clone();
            } else {
                tracker = interval_tracker;
            }
        }

        if segment.lattice.intervals.is_empty() {
            segment_confidence = 0.0;
        }
        confidence_by_segment.insert(
            SegmentKey {
                player_index,
                segment_id: segment.summary.id,
                frame_span: segment.frame_span,
            },
            segment_confidence,
        );
    }

    PlayerSolved {
        player_id: player.player_id.clone(),
        samples,
        events,
    }
}

#[allow(clippy::too_many_arguments)]
fn solve_interval(
    series: &ReplaySeries,
    player_index: usize,
    player: &PlayerSeries,
    tracker: &mut CarTracker,
    interval: &LatticeInterval,
    frames: (u32, u32),
    segment_kind: SegmentKind,
    segment_base_time: f64,
    hints: &SeededHints,
    config: &EstimatorConfig,
    reference: &mut ReferenceScorer,
    allow_retro_upgrades: bool,
) -> IntervalSolve {
    let (start_frame, end_frame) = frames;
    let ticks = interval_ticks(interval);
    let state_k = car_state(player, start_frame, tracker);
    let observed_end = car_state(player, end_frame, tracker);
    let base_controls = solve_controls(player, start_frame, end_frame, interval, tracker, config);
    let candidates = generate_candidates(
        &state_k,
        &observed_end,
        tracker,
        interval,
        base_controls,
        hints.edges_for_frame(end_frame),
        config,
        segment_kind,
    );
    let mut scored = score_candidates(
        &state_k,
        &observed_end,
        ticks,
        &candidates.candidates,
        config,
        reference,
    );
    if scored.is_empty() {
        scored.push(score_one(
            &mut PortableEngine::new(),
            &state_k,
            &observed_end,
            ticks,
            Candidate::null(vec![Controls::default(); ticks as usize], interval.flags),
            &config.fit,
        ));
    }
    prefer_event_when_null_is_rejected(&mut scored, &config.fit);
    prefer_long_gap_stall_z_damp(&mut scored, interval, &observed_end);
    let branch_options = scored
        .iter()
        .enumerate()
        .take(BranchingTracker::DEFAULT_BEAM_WIDTH)
        .map(|(rank, item)| BranchOption {
            candidate: item.candidate.clone(),
            score: rank as f64,
        })
        .collect();
    let best = scored.remove(0);
    let confidence = best.confidence;
    apply_candidate_to_tracker(tracker, &best.candidate, interval.tick_range.0);

    let sample = sample_from_candidate(
        player,
        start_frame,
        end_frame,
        interval,
        segment_base_time,
        &best,
        config,
    );
    let events = events_from_candidate(
        &best.candidate,
        interval,
        segment_base_time,
        end_frame,
        confidence,
        best.flags,
    );
    let velocity_residual = norm(diff(best.sim_end.vel, observed_end.vel));
    let retro_split = (allow_retro_upgrades
        && config.engine == EnginePreference::PreferReference
        && segment_kind == SegmentKind::Air
        && confidence <= 0.3
        && velocity_residual > RETRO_VELOCITY_RESIDUAL_UU_PER_S
        && endpoint_car_proximity(series, player_index, start_frame, end_frame))
    .then(|| split_segment_at(player.player_id.clone(), end_frame));

    IntervalSolve {
        sample,
        events,
        confidence,
        retro_split,
        branch_options,
    }
}

#[allow(clippy::too_many_arguments)]
fn generate_candidates(
    state_k: &CarPhysState,
    observed_end: &CarPhysState,
    tracker: &CarTracker,
    interval: &LatticeInterval,
    base_controls: Vec<Controls>,
    seeded_edges: &[ReconstructedEdge],
    config: &EstimatorConfig,
    segment_kind: SegmentKind,
) -> CandidateSet {
    let ticks = interval_ticks(interval);
    let null = Candidate::null(base_controls.clone(), interval.flags);
    let null_energy = score_null(state_k, observed_end, ticks, &null, &config.fit);
    if null_energy <= f64::from(config.fit.reject_threshold)
        && seeded_edges.is_empty()
        && !interval.flags.contains(AmbiguityFlags::LONG_GAP)
    {
        return CandidateSet {
            candidates: vec![null],
        };
    }

    let mut candidates = vec![null];
    let seeded = seeded_candidate_events(seeded_edges);
    let event_kinds = if seeded.is_empty() {
        let mut events = kinematic_candidate_events(state_k, observed_end, tracker, segment_kind);
        if interval.flags.contains(AmbiguityFlags::LONG_GAP) && second_available(tracker) {
            push_unique_event(&mut events, CandidateEvent::Stall);
        }
        events
    } else {
        seeded
    };

    for event in event_kinds {
        for tick_offset in 0..ticks {
            if let Some(candidate) =
                single_event_candidate(event, tick_offset, base_controls.clone(), interval.flags)
            {
                if candidate_legal(tracker, &candidate, interval.tick_range.0) {
                    candidates.push(candidate);
                }
            }
        }
    }

    if interval.flags.contains(AmbiguityFlags::LONG_GAP) {
        add_long_gap_composites(
            &mut candidates,
            tracker,
            interval,
            base_controls,
            dodge_dir_from_signature(state_k, observed_end),
        );
    }

    candidates.truncate(HYPOTHESIS_CAP);
    CandidateSet { candidates }
}

fn single_event_candidate(
    event: CandidateEvent,
    tick_offset: u32,
    mut controls: Vec<Controls>,
    flags: AmbiguityFlags,
) -> Option<Candidate> {
    if controls.is_empty() {
        return None;
    }
    match event {
        CandidateEvent::JumpPress => {
            for control in controls.iter_mut().skip(tick_offset as usize) {
                control.jump = true;
            }
        }
        CandidateEvent::JumpRelease => {
            for control in controls.iter_mut().skip(tick_offset as usize) {
                control.jump = false;
            }
        }
        CandidateEvent::DoubleJump | CandidateEvent::Dodge { .. } | CandidateEvent::Stall => {}
    }
    Some(Candidate {
        actions: vec![CandidateAction { tick_offset, event }],
        controls,
        flags,
        confidence_cap: 1.0,
    })
}

fn add_long_gap_composites(
    candidates: &mut Vec<Candidate>,
    tracker: &CarTracker,
    interval: &LatticeInterval,
    base_controls: Vec<Controls>,
    dodge_dir: [f32; 2],
) {
    if !matches!(tracker.contact, ContactState::Grounded { .. }) {
        return;
    }
    let ticks = interval_ticks(interval);
    for press in 0..ticks {
        let min_release = (press + 3).min(ticks);
        for release in min_release..ticks {
            for second in release.saturating_add(1)..ticks {
                for event in [
                    CandidateEvent::Dodge { dir: dodge_dir },
                    CandidateEvent::DoubleJump,
                ] {
                    if candidates.len() >= HYPOTHESIS_CAP {
                        return;
                    }
                    let mut controls = base_controls.clone();
                    for control in controls
                        .iter_mut()
                        .take(release as usize)
                        .skip(press as usize)
                    {
                        control.jump = true;
                    }
                    let candidate = Candidate {
                        actions: vec![
                            CandidateAction {
                                tick_offset: press,
                                event: CandidateEvent::JumpPress,
                            },
                            CandidateAction {
                                tick_offset: release,
                                event: CandidateEvent::JumpRelease,
                            },
                            CandidateAction {
                                tick_offset: second,
                                event,
                            },
                        ],
                        controls,
                        flags: interval.flags | AmbiguityFlags::LONG_GAP,
                        confidence_cap: LONG_GAP_CONFIDENCE_CAP,
                    };
                    if candidate_legal(tracker, &candidate, interval.tick_range.0) {
                        candidates.push(candidate);
                    }
                }
            }
        }
    }
}

fn seeded_candidate_events(edges: &[ReconstructedEdge]) -> Vec<CandidateEvent> {
    let mut out = Vec::new();
    for edge in edges {
        match edge.component {
            ComponentKind::Jump => {
                let event = if edge
                    .counter_delta
                    .as_ref()
                    .is_some_and(|delta| delta.current % 2 == 0)
                {
                    CandidateEvent::JumpRelease
                } else {
                    CandidateEvent::JumpPress
                };
                push_unique_event(&mut out, event);
            }
            ComponentKind::DoubleJumpImpulse => {
                push_unique_event(&mut out, CandidateEvent::DoubleJump);
            }
            ComponentKind::DodgeTorque => match edge.vector.map(classify_dodge_torque_vector) {
                Some(SecondActionClass::Dodge { dir, .. }) => {
                    push_unique_event(&mut out, CandidateEvent::Dodge { dir });
                }
                Some(SecondActionClass::Stall) => {
                    push_unique_event(&mut out, CandidateEvent::Stall)
                }
                Some(SecondActionClass::DoubleJump) => {
                    push_unique_event(&mut out, CandidateEvent::DoubleJump);
                }
                None => push_unique_event(&mut out, CandidateEvent::Dodge { dir: [1.0, 0.0] }),
            },
            ComponentKind::Boost => {}
        }
    }
    out
}

fn kinematic_candidate_events(
    state_k: &CarPhysState,
    observed_end: &CarPhysState,
    tracker: &CarTracker,
    segment_kind: SegmentKind,
) -> Vec<CandidateEvent> {
    let mut events = Vec::new();
    let vel_residual = diff(observed_end.vel, state_k.vel);
    let planar_residual =
        (vel_residual[0] * vel_residual[0] + vel_residual[1] * vel_residual[1]).sqrt();
    let vertical_residual = vel_residual[2];
    let ang_residual = norm(diff(observed_end.ang_vel, state_k.ang_vel));

    if segment_kind == SegmentKind::Air
        && matches!(tracker.contact, ContactState::Grounded { .. })
        && vertical_residual > 200.0
    {
        push_unique_event(&mut events, CandidateEvent::JumpPress);
    }
    if matches!(tracker.jump, JumpState::Holding { .. }) {
        push_unique_event(&mut events, CandidateEvent::JumpRelease);
    }
    if second_available(tracker) {
        if vertical_residual > 120.0 && ang_residual < 0.3 && planar_residual < 250.0 {
            push_unique_event(&mut events, CandidateEvent::DoubleJump);
        }
        if planar_residual > 150.0 || ang_residual > 0.5 {
            push_unique_event(
                &mut events,
                CandidateEvent::Dodge {
                    dir: dodge_dir_from_signature(state_k, observed_end),
                },
            );
        }
        if vertical_residual < -30.0 {
            push_unique_event(&mut events, CandidateEvent::Stall);
        }
    }
    events
}

fn push_unique_event(events: &mut Vec<CandidateEvent>, event: CandidateEvent) {
    if !events.contains(&event) {
        events.push(event);
    }
}

fn candidate_legal(tracker: &CarTracker, candidate: &Candidate, base_tick: u64) -> bool {
    let mut branch = tracker.clone();
    apply_candidate_to_tracker(&mut branch, candidate, base_tick)
}

fn apply_branch_options(branches: &mut BranchingTracker, options: &[BranchOption], base_tick: u64) {
    if options.is_empty() {
        branches.advance_unresolved();
        return;
    }
    branches.expand(options.iter().map(|option| option.score), |tracker, idx| {
        let mut branch = tracker.clone();
        apply_candidate_to_tracker(&mut branch, &options[idx].candidate, base_tick)
            .then_some(branch)
    });
}

fn apply_candidate_to_tracker(
    tracker: &mut CarTracker,
    candidate: &Candidate,
    base_tick: u64,
) -> bool {
    let mut actions = candidate.actions.clone();
    actions.sort_by_key(|action| action.tick_offset);
    for action in actions {
        let tick = base_tick + u64::from(action.tick_offset);
        let result = match action.event {
            CandidateEvent::JumpPress => tracker.first_jump_press(tick).map(|_| ()),
            CandidateEvent::JumpRelease => tracker.jump_release(tick).map(|_| ()),
            CandidateEvent::DoubleJump => tracker
                .second_action_from_controls(tick, 0.0, 0.0, 0.0)
                .map(|_| ()),
            CandidateEvent::Dodge { dir } => tracker
                .second_action_from_controls(tick, -dir[0], dir[1], 0.0)
                .map(|_| ()),
            CandidateEvent::Stall => tracker
                .second_action_from_controls(tick, 0.0, 0.3, -0.3)
                .map(|_| ()),
        };
        if result.is_err() {
            return false;
        }
    }
    tracker.advance_to(base_tick + u64::from(candidate.controls.len() as u32));
    true
}

fn score_candidates(
    state_k: &CarPhysState,
    observed_end: &CarPhysState,
    ticks: u32,
    candidates: &[Candidate],
    config: &EstimatorConfig,
    reference: &mut ReferenceScorer,
) -> Vec<ScoredCandidate> {
    let mut portable = PortableEngine::new();
    let mut scored: Vec<_> = candidates
        .iter()
        .cloned()
        .map(|candidate| {
            score_one(
                &mut portable,
                state_k,
                observed_end,
                ticks,
                candidate,
                &config.fit,
            )
        })
        .collect();
    scored = rank_scored(scored, &config.fit);

    if config.engine == EnginePreference::PreferReference
        && scored.iter().any(|item| !item.candidate.is_null())
    {
        scored = reference.rescore(state_k, observed_end, ticks, scored, &config.fit);
    }
    scored
}

fn score_one<E: AirEngine>(
    engine: &mut E,
    state_k: &CarPhysState,
    observed_end: &CarPhysState,
    ticks: u32,
    candidate: Candidate,
    weights: &FitWeights,
) -> ScoredCandidate {
    let sim_end = engine.rollout(state_k, &candidate.to_tick_plan(), ticks);
    ScoredCandidate {
        energy: score(&sim_end, observed_end, weights),
        sim_end,
        candidate,
        probability: 0.0,
        confidence: 0.0,
        flags: AmbiguityFlags::empty(),
    }
}

fn rank_scored(mut scored: Vec<ScoredCandidate>, weights: &FitWeights) -> Vec<ScoredCandidate> {
    if scored.is_empty() {
        return scored;
    }
    let best = scored
        .iter()
        .map(|item| item.energy)
        .fold(f64::INFINITY, f64::min);
    let normalizer: f64 = scored
        .iter()
        .map(|item| (-(item.energy - best)).exp())
        .sum();
    let mut best_probability = 0.0;
    for item in &mut scored {
        item.probability = (-(item.energy - best)).exp() / normalizer;
        best_probability = f64::max(best_probability, item.probability);
        item.confidence = (item.probability as f32).min(item.candidate.confidence_cap);
        item.flags = item.candidate.flags;
    }
    if best > f64::from(weights.reject_threshold) {
        for item in &mut scored {
            item.confidence = item.confidence.min(0.3);
        }
    }
    if best_probability < f64::from(weights.low_margin_threshold) {
        for item in &mut scored {
            item.flags |= AmbiguityFlags::LOW_MARGIN;
        }
    }
    scored.sort_by(|a, b| a.energy.total_cmp(&b.energy));
    scored
}

fn prefer_event_when_null_is_rejected(scored: &mut [ScoredCandidate], weights: &FitWeights) {
    if scored.first().is_some_and(|item| {
        item.candidate.is_null() && item.energy > f64::from(weights.reject_threshold)
    }) {
        if let Some(event_index) = scored.iter().position(|item| !item.candidate.is_null()) {
            scored.swap(0, event_index);
            scored[0].confidence = scored[0].confidence.min(0.3);
            scored[0].flags |= AmbiguityFlags::LOW_MARGIN;
        }
    }
}

fn prefer_long_gap_stall_z_damp(
    scored: &mut [ScoredCandidate],
    interval: &LatticeInterval,
    observed_end: &CarPhysState,
) {
    let Some(null) = scored.first() else {
        return;
    };
    if !interval.flags.contains(AmbiguityFlags::LONG_GAP) || !null.candidate.is_null() {
        return;
    }
    if observed_end.vel[2] - null.sim_end.vel[2] > -20.0 {
        return;
    }
    if let Some(stall_index) = scored.iter().position(|item| {
        item.candidate
            .actions
            .iter()
            .any(|action| action.event == CandidateEvent::Stall)
    }) {
        scored.swap(0, stall_index);
        scored[0].confidence = scored[0].confidence.min(LONG_GAP_CONFIDENCE_CAP);
        scored[0].flags |= AmbiguityFlags::LONG_GAP | AmbiguityFlags::LOW_MARGIN;
    }
}

#[cfg(feature = "sim")]
struct ReferenceScorer {
    engine: crate::engine::rocketsim::RocketSimEngine,
}

#[cfg(feature = "sim")]
impl ReferenceScorer {
    fn new() -> Self {
        Self {
            engine: crate::engine::rocketsim::RocketSimEngine::new(),
        }
    }

    fn rescore(
        &mut self,
        state_k: &CarPhysState,
        observed_end: &CarPhysState,
        ticks: u32,
        scored: Vec<ScoredCandidate>,
        weights: &FitWeights,
    ) -> Vec<ScoredCandidate> {
        let rescored: Vec<_> = scored
            .into_iter()
            .take(REFERENCE_SURVIVORS)
            .map(|item| {
                score_one(
                    &mut self.engine,
                    state_k,
                    observed_end,
                    ticks,
                    item.candidate,
                    weights,
                )
            })
            .collect();
        rank_scored(rescored, weights)
    }
}

#[cfg(not(feature = "sim"))]
struct ReferenceScorer;

#[cfg(not(feature = "sim"))]
impl ReferenceScorer {
    fn new() -> Self {
        Self
    }

    fn rescore(
        &mut self,
        _state_k: &CarPhysState,
        _observed_end: &CarPhysState,
        _ticks: u32,
        scored: Vec<ScoredCandidate>,
        _weights: &FitWeights,
    ) -> Vec<ScoredCandidate> {
        scored
    }
}

fn score_null(
    state_k: &CarPhysState,
    observed_end: &CarPhysState,
    ticks: u32,
    null: &Candidate,
    weights: &FitWeights,
) -> f64 {
    let mut engine = PortableEngine::new();
    let sim_end = engine.rollout(state_k, &null.to_tick_plan(), ticks);
    score(&sim_end, observed_end, weights)
}

fn solve_controls(
    player: &PlayerSeries,
    start_frame: u32,
    end_frame: u32,
    interval: &LatticeInterval,
    tracker: &CarTracker,
    config: &EstimatorConfig,
) -> Vec<Controls> {
    let ticks = interval_ticks(interval) as usize;
    let start = frame_state(player, start_frame);
    let end = frame_state(player, end_frame);
    let dt = (interval.time_range.1 - interval.time_range.0).max(f64::from(crate::engine::AIR_DT));
    let delta_v = diff(end.vel, start.vel);
    let rot = start.rot;
    let forward = forward(rot);
    let grounded = player
        .frames
        .on_ground
        .get(start_frame as usize)
        .copied()
        .unwrap_or(false);

    let throttle = if grounded {
        solve_throttle(ThrottleObservation {
            forward_speed: dot(start.vel, forward),
            longitudinal_accel: dot(delta_v, forward) / dt as f32,
            raw_throttle: player
                .replicated
                .throttle_raw
                .get(start_frame as usize)
                .copied(),
        })
        .value
    } else {
        replicated_axis(
            player
                .replicated
                .throttle_raw
                .get(start_frame as usize)
                .copied(),
            config.mode == Mode::Seeded && !config.withhold.contains(WithheldChannels::THROTTLE),
        )
        .unwrap_or(0.0)
    };

    let steer = if grounded {
        solve_steer(SteerObservation {
            speed_2d: norm2([start.vel[0], start.vel[1]]),
            yaw_rate_z: start.ang_vel[2],
        })
        .value
    } else {
        0.0
    };
    let handbrake = grounded
        && solve_handbrake(HandbrakeObservation {
            velocity_2d: [start.vel[0], start.vel[1]],
            forward_2d: [forward[0], forward[1]],
            yaw_rate_z: start.ang_vel[2],
            steer,
        })
        .value;

    let flip = match &tracker.second {
        SecondAction::UsedDodge(phase) => Some(phase),
        _ => None,
    };
    let axis_start = AxisObservation {
        rot,
        ang_vel: start.ang_vel,
    };
    let axis_end = AxisObservation {
        rot: end.rot,
        ang_vel: end.ang_vel,
    };
    let pitch = if grounded {
        0.0
    } else {
        solve_axis_from_observations(
            AerialAxis::Pitch,
            axis_start,
            axis_end,
            ticks as u32,
            interval.tick_range,
            flip,
        )
        .value
    };
    let yaw = if grounded {
        0.0
    } else {
        solve_axis_from_observations(
            AerialAxis::Yaw,
            axis_start,
            axis_end,
            ticks as u32,
            interval.tick_range,
            flip,
        )
        .value
    };
    let roll = if grounded {
        0.0
    } else {
        solve_axis_from_observations(
            AerialAxis::Roll,
            axis_start,
            axis_end,
            ticks as u32,
            interval.tick_range,
            flip,
        )
        .value
    };
    let boost = solve_boost(BoostObservation {
        tick: interval.tick_range.0,
        dt: dt as f32,
        delta_v,
        nose: forward,
        grounded,
        forward_speed: dot(start.vel, forward),
        longitudinal_accel: dot(delta_v, forward) / dt as f32,
    })
    .value;
    let jump = matches!(tracker.jump, JumpState::Holding { .. });

    vec![
        Controls {
            throttle,
            steer,
            pitch,
            yaw,
            roll,
            jump,
            boost,
            handbrake,
        };
        ticks
    ]
}

fn sample_from_candidate(
    player: &PlayerSeries,
    start_frame: u32,
    end_frame: u32,
    interval: &LatticeInterval,
    segment_base_time: f64,
    best: &ScoredCandidate,
    config: &EstimatorConfig,
) -> InputSample {
    let controls = best.candidate.controls.first().copied().unwrap_or_default();
    let confidence = best.confidence;
    let flags = best.flags;
    InputSample {
        frame_index: end_frame,
        tick_range: interval.tick_range,
        time_range: (
            segment_base_time + interval.time_range.0,
            segment_base_time + interval.time_range.1,
        ),
        throttle: f32_channel(
            replicated_axis(
                player
                    .replicated
                    .throttle_raw
                    .get(start_frame as usize)
                    .copied(),
                config.mode == Mode::Seeded
                    && !config.withhold.contains(WithheldChannels::THROTTLE),
            )
            .unwrap_or(controls.throttle),
            source_for_replicated(config, WithheldChannels::THROTTLE),
            confidence,
            flags,
        ),
        steer: f32_channel(
            replicated_axis(
                player
                    .replicated
                    .steer_raw
                    .get(start_frame as usize)
                    .copied(),
                config.mode == Mode::Seeded && !config.withhold.contains(WithheldChannels::STEER),
            )
            .unwrap_or(controls.steer),
            source_for_replicated(config, WithheldChannels::STEER),
            confidence,
            flags,
        ),
        pitch: f32_channel(controls.pitch, Source::Solved, confidence, flags),
        yaw: f32_channel(controls.yaw, Source::Solved, confidence, flags),
        roll: f32_channel(controls.roll, Source::Solved, confidence, flags),
        jump: bool_channel(
            best.candidate.controls.iter().any(|control| control.jump),
            Source::Solved,
            confidence,
            flags,
        ),
        boost: bool_channel(
            player
                .replicated
                .boost_active_raw
                .get(start_frame as usize)
                .copied()
                .filter(|_| {
                    config.mode == Mode::Seeded
                        && !config.withhold.contains(WithheldChannels::BOOST_ACTIVE)
                })
                .unwrap_or(controls.boost),
            source_for_replicated(config, WithheldChannels::BOOST_ACTIVE),
            confidence,
            flags,
        ),
        handbrake: bool_channel(
            player
                .replicated
                .handbrake
                .get(start_frame as usize)
                .copied()
                .filter(|_| {
                    config.mode == Mode::Seeded
                        && !config.withhold.contains(WithheldChannels::HANDBRAKE)
                })
                .unwrap_or(controls.handbrake),
            source_for_replicated(config, WithheldChannels::HANDBRAKE),
            confidence,
            flags,
        ),
    }
}

fn events_from_candidate(
    candidate: &Candidate,
    interval: &LatticeInterval,
    segment_base_time: f64,
    frame_index: u32,
    confidence: f32,
    flags: AmbiguityFlags,
) -> Vec<SolvedEvent> {
    candidate
        .actions
        .iter()
        .map(|action| {
            let tick = interval.tick_range.0 + u64::from(action.tick_offset);
            SolvedEvent {
                kind: event_kind(action.event),
                tick,
                t: segment_base_time
                    + interval.time_range.0
                    + f64::from(action.tick_offset) / 120.0,
                frame_index,
                confidence,
                flags,
            }
        })
        .collect()
}

fn event_kind(event: CandidateEvent) -> SolvedEventKind {
    match event {
        CandidateEvent::JumpPress => SolvedEventKind::JumpPress,
        CandidateEvent::JumpRelease => SolvedEventKind::JumpRelease,
        CandidateEvent::DoubleJump => SolvedEventKind::DoubleJump,
        CandidateEvent::Dodge { dir } => SolvedEventKind::Dodge {
            dir,
            cancel: CancelSummary {
                onset_tick: None,
                peak_pitch: 0.0,
                full_cancel: false,
            },
        },
        CandidateEvent::Stall => SolvedEventKind::Stall,
    }
}

fn tracker_for_segment(player: &PlayerSeries, segment: &Segment, tick_rate: f64) -> CarTracker {
    let start_frame = segment.frame_span.0.saturating_sub(1) as usize;
    let mut tracker =
        CarTracker::new_grounded_with_tick_rate(segment.summary.tick_span.0, tick_rate);
    let airborne = player
        .frames
        .on_ground
        .get(start_frame)
        .is_some_and(|on_ground| !*on_ground);
    if airborne {
        tracker.set_airborne(segment.summary.tick_span.0);
        // Air stream edges have no trustworthy prior first-jump edge. Keep second action
        // legal and let fit adjudicate; liftoff intervals still start grounded.
        tracker.jump = JumpState::Released {
            press_tick: segment.summary.tick_span.0,
            release_tick: segment.summary.tick_span.0,
            jump_end_tick: segment.summary.tick_span.0,
        };
        tracker.second = SecondAction::Available {
            deadline_tick: segment.summary.tick_span.0 + (tick_rate * 1.25).round() as u64,
        };
    }
    tracker
}

fn car_state(player: &PlayerSeries, frame: u32, tracker: &CarTracker) -> CarPhysState {
    let base = frame_state(player, frame);
    let airborne = player
        .frames
        .on_ground
        .get(frame as usize)
        .is_some_and(|on_ground| !*on_ground);
    let boost = player
        .replicated
        .boost_amount_raw
        .get(frame as usize)
        .map(|raw| f32::from(*raw) * 100.0 / 255.0)
        .unwrap_or(0.0);
    let is_boosting = player
        .replicated
        .boost_active_raw
        .get(frame as usize)
        .copied()
        .unwrap_or(false);
    let flip = match &tracker.second {
        SecondAction::UsedDodge(phase) => Some(phase),
        _ => None,
    };

    CarPhysState {
        pos: base.pos,
        vel: base.vel,
        rot: base.rot,
        ang_vel: base.ang_vel,
        boost,
        is_boosting,
        boosting_time: if is_boosting {
            crate::engine::AIR_DT
        } else {
            0.0
        },
        has_jumped: airborne || !matches!(tracker.jump, JumpState::Idle),
        has_double_jumped: matches!(tracker.second, SecondAction::UsedDoubleJump { .. }),
        has_flipped: flip.is_some(),
        is_jumping: matches!(tracker.jump, JumpState::Holding { .. }),
        is_flipping: flip.is_some_and(|phase| phase.start_tick <= 120),
        jump_time: match tracker.jump {
            JumpState::Holding { press_tick } => ticks_since(frame, press_tick),
            JumpState::Released {
                press_tick,
                release_tick,
                ..
            } => ticks_since(frame, release_tick.max(press_tick)),
            JumpState::Idle => 0.0,
        },
        flip_time: flip
            .map(|phase| ticks_since(frame, phase.start_tick))
            .unwrap_or(0.0),
        air_time_since_jump: if airborne { 0.1 } else { 0.0 },
        flip_rel_torque: flip
            .map(|phase| [phase.rel_torque[0], phase.rel_torque[1], 0.0])
            .unwrap_or([0.0, 0.0, 0.0]),
    }
}

#[derive(Clone, Copy)]
struct FrameState {
    pos: [f32; 3],
    vel: [f32; 3],
    rot: RotationMatrix,
    ang_vel: [f32; 3],
}

fn frame_state(player: &PlayerSeries, frame: u32) -> FrameState {
    let idx = frame as usize;
    FrameState {
        pos: player.frames.pos.get(idx).copied().unwrap_or([0.0; 3]),
        vel: player.frames.vel.get(idx).copied().unwrap_or([0.0; 3]),
        rot: player
            .frames
            .quat_xyzw
            .get(idx)
            .copied()
            .map(replay_quat_xyzw_to_rot_mat)
            .unwrap_or_else(identity_rot_mat),
        ang_vel: player.frames.ang_vel.get(idx).copied().unwrap_or([0.0; 3]),
    }
}

impl SeededHints {
    fn new(stream: &ComponentStream) -> Self {
        let mut edges: HashMap<u32, Vec<ReconstructedEdge>> = HashMap::new();
        for edge in crate::tracker::reconstruct_seeded_edges(stream) {
            edges.entry(edge.frame_index).or_default().push(edge);
        }
        Self { edges }
    }

    fn edges_for_frame(&self, frame: u32) -> &[ReconstructedEdge] {
        self.edges.get(&frame).map(Vec::as_slice).unwrap_or(&[])
    }
}

fn segmentation_diagnostics(players: &[crate::segment::PlayerSegmentation]) -> SolveDiagnostics {
    let mut nonstandard_cadence = false;
    let mut lattice = Vec::new();
    for player in players {
        for segment in &player.segments {
            let diagnostics = &segment.lattice.diagnostics;
            if diagnostics.nonstandard_cadence {
                nonstandard_cadence = true;
                lattice.push(LatticeDiagnostic {
                    kind: "nonstandard_cadence".to_string(),
                    first_frame_index: diagnostics.first_nonstandard_frame.unwrap_or(0),
                    count: 1,
                });
            }
        }
    }
    SolveDiagnostics {
        nonstandard_cadence,
        lattice,
        warnings: Vec::new(),
    }
}

fn endpoint_car_proximity(
    series: &ReplaySeries,
    player_index: usize,
    start_frame: u32,
    end_frame: u32,
) -> bool {
    let Some(player) = series.players.get(player_index) else {
        return false;
    };
    [start_frame, end_frame].into_iter().any(|frame| {
        let Some(pos) = player.frames.pos.get(frame as usize).copied() else {
            return false;
        };
        series
            .players
            .iter()
            .enumerate()
            .any(|(other_index, other)| {
                other_index != player_index
                    && other
                        .frames
                        .pos
                        .get(frame as usize)
                        .is_some_and(|other_pos| dist(pos, *other_pos) < RETRO_CAR_PROXIMITY_UU)
            })
    })
}

fn dedupe_splits(splits: Vec<RetroactiveSplit>) -> Vec<RetroactiveSplit> {
    let mut seen = HashSet::new();
    splits
        .into_iter()
        .filter(|split| seen.insert((split.player_id.clone(), split.interval_terminating_frame)))
        .collect()
}

fn prior_streams_empty(series: &ReplaySeries) -> bool {
    series.players.iter().all(|player| {
        player.component.events.is_empty()
            && all_zero(&player.component.jump_raw)
            && all_zero(&player.component.dodge_raw)
            && all_zero(&player.component.double_jump_raw)
            && all_zero(&player.component.boost_raw)
    })
}

fn empty_component_stream(len: usize) -> ComponentStream {
    ComponentStream {
        jump_raw: vec![0; len],
        dodge_raw: vec![0; len],
        double_jump_raw: vec![0; len],
        boost_raw: vec![0; len],
        events: Vec::new(),
    }
}

fn source_for_replicated(config: &EstimatorConfig, channel: WithheldChannels) -> Source {
    if config.mode == Mode::Seeded && !config.withhold.contains(channel) {
        Source::Replicated
    } else {
        Source::Solved
    }
}

fn f32_channel(value: f32, source: Source, confidence: f32, flags: AmbiguityFlags) -> Channel<f32> {
    Channel {
        value,
        source,
        confidence,
        flags,
    }
}

fn bool_channel(
    value: bool,
    source: Source,
    confidence: f32,
    flags: AmbiguityFlags,
) -> Channel<bool> {
    Channel {
        value,
        source,
        confidence,
        flags,
    }
}

fn replicated_axis(raw: Option<u8>, available: bool) -> Option<f32> {
    available.then(|| (f32::from(raw.unwrap_or(128)) - 128.0) / 127.0)
}

fn interval_ticks(interval: &LatticeInterval) -> u32 {
    interval
        .tick_range
        .1
        .saturating_sub(interval.tick_range.0)
        .clamp(1, u64::from(u32::MAX)) as u32
}

fn second_available(tracker: &CarTracker) -> bool {
    matches!(tracker.second, SecondAction::Available { .. })
}

fn dodge_dir_from_signature(state_k: &CarPhysState, observed_end: &CarPhysState) -> [f32; 2] {
    let residual = diff(observed_end.vel, state_k.vel);
    let f = forward(state_k.rot);
    let r = right(state_k.rot);
    let dir = [dot(residual, f), dot(residual, r)];
    normalize2_or(dir, [1.0, 0.0])
}

fn frame_times(series: &ReplaySeries) -> Vec<f64> {
    let frame_count = series
        .players
        .iter()
        .map(|player| player.frames.pos.len())
        .max()
        .unwrap_or(series.deltas.len());
    let mut out = vec![0.0; frame_count];
    for frame in 1..frame_count {
        out[frame] = out[frame - 1] + f64::from(delta_for(series, frame));
    }
    out
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

fn frame_out_of_bounds(player: &PlayerSeries, frame: u32) -> bool {
    frame as usize >= player.frames.pos.len()
}

fn ticks_since(frame: u32, tick: u64) -> f32 {
    ((u64::from(frame) * 4).saturating_sub(tick) as f32) / 120.0
}

fn reference_engine_available() -> bool {
    cfg!(feature = "sim")
}

fn all_zero(values: &[u8]) -> bool {
    values.iter().all(|value| *value == 0)
}

fn forward(rot: RotationMatrix) -> [f32; 3] {
    [rot[0][0], rot[1][0], rot[2][0]]
}

fn right(rot: RotationMatrix) -> [f32; 3] {
    [rot[0][1], rot[1][1], rot[2][1]]
}

fn dot(a: [f32; 3], b: [f32; 3]) -> f32 {
    a[0] * b[0] + a[1] * b[1] + a[2] * b[2]
}

fn diff(a: [f32; 3], b: [f32; 3]) -> [f32; 3] {
    [a[0] - b[0], a[1] - b[1], a[2] - b[2]]
}

fn norm(v: [f32; 3]) -> f32 {
    dot(v, v).sqrt()
}

fn dist(a: [f32; 3], b: [f32; 3]) -> f32 {
    norm(diff(a, b))
}

fn norm2(v: [f32; 2]) -> f32 {
    (v[0] * v[0] + v[1] * v[1]).sqrt()
}

fn normalize2_or(v: [f32; 2], fallback: [f32; 2]) -> [f32; 2] {
    let n = norm2(v);
    if n <= f32::EPSILON {
        fallback
    } else {
        [v[0] / n, v[1] / n]
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::{
        convert::identity_rot_mat,
        engine::{TickEvent, TickEventKind},
        model::{BallSeries, Kinematics, ReplicatedChannels},
    };

    #[test]
    fn unseeded_masks_priors_before_single_solver_path() {
        let mut series = quiet_series(3);
        series.players[0].component.jump_raw = vec![0, 1, 2];
        let config = EstimatorConfig {
            mode: Mode::Unseeded,
            ..default_estimator_config()
        };
        let masked = masked_series_for_solving(&series, &config);
        assert!(prior_streams_empty(&masked));

        let seeded = solve_series(&series, &default_estimator_config());
        let unseeded = solve_series(&series, &config);
        assert!(seeded
            .diagnostics
            .warnings
            .contains(&"rlinput_solver_path=single".to_string()));
        assert!(unseeded
            .diagnostics
            .warnings
            .contains(&"rlinput_solver_path=single".to_string()));
    }

    #[test]
    fn null_fast_path_generates_zero_event_hypotheses() {
        let series = quiet_series(2);
        let player = &series.players[0];
        let mut tracker = tracker_for_segment(
            player,
            &crate::segment::segment_replay(&series).players[0].segments[0],
            120.0,
        );
        let interval = &crate::segment::segment_replay(&series).players[0].segments[0]
            .lattice
            .intervals[0];
        let state = car_state(player, 0, &tracker);
        let observed = PortableEngine::new().rollout(
            &state,
            &TickPlan {
                controls: vec![Controls::default(); interval_ticks(interval) as usize],
                events: Vec::new(),
            },
            interval_ticks(interval),
        );
        let candidates = generate_candidates(
            &state,
            &observed,
            &tracker,
            interval,
            vec![Controls::default(); interval_ticks(interval) as usize],
            &[],
            &default_estimator_config(),
            SegmentKind::Air,
        );
        assert_eq!(
            candidates
                .candidates
                .iter()
                .filter(|candidate| !candidate.is_null())
                .count(),
            0
        );
        assert_eq!(candidates.candidates.len(), 1);
        assert!(candidates.candidates[0].is_null());
        tracker.advance_to(4);
    }

    #[test]
    fn unseeded_synthetic_second_actions_are_detected() {
        for (kind, expected) in [
            (TickEventKind::Dodge { dir: [1.0, 0.0] }, "Dodge"),
            (TickEventKind::DoubleJump, "DoubleJump"),
        ] {
            let series = two_frame_rollout(
                true,
                4,
                vec![TickEvent {
                    tick_offset: 1,
                    kind,
                }],
            );
            let output = solve_series(
                &series,
                &EstimatorConfig {
                    mode: Mode::Unseeded,
                    ..default_estimator_config()
                },
            );
            let events = &output.timelines[0].events;
            assert!(
                events
                    .iter()
                    .any(|event| event_name(&event.kind) == expected),
                "{expected} not found in {events:?}"
            );
        }

        let stall = two_frame_rollout(
            true,
            80,
            vec![TickEvent {
                tick_offset: 1,
                kind: TickEventKind::Dodge { dir: [0.0, 0.0] },
            }],
        );
        let output = solve_series(
            &stall,
            &EstimatorConfig {
                mode: Mode::Unseeded,
                ..default_estimator_config()
            },
        );
        assert!(
            output.timelines[0]
                .events
                .iter()
                .any(|event| matches!(event.kind, SolvedEventKind::Stall)),
            "Stall not found in {:?}",
            output.timelines[0].events
        );
    }

    #[test]
    fn long_gap_composite_press_release_dodge_is_solved_with_confidence_cap() {
        let series = two_frame_rollout(
            false,
            23,
            vec![
                TickEvent {
                    tick_offset: 0,
                    kind: TickEventKind::JumpPress,
                },
                TickEvent {
                    tick_offset: 3,
                    kind: TickEventKind::JumpRelease,
                },
                TickEvent {
                    tick_offset: 6,
                    kind: TickEventKind::Dodge { dir: [1.0, 0.0] },
                },
            ],
        );
        let output = solve_series(
            &series,
            &EstimatorConfig {
                mode: Mode::Unseeded,
                ..default_estimator_config()
            },
        );
        let events = &output.timelines[0].events;
        assert!(events
            .iter()
            .any(|event| matches!(event.kind, SolvedEventKind::JumpPress)));
        assert!(events
            .iter()
            .any(|event| matches!(event.kind, SolvedEventKind::JumpRelease)));
        assert!(events
            .iter()
            .any(|event| matches!(event.kind, SolvedEventKind::Dodge { .. })));
        assert!(events
            .iter()
            .all(|event| event.confidence <= LONG_GAP_CONFIDENCE_CAP));
        assert!(events
            .iter()
            .all(|event| event.flags.contains(AmbiguityFlags::LONG_GAP)));
    }

    #[test]
    #[ignore = "set RLINPUT_SERIES_JSON to an exported ReplaySeries for Replay_files/0925.replay"]
    fn exported_0925_unseeded_flip_agreement_and_wall_time() {
        let path = std::env::var("RLINPUT_SERIES_JSON")
            .expect("RLINPUT_SERIES_JSON should point to exported ReplaySeries JSON");
        let file = std::fs::File::open(path).expect("fixture should open");
        let series: ReplaySeries = serde_json::from_reader(file).expect("fixture should parse");
        let seeded_edges = seeded_flip_intervals(&series);
        let mut config = default_estimator_config();
        config.mode = Mode::Unseeded;
        config.engine = if cfg!(feature = "sim") {
            EnginePreference::PreferReference
        } else {
            EnginePreference::PortableOnly
        };
        let started = std::time::Instant::now();
        let output = solve_series(&series, &config);
        let elapsed = started.elapsed();
        let unseeded = solved_flip_intervals(&output);
        let agreement = if seeded_edges.is_empty() {
            0.0
        } else {
            seeded_edges.intersection(&unseeded).count() as f32 / seeded_edges.len() as f32
        };
        println!(
            "0925_unseeded,seeded_flip_intervals={},unseeded_flip_intervals={},agreement={agreement:.3},wall_time_seconds={:.3}",
            seeded_edges.len(),
            unseeded.len(),
            elapsed.as_secs_f64()
        );
        assert!(!unseeded.is_empty());
    }

    fn quiet_series(frames: usize) -> ReplaySeries {
        let mut states = Vec::new();
        let mut state = base_state(true);
        states.push(state);
        for _ in 1..frames {
            state = PortableEngine::new().rollout(
                &state,
                &TickPlan {
                    controls: vec![Controls::default(); 4],
                    events: Vec::new(),
                },
                4,
            );
            states.push(state);
        }
        series_from_states(states, vec![1.0 / 30.0; frames], vec![true; frames])
    }

    fn two_frame_rollout(airborne_start: bool, ticks: u32, events: Vec<TickEvent>) -> ReplaySeries {
        let start = base_state(airborne_start);
        let end = PortableEngine::new().rollout(
            &start,
            &TickPlan {
                controls: vec![Controls::default(); ticks as usize],
                events,
            },
            ticks,
        );
        series_from_states(
            vec![start, end],
            vec![0.0, ticks as f32 / 120.0],
            vec![!airborne_start, false],
        )
    }

    fn base_state(airborne: bool) -> CarPhysState {
        CarPhysState {
            pos: [0.0, 0.0, if airborne { 500.0 } else { 17.0 }],
            vel: [0.0; 3],
            rot: identity_rot_mat(),
            ang_vel: [0.0; 3],
            boost: 100.0,
            is_boosting: false,
            boosting_time: 0.0,
            has_jumped: airborne,
            has_double_jumped: false,
            has_flipped: false,
            is_jumping: false,
            is_flipping: false,
            jump_time: 0.1,
            flip_time: 0.0,
            air_time_since_jump: if airborne { 0.1 } else { 0.0 },
            flip_rel_torque: [0.0; 3],
        }
    }

    fn series_from_states(
        states: Vec<CarPhysState>,
        deltas: Vec<f32>,
        on_ground: Vec<bool>,
    ) -> ReplaySeries {
        let frames = Kinematics {
            pos: states.iter().map(|state| state.pos).collect(),
            vel: states.iter().map(|state| state.vel).collect(),
            quat_xyzw: vec![[0.0, 0.0, 0.0, 1.0]; states.len()],
            ang_vel: states.iter().map(|state| state.ang_vel).collect(),
            on_ground,
            sleeping: vec![false; states.len()],
            demolished: vec![false; states.len()],
        };
        ReplaySeries {
            tick_rate: 120.0,
            build_bucket: "test".to_string(),
            players: vec![PlayerSeries {
                player_id: "p0".to_string(),
                frames,
                replicated: ReplicatedChannels {
                    throttle_raw: vec![128; states.len()],
                    steer_raw: vec![128; states.len()],
                    handbrake: vec![false; states.len()],
                    boost_amount_raw: vec![255; states.len()],
                    boost_active_raw: vec![false; states.len()],
                },
                component: empty_component_stream(states.len()),
            }],
            ball: BallSeries {
                pos: vec![[10_000.0, 10_000.0, 93.0]; states.len()],
                vel: vec![[0.0; 3]; states.len()],
            },
            deltas,
            demo_events: Vec::new(),
            touch_events: Vec::new(),
            kickoff_markers: Vec::new(),
        }
    }

    fn event_name(kind: &SolvedEventKind) -> &'static str {
        match kind {
            SolvedEventKind::JumpPress => "JumpPress",
            SolvedEventKind::JumpRelease => "JumpRelease",
            SolvedEventKind::DoubleJump => "DoubleJump",
            SolvedEventKind::Dodge { .. } => "Dodge",
            SolvedEventKind::Stall => "Stall",
            SolvedEventKind::Liftoff => "Liftoff",
            SolvedEventKind::Landing => "Landing",
        }
    }

    fn seeded_flip_intervals(series: &ReplaySeries) -> HashSet<(String, u32)> {
        let mut out = HashSet::new();
        for player in &series.players {
            for edge in crate::tracker::reconstruct_seeded_edges(&player.component) {
                if matches!(
                    edge.component,
                    ComponentKind::DodgeTorque | ComponentKind::DoubleJumpImpulse
                ) {
                    out.insert((player.player_id.clone(), edge.frame_index));
                }
            }
        }
        out
    }

    fn solved_flip_intervals(output: &SolveOutput) -> HashSet<(String, u32)> {
        let mut out = HashSet::new();
        for timeline in &output.timelines {
            for event in &timeline.events {
                if matches!(
                    event.kind,
                    SolvedEventKind::Dodge { .. }
                        | SolvedEventKind::DoubleJump
                        | SolvedEventKind::Stall
                ) {
                    out.insert((timeline.player_id.clone(), event.frame_index));
                }
            }
        }
        out
    }
}
