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
        ComponentKind, ComponentStream, EnginePreference, EstimatorConfig, FitWeights,
        KinematicFreshness, Mode, PlayerSeries, ReplaySeries, SolverThresholds, WithheldChannels,
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

#[derive(Clone, Debug)]
struct ScoringInterval {
    start_frame: u32,
    interval: LatticeInterval,
}

#[derive(Clone, Debug)]
struct TimedSeededEdge {
    edge: ReconstructedEdge,
    tick_range: (u32, u32),
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
    frame_index: Option<u32>,
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
    let mut freshness = KinematicFreshness::from_frames(&player.frames);
    for segment in segments {
        freshness.mark_fresh(segment.frame_span.0);
    }

    for segment in segments {
        let mut tracker = tracker_for_segment(player, segment, series.tick_rate);
        let mut branching = BranchingTracker::new(tracker.clone());
        let mut segment_confidence = 1.0f32;
        let segment_base_frame = segment.frame_span.0.saturating_sub(1);
        let segment_base_time = frame_times
            .get(segment_base_frame as usize)
            .copied()
            .unwrap_or_default();

        for scoring in fresh_scoring_intervals(segment, &freshness) {
            let start_frame = scoring.start_frame;
            let interval = &scoring.interval;
            let end_frame = interval.frame_index;
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
                segment,
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

fn fresh_scoring_intervals(
    segment: &Segment,
    freshness: &KinematicFreshness,
) -> Vec<ScoringInterval> {
    let mut out = Vec::new();
    let mut anchor_frame = segment.frame_span.0.saturating_sub(1);
    let mut anchor_tick = 0;
    let mut anchor_time = 0.0;
    let mut flags = AmbiguityFlags::empty();

    for interval in &segment.lattice.intervals {
        flags |= interval.flags;
        if !freshness.is_fresh(interval.frame_index) {
            continue;
        }
        if interval.frame_index != anchor_frame {
            out.push(ScoringInterval {
                start_frame: anchor_frame,
                interval: LatticeInterval {
                    frame_index: interval.frame_index,
                    tick_range: (anchor_tick, interval.tick_range.1),
                    time_range: (anchor_time, interval.time_range.1),
                    flags,
                },
            });
        }
        anchor_frame = interval.frame_index;
        anchor_tick = interval.tick_range.1;
        anchor_time = interval.time_range.1;
        flags = AmbiguityFlags::empty();
    }

    out
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
    segment: &Segment,
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
        hints.edges_for_interval(segment, start_frame, end_frame, interval.tick_range.0),
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
    let branch_width = if scored.first().is_some_and(|item| item.candidate.is_null()) {
        1
    } else {
        BranchingTracker::DEFAULT_BEAM_WIDTH
    };
    let branch_options = scored
        .iter()
        .enumerate()
        .take(branch_width)
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
    seeded_edges: Vec<TimedSeededEdge>,
    config: &EstimatorConfig,
    segment_kind: SegmentKind,
) -> CandidateSet {
    let ticks = interval_ticks(interval);
    let null = Candidate::null(base_controls.clone(), interval.flags);
    let null_energy = score_null(state_k, observed_end, ticks, &null, &config.fit);
    if null_energy
        <= f64::from(
            config
                .fit
                .reject_threshold
                .max(config.fit.null_event_accept_margin),
        )
        && seeded_edges.is_empty()
        && !interval.flags.contains(AmbiguityFlags::LONG_GAP)
    {
        return CandidateSet {
            candidates: vec![null],
        };
    }

    let mut candidates = vec![null];
    let seeded = seeded_candidate_action_sets(&seeded_edges);
    if !seeded.is_empty() {
        for actions in seeded {
            if let Some(candidate) =
                candidate_from_actions(actions, base_controls.clone(), interval.flags)
            {
                if candidate_legal(tracker, &candidate, interval.tick_range.0) {
                    candidates.push(candidate);
                }
            }
        }
    } else {
        let mut events = kinematic_candidate_events(state_k, observed_end, tracker, segment_kind);
        if interval.flags.contains(AmbiguityFlags::LONG_GAP) && second_available(tracker) {
            push_unique_event(&mut events, CandidateEvent::Stall);
        }
        for event in events {
            for tick_offset in 0..ticks {
                if let Some(candidate) = single_event_candidate(
                    event,
                    tick_offset,
                    base_controls.clone(),
                    interval.flags,
                ) {
                    if candidate_legal(tracker, &candidate, interval.tick_range.0) {
                        candidates.push(candidate);
                    }
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
    controls: Vec<Controls>,
    flags: AmbiguityFlags,
) -> Option<Candidate> {
    candidate_from_actions(
        vec![CandidateAction {
            tick_offset,
            event,
            frame_index: None,
        }],
        controls,
        flags,
    )
}

fn candidate_from_actions(
    mut actions: Vec<CandidateAction>,
    mut controls: Vec<Controls>,
    flags: AmbiguityFlags,
) -> Option<Candidate> {
    if controls.is_empty() {
        return None;
    }
    actions.sort_by_key(|action| action.tick_offset);
    for action in &actions {
        match action.event {
            CandidateEvent::JumpPress => {
                for control in controls.iter_mut().skip(action.tick_offset as usize) {
                    control.jump = true;
                }
            }
            CandidateEvent::JumpRelease => {
                for control in controls.iter_mut().skip(action.tick_offset as usize) {
                    control.jump = false;
                }
            }
            CandidateEvent::DoubleJump | CandidateEvent::Dodge { .. } | CandidateEvent::Stall => {}
        }
    }
    Some(Candidate {
        actions,
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
                                frame_index: None,
                            },
                            CandidateAction {
                                tick_offset: release,
                                event: CandidateEvent::JumpRelease,
                                frame_index: None,
                            },
                            CandidateAction {
                                tick_offset: second,
                                event,
                                frame_index: None,
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

fn seeded_candidate_action_sets(edges: &[TimedSeededEdge]) -> Vec<Vec<CandidateAction>> {
    let mut specs = Vec::new();
    for edge in edges {
        let event = match edge.edge.component {
            ComponentKind::Jump => {
                if edge
                    .edge
                    .counter_delta
                    .as_ref()
                    .is_some_and(|delta| delta.current % 2 == 0)
                {
                    Some(CandidateEvent::JumpRelease)
                } else {
                    Some(CandidateEvent::JumpPress)
                }
            }
            ComponentKind::DoubleJumpImpulse => Some(CandidateEvent::DoubleJump),
            ComponentKind::DodgeTorque => {
                match edge.edge.vector.map(classify_dodge_torque_vector) {
                    Some(SecondActionClass::Dodge { dir, .. }) => {
                        Some(CandidateEvent::Dodge { dir })
                    }
                    Some(SecondActionClass::Stall) => Some(CandidateEvent::Stall),
                    Some(SecondActionClass::DoubleJump) => Some(CandidateEvent::DoubleJump),
                    None => Some(CandidateEvent::Dodge { dir: [1.0, 0.0] }),
                }
            }
            ComponentKind::Boost => None,
        };
        if let Some(event) = event {
            specs.push((event, edge.edge.frame_index, edge.tick_range));
        }
    }
    if specs.is_empty() {
        return Vec::new();
    }

    let mut sets = vec![Vec::new()];
    for (idx, (event, frame_index, tick_range)) in specs.into_iter().enumerate() {
        let offsets: Vec<u32> = if idx < 2 && tick_range.0 < tick_range.1 {
            (tick_range.0..tick_range.1).collect()
        } else {
            vec![tick_range.0]
        };
        let mut next = Vec::new();
        for existing in &sets {
            for tick_offset in &offsets {
                let mut actions = existing.clone();
                let action = CandidateAction {
                    tick_offset: *tick_offset,
                    event,
                    frame_index: Some(frame_index),
                };
                if !actions.contains(&action) {
                    actions.push(action);
                }
                next.push(actions);
            }
        }
        sets = next;
    }
    sets
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
        && best_event_beats_null_margin(&scored, &config.fit)
    {
        scored = reference.rescore(state_k, observed_end, ticks, scored, &config.fit);
    }
    scored
}

fn best_event_beats_null_margin(scored: &[ScoredCandidate], weights: &FitWeights) -> bool {
    let Some(null_energy) = scored
        .iter()
        .find(|item| item.candidate.is_null())
        .map(|item| item.energy)
    else {
        return scored.iter().any(|item| !item.candidate.is_null());
    };
    scored
        .iter()
        .filter(|item| !item.candidate.is_null())
        .map(|item| item.energy)
        .min_by(|a, b| a.total_cmp(b))
        .is_some_and(|event_energy| {
            null_energy - event_energy > f64::from(weights.null_event_accept_margin)
        })
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
    let null_energy = scored
        .iter()
        .find(|item| item.candidate.is_null())
        .map(|item| item.energy);
    scored.sort_by(|a, b| {
        adjusted_event_energy(a.energy, !a.candidate.is_null(), null_energy, weights).total_cmp(
            &adjusted_event_energy(b.energy, !b.candidate.is_null(), null_energy, weights),
        )
    });
    if scored.first().is_some_and(|item| item.candidate.is_null()) {
        for item in &mut scored {
            if !item.candidate.is_null() {
                item.flags |= AmbiguityFlags::LOW_MARGIN;
            }
        }
    }
    scored
}

fn adjusted_event_energy(
    energy: f64,
    is_event: bool,
    null_energy: Option<f64>,
    weights: &FitWeights,
) -> f64 {
    if is_event && null_energy.is_some() {
        energy + f64::from(weights.null_event_accept_margin.max(0.0))
    } else {
        energy
    }
}

fn prefer_event_when_null_is_rejected(scored: &mut [ScoredCandidate], weights: &FitWeights) {
    if scored.first().is_some_and(|item| {
        item.candidate.is_null() && item.energy > f64::from(weights.reject_threshold)
    }) {
        if let Some(event_index) = scored.iter().position(|item| {
            !item.candidate.is_null()
                && scored[0].energy - item.energy > f64::from(weights.null_event_accept_margin)
        }) {
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
        let mut selected = Vec::new();
        if let Some(null) = scored.iter().find(|item| item.candidate.is_null()) {
            selected.push(null.clone());
        }
        for item in scored {
            if selected.len() >= REFERENCE_SURVIVORS {
                break;
            }
            if !item.candidate.is_null() {
                selected.push(item);
            }
        }

        let rescored: Vec<_> = selected
            .into_iter()
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
                frame_index: action.frame_index.unwrap_or(frame_index),
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

    fn edges_for_interval(
        &self,
        segment: &Segment,
        start_frame: u32,
        end_frame: u32,
        tick_start: u64,
    ) -> Vec<TimedSeededEdge> {
        let mut out = Vec::new();
        for interval in &segment.lattice.intervals {
            let frame = interval.frame_index;
            if frame <= start_frame || frame > end_frame {
                continue;
            }
            let tick_range = (
                interval
                    .tick_range
                    .0
                    .saturating_sub(tick_start)
                    .min(u64::from(u32::MAX)) as u32,
                interval
                    .tick_range
                    .1
                    .saturating_sub(tick_start)
                    .min(u64::from(u32::MAX)) as u32,
            );
            if let Some(edges) = self.edges.get(&frame) {
                out.extend(
                    edges
                        .iter()
                        .cloned()
                        .map(|edge| TimedSeededEdge { edge, tick_range }),
                );
            }
        }
        out
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
        model::{BallSeries, ComponentEventIn, Kinematics, ReplicatedChannels},
    };

    #[test]
    fn fresh_scoring_intervals_span_held_frame_terminators() {
        let segment = Segment {
            summary: crate::timeline::SegmentSummary {
                id: 0,
                tick_span: (0, 12),
                boundary_causes: Vec::new(),
                confidence: 0.0,
            },
            kind: SegmentKind::Air,
            frame_span: (1, 4),
            lattice: crate::lattice::SegmentLattice {
                intervals: vec![
                    LatticeInterval {
                        frame_index: 1,
                        tick_range: (0, 4),
                        time_range: (0.0, 1.0 / 30.0),
                        flags: AmbiguityFlags::empty(),
                    },
                    LatticeInterval {
                        frame_index: 2,
                        tick_range: (4, 8),
                        time_range: (1.0 / 30.0, 2.0 / 30.0),
                        flags: AmbiguityFlags::empty(),
                    },
                    LatticeInterval {
                        frame_index: 3,
                        tick_range: (8, 12),
                        time_range: (2.0 / 30.0, 3.0 / 30.0),
                        flags: AmbiguityFlags::empty(),
                    },
                ],
                diagnostics: crate::lattice::LatticeDiagnostics::default(),
            },
        };
        let frames = Kinematics {
            pos: vec![
                [0.0, 0.0, 0.0],
                [10.0, 0.0, 0.0],
                [10.0, 0.0, 0.0],
                [30.0, 0.0, 0.0],
            ],
            vel: vec![[0.0; 3]; 4],
            quat_xyzw: vec![[0.0, 0.0, 0.0, 1.0]; 4],
            ang_vel: vec![[0.0; 3]; 4],
            on_ground: vec![false; 4],
            sleeping: vec![false; 4],
            demolished: vec![false; 4],
        };
        let mut freshness = KinematicFreshness::from_frames(&frames);
        freshness.mark_fresh(segment.frame_span.0);

        let intervals = fresh_scoring_intervals(&segment, &freshness);

        assert_eq!(intervals.len(), 2);
        assert_eq!(intervals[0].start_frame, 0);
        assert_eq!(intervals[0].interval.frame_index, 1);
        assert_eq!(intervals[1].start_frame, 1);
        assert_eq!(intervals[1].interval.frame_index, 3);
        assert_eq!(intervals[1].interval.tick_range, (4, 12));
    }

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
            Vec::new(),
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
    fn seeded_edge_tick_search_recovers_mid_window_tick() {
        let mut series = two_frame_rollout(
            true,
            4,
            vec![TickEvent {
                tick_offset: 2,
                kind: TickEventKind::Dodge { dir: [1.0, 0.0] },
            }],
        );
        series.players[0].component.events.push(ComponentEventIn {
            t: 1.0 / 30.0,
            frame_index: 1,
            component: ComponentKind::DodgeTorque,
            vector: Some([0.0, 2.24, 0.0]),
            raw_value: None,
        });

        let output = solve_series(&series, &default_estimator_config());
        let event = output.timelines[0]
            .events
            .iter()
            .find(|event| matches!(event.kind, SolvedEventKind::Dodge { .. }))
            .expect("seeded dodge should be solved");

        assert_eq!(event.tick, 2);
        assert_eq!(event.frame_index, 1);
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
        let coalesced_seeded = coalesced_seeded_flip_intervals(&series);
        let mut config = default_estimator_config();
        config.mode = Mode::Unseeded;
        config.engine = if cfg!(feature = "sim") {
            EnginePreference::PreferReference
        } else {
            EnginePreference::PortableOnly
        };
        if let Ok(margin) = std::env::var("RLINPUT_MARGIN_ONLY") {
            config.fit.null_event_accept_margin =
                margin.parse().expect("RLINPUT_MARGIN_ONLY should be f32");
        }
        let started = std::time::Instant::now();
        let output = solve_series(&series, &config);
        let elapsed = started.elapsed();
        let unseeded = solved_flip_intervals(&output);
        let raw_hits = seeded_edges.intersection(&unseeded).count();
        let coalesced_hits = coalesced_seeded.intersection(&unseeded).count();
        let agreement = recall(raw_hits, seeded_edges.len());
        let coalesced_agreement = recall(coalesced_hits, coalesced_seeded.len());
        println!(
            "0925_unseeded,seeded_flip_intervals={},coalesced_seeded_flip_intervals={},unseeded_flip_intervals={},agreement={agreement:.3},coalesced_agreement={coalesced_agreement:.3},raw_jaccard={:.3},coalesced_jaccard={:.3},wall_time_seconds={:.3}",
            seeded_edges.len(),
            coalesced_seeded.len(),
            unseeded.len(),
            jaccard(raw_hits, seeded_edges.len(), unseeded.len()),
            jaccard(coalesced_hits, coalesced_seeded.len(), unseeded.len()),
            elapsed.as_secs_f64()
        );
        assert!(!unseeded.is_empty());
    }

    #[test]
    #[ignore = "set RLINPUT_SERIES_JSON to an exported ReplaySeries for Replay_files/0925.replay"]
    fn exported_0925_agreement_ruler_diagnostics() {
        let path = std::env::var("RLINPUT_SERIES_JSON")
            .expect("RLINPUT_SERIES_JSON should point to exported ReplaySeries JSON");
        let file = std::fs::File::open(path).expect("fixture should open");
        let series: ReplaySeries = serde_json::from_reader(file).expect("fixture should parse");
        let raw_seeded = seeded_flip_intervals(&series);
        let coalesced_seeded = coalesced_seeded_flip_intervals(&series);
        let mut config = default_estimator_config();
        config.mode = Mode::Unseeded;
        config.engine = if cfg!(feature = "sim") {
            EnginePreference::PreferReference
        } else {
            EnginePreference::PortableOnly
        };
        let output = solve_series(&series, &config);
        let unseeded = solved_flip_intervals(&output);
        let raw_hits = raw_seeded.intersection(&unseeded).count();
        let coalesced_hits = coalesced_seeded.intersection(&unseeded).count();
        println!(
            "ruler,raw_seeded={},coalesced_seeded={},unseeded={},raw_hits={},raw_recall={:.3},raw_jaccard={:.3},coalesced_hits={},coalesced_recall={:.3},coalesced_jaccard={:.3}",
            raw_seeded.len(),
            coalesced_seeded.len(),
            unseeded.len(),
            raw_hits,
            recall(raw_hits, raw_seeded.len()),
            jaccard(raw_hits, raw_seeded.len(), unseeded.len()),
            coalesced_hits,
            recall(coalesced_hits, coalesced_seeded.len()),
            jaccard(coalesced_hits, coalesced_seeded.len(), unseeded.len()),
        );
    }

    #[test]
    #[ignore = "set RLINPUT_DEV_SERIES_DIR to exported dev-set ReplaySeries JSON directory"]
    fn exported_dev_set_null_margin_calibration() {
        let dir = std::env::var("RLINPUT_DEV_SERIES_DIR")
            .expect("RLINPUT_DEV_SERIES_DIR should point to exported ReplaySeries JSONs");
        let margins = std::env::var("RLINPUT_MARGIN_ONLY")
            .ok()
            .and_then(|value| value.parse::<f32>().ok())
            .map_or_else(
                || {
                    vec![
                        0.0_f32, 4.0, 8.0, 12.0, 16.0, 20.0, 24.0, 32.0, 64.0, 128.0, 256.0,
                    ]
                },
                |margin| vec![margin],
            );
        for margin in margins {
            let mut seeded_total = 0usize;
            let mut retained_total = 0usize;
            let mut hallucinated_total = 0usize;
            let mut solved_total = 0usize;
            for entry in std::fs::read_dir(&dir).expect("dev series dir should read") {
                let path = entry.expect("entry should read").path();
                if path.extension().and_then(|ext| ext.to_str()) != Some("json") {
                    continue;
                }
                let file = std::fs::File::open(&path).expect("fixture should open");
                let series: ReplaySeries =
                    serde_json::from_reader(file).expect("fixture should parse");
                let seeded = coalesced_seeded_flip_intervals(&series);
                let mut config = default_estimator_config();
                config.mode = Mode::Unseeded;
                config.engine = if cfg!(feature = "sim") {
                    EnginePreference::PreferReference
                } else {
                    EnginePreference::PortableOnly
                };
                config.fit.null_event_accept_margin = margin;
                let solved = solved_flip_intervals(&solve_series(&series, &config));
                let retained = seeded.intersection(&solved).count();
                seeded_total += seeded.len();
                retained_total += retained;
                hallucinated_total += solved.difference(&seeded).count();
                solved_total += solved.len();
            }
            println!(
                "margin_calibration,margin={margin:.1},seeded_known_flips={seeded_total},retained={retained_total},retention={:.3},solved_flips={solved_total},quiet_hallucinations={hallucinated_total}",
                recall(retained_total, seeded_total),
            );
        }
    }

    #[test]
    #[ignore = "set RLINPUT_SERIES_JSON to an exported ReplaySeries for Replay_files/0925.replay"]
    fn exported_0925_quiet_flip_disagreement_diagnostics() {
        let path = std::env::var("RLINPUT_SERIES_JSON")
            .expect("RLINPUT_SERIES_JSON should point to exported ReplaySeries JSON");
        let file = std::fs::File::open(path).expect("fixture should open");
        let series: ReplaySeries = serde_json::from_reader(file).expect("fixture should parse");
        let diags = quiet_flip_disagreement_diags(&series);
        let low64 = diags.iter().filter(|diag| diag.margin <= 64.0).count();
        let after_prior = diags.iter().filter(|diag| diag.after_prior).count();
        let first_half = diags.iter().filter(|diag| diag.segment_frac < 0.5).count();
        let second_half = diags.len().saturating_sub(first_half);
        let low_kinematic = diags
            .iter()
            .filter(|diag| {
                diag.planar_delta <= crate::consts::FIT_SIGMA_VEL_MEASURED
                    && diag.ang_delta <= crate::consts::FIT_SIGMA_ANG_VEL_MEASURED
            })
            .count();
        println!(
            "quiet_disagreement_summary,count={},margin_p50={:.3},margin_p68={:.3},margin_p90={:.3},margin_le_64={},after_prior_same_segment={},first_half={},second_half={},low_kinematic_floor={}",
            diags.len(),
            percentile(diags.iter().map(|diag| diag.margin).collect(), 0.50),
            percentile(diags.iter().map(|diag| diag.margin).collect(), 0.68),
            percentile(diags.iter().map(|diag| diag.margin).collect(), 0.90),
            low64,
            after_prior,
            first_half,
            second_half,
            low_kinematic,
        );
        for diag in diags.iter().take(12) {
            println!(
                "quiet_disagreement,player={},segment={},frames={}..{},ticks={:?},null={:.3},flip={:.3},margin={:.3},flags={:?},portable={},reference={},planar_delta={:.3},vertical_delta={:.3},ang_delta={:.3},after_prior={}",
                diag.player_id,
                diag.segment_id,
                diag.start_frame,
                diag.end_frame,
                diag.tick_range,
                diag.null_energy,
                diag.flip_energy,
                diag.margin,
                diag.flags,
                diag.portable_best,
                diag.reference_best,
                diag.planar_delta,
                diag.vertical_delta,
                diag.ang_delta,
                diag.after_prior,
            );
        }
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

    fn coalesced_seeded_flip_intervals(series: &ReplaySeries) -> HashSet<(String, u32)> {
        let segmentation = crate::segment::segment_replay(series);
        let mut out = HashSet::new();
        for segmented_player in &segmentation.players {
            let Some(player) = series
                .players
                .iter()
                .find(|player| player.player_id == segmented_player.player_id)
            else {
                continue;
            };
            let seeded_frames: HashSet<_> =
                crate::tracker::reconstruct_seeded_edges(&player.component)
                    .into_iter()
                    .filter(|edge| {
                        matches!(
                            edge.component,
                            ComponentKind::DodgeTorque | ComponentKind::DoubleJumpImpulse
                        )
                    })
                    .map(|edge| edge.frame_index)
                    .collect();
            let mut freshness = KinematicFreshness::from_frames(&player.frames);
            for segment in &segmented_player.segments {
                freshness.mark_fresh(segment.frame_span.0);
                for scoring in fresh_scoring_intervals(segment, &freshness) {
                    if seeded_frames.iter().any(|frame| {
                        *frame > scoring.start_frame && *frame <= scoring.interval.frame_index
                    }) {
                        out.insert((player.player_id.clone(), scoring.interval.frame_index));
                    }
                }
            }
        }
        out
    }

    #[derive(Clone, Debug)]
    struct QuietFlipDiag {
        player_id: String,
        segment_id: u32,
        start_frame: u32,
        end_frame: u32,
        tick_range: (u64, u64),
        null_energy: f64,
        flip_energy: f64,
        margin: f64,
        flags: AmbiguityFlags,
        portable_best: &'static str,
        reference_best: &'static str,
        planar_delta: f32,
        vertical_delta: f32,
        ang_delta: f32,
        segment_frac: f32,
        after_prior: bool,
    }

    fn quiet_flip_disagreement_diags(series: &ReplaySeries) -> Vec<QuietFlipDiag> {
        let mut config = default_estimator_config();
        config.mode = Mode::Unseeded;
        config.engine = if cfg!(feature = "sim") {
            EnginePreference::PreferReference
        } else {
            EnginePreference::PortableOnly
        };
        let masked = masked_series_for_solving(series, &config);
        let segmentation = segment_replay_with_splits_and_confidences(
            &masked,
            &[],
            CONFIDENT_SEGMENT_THRESHOLD,
            |_player_id, _segment| None,
        );
        let mut out = Vec::new();

        for segmented_player in &segmentation.players {
            let Some(player_index) = masked
                .players
                .iter()
                .position(|player| player.player_id == segmented_player.player_id)
            else {
                continue;
            };
            let player = &masked.players[player_index];
            let original_player = &series.players[player_index];
            let seeded_frames: HashSet<_> =
                crate::tracker::reconstruct_seeded_edges(&original_player.component)
                    .into_iter()
                    .filter(|edge| {
                        matches!(
                            edge.component,
                            ComponentKind::DodgeTorque | ComponentKind::DoubleJumpImpulse
                        )
                    })
                    .map(|edge| edge.frame_index)
                    .collect();
            let hints = SeededHints::new(&player.component);
            let mut reference = ReferenceScorer::new();
            let mut freshness = KinematicFreshness::from_frames(&player.frames);
            for segment in &segmented_player.segments {
                freshness.mark_fresh(segment.frame_span.0);
            }

            for segment in &segmented_player.segments {
                let tracker = tracker_for_segment(player, segment, masked.tick_rate);
                let mut branching = BranchingTracker::new(tracker.clone());
                let intervals = fresh_scoring_intervals(segment, &freshness);
                let mut prior_quiet_flip = false;
                for (idx, scoring) in intervals.iter().enumerate() {
                    let start_frame = scoring.start_frame;
                    let interval = &scoring.interval;
                    let end_frame = interval.frame_index;
                    if frame_out_of_bounds(player, start_frame)
                        || frame_out_of_bounds(player, end_frame)
                    {
                        continue;
                    }
                    let interval_tracker = branching.best_tracker().clone();
                    let ticks = interval_ticks(interval);
                    let state_k = car_state(player, start_frame, &interval_tracker);
                    let observed_end = car_state(player, end_frame, &interval_tracker);
                    let base_controls = solve_controls(
                        player,
                        start_frame,
                        end_frame,
                        interval,
                        &interval_tracker,
                        &config,
                    );
                    let candidates = generate_candidates(
                        &state_k,
                        &observed_end,
                        &interval_tracker,
                        interval,
                        base_controls,
                        hints.edges_for_interval(
                            segment,
                            start_frame,
                            end_frame,
                            interval.tick_range.0,
                        ),
                        &config,
                        segment.kind,
                    );
                    let (mut scored, portable_best, reference_best) = score_candidates_for_diag(
                        &state_k,
                        &observed_end,
                        ticks,
                        &candidates.candidates,
                        &config,
                        &mut reference,
                    );
                    if scored.is_empty() {
                        scored.push(score_one(
                            &mut PortableEngine::new(),
                            &state_k,
                            &observed_end,
                            ticks,
                            Candidate::null(
                                vec![Controls::default(); ticks as usize],
                                interval.flags,
                            ),
                            &config.fit,
                        ));
                    }
                    prefer_event_when_null_is_rejected(&mut scored, &config.fit);
                    prefer_long_gap_stall_z_damp(&mut scored, interval, &observed_end);

                    let quiet_seeded = !seeded_frames
                        .iter()
                        .any(|frame| *frame > start_frame && *frame <= end_frame);
                    let null_energy = scored
                        .iter()
                        .find(|item| item.candidate.is_null())
                        .map(|item| item.energy)
                        .unwrap_or(f64::NAN);
                    let best_flip = scored
                        .iter()
                        .filter(|item| candidate_has_flip(&item.candidate))
                        .min_by(|a, b| a.energy.total_cmp(&b.energy));
                    if quiet_seeded
                        && scored
                            .first()
                            .is_some_and(|item| candidate_has_flip(&item.candidate))
                    {
                        if let Some(best_flip) = best_flip {
                            let delta_v = diff(observed_end.vel, state_k.vel);
                            out.push(QuietFlipDiag {
                                player_id: player.player_id.clone(),
                                segment_id: segment.summary.id,
                                start_frame,
                                end_frame,
                                tick_range: interval.tick_range,
                                null_energy,
                                flip_energy: best_flip.energy,
                                margin: null_energy - best_flip.energy,
                                flags: scored[0].flags,
                                portable_best,
                                reference_best,
                                planar_delta: norm2([delta_v[0], delta_v[1]]),
                                vertical_delta: delta_v[2],
                                ang_delta: norm(diff(observed_end.ang_vel, state_k.ang_vel)),
                                segment_frac: idx as f32 / intervals.len().max(1) as f32,
                                after_prior: prior_quiet_flip,
                            });
                            prior_quiet_flip = true;
                        }
                    }
                    let branch_width =
                        if scored.first().is_some_and(|item| item.candidate.is_null()) {
                            1
                        } else {
                            BranchingTracker::DEFAULT_BEAM_WIDTH
                        };
                    let branch_options: Vec<_> = scored
                        .iter()
                        .enumerate()
                        .take(branch_width)
                        .map(|(rank, item)| BranchOption {
                            candidate: item.candidate.clone(),
                            score: rank as f64,
                        })
                        .collect();
                    apply_branch_options(&mut branching, &branch_options, interval.tick_range.0);
                }
            }
        }
        out
    }

    fn score_candidates_for_diag(
        state_k: &CarPhysState,
        observed_end: &CarPhysState,
        ticks: u32,
        candidates: &[Candidate],
        config: &EstimatorConfig,
        reference: &mut ReferenceScorer,
    ) -> (Vec<ScoredCandidate>, &'static str, &'static str) {
        let mut portable = PortableEngine::new();
        let portable_scored = rank_scored(
            candidates
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
                .collect(),
            &config.fit,
        );
        let portable_best = portable_scored
            .first()
            .map_or("none", |item| candidate_name(&item.candidate));
        let scored = if config.engine == EnginePreference::PreferReference
            && best_event_beats_null_margin(&portable_scored, &config.fit)
        {
            reference.rescore(state_k, observed_end, ticks, portable_scored, &config.fit)
        } else {
            portable_scored
        };
        let reference_best = scored
            .first()
            .map_or("none", |item| candidate_name(&item.candidate));
        (scored, portable_best, reference_best)
    }

    fn candidate_has_flip(candidate: &Candidate) -> bool {
        candidate.actions.iter().any(|action| {
            matches!(
                action.event,
                CandidateEvent::DoubleJump | CandidateEvent::Dodge { .. } | CandidateEvent::Stall
            )
        })
    }

    fn candidate_name(candidate: &Candidate) -> &'static str {
        if candidate.is_null() {
            "Null"
        } else if candidate
            .actions
            .iter()
            .any(|action| matches!(action.event, CandidateEvent::Dodge { .. }))
        {
            "Dodge"
        } else if candidate
            .actions
            .iter()
            .any(|action| action.event == CandidateEvent::DoubleJump)
        {
            "DoubleJump"
        } else if candidate
            .actions
            .iter()
            .any(|action| action.event == CandidateEvent::Stall)
        {
            "Stall"
        } else {
            "Other"
        }
    }

    fn percentile(mut values: Vec<f64>, q: f64) -> f64 {
        values.sort_by(|a, b| a.total_cmp(b));
        if values.is_empty() {
            return f64::NAN;
        }
        let idx = ((values.len() - 1) as f64 * q).round() as usize;
        values[idx]
    }

    fn recall(hits: usize, expected: usize) -> f32 {
        if expected == 0 {
            0.0
        } else {
            hits as f32 / expected as f32
        }
    }

    fn jaccard(hits: usize, left: usize, right: usize) -> f32 {
        let union = left + right - hits;
        if union == 0 {
            0.0
        } else {
            hits as f32 / union as f32
        }
    }
}
