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
        classify_dodge_torque_vector, seconds_to_ticks, BranchingTracker, CarTracker, ContactState,
        CounterDelta, EdgeEvidence, JumpState, ReconstructedEdge, SecondAction, SecondActionClass,
    },
};

const CONFIDENT_SEGMENT_THRESHOLD: f32 = 0.7;
const RETRO_VELOCITY_RESIDUAL_UU_PER_S: f32 = 150.0;
const RETRO_CAR_PROXIMITY_UU: f32 = 500.0;
const LONG_GAP_CONFIDENCE_CAP: f32 = 0.5;
const HYPOTHESIS_CAP: usize = 256;
const LIFTOFF_PRESS_BOUNDARY_LOOKBACK_FRAMES: u32 = 6;
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
    event_frame_index: Option<u32>,
    fit_liftoff_release: bool,
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
        let boundary_press_event = (config.mode == Mode::Unseeded)
            .then(|| implied_liftoff_boundary_press_event(player, segment, frame_times))
            .flatten();
        let mut segment_events = Vec::new();

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
            segment_events.extend(solved.events);
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

        if let Some(event) = boundary_press_event {
            if !segment_events.iter().any(|existing| {
                matches!(existing.kind, SolvedEventKind::JumpPress)
                    && existing.frame_index.abs_diff(event.frame_index)
                        <= LIFTOFF_PRESS_BOUNDARY_LOOKBACK_FRAMES
            }) {
                segment_events.insert(0, event);
            }
        }
        events.extend(segment_events);

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
    let state_k = car_state(player, start_frame, interval.tick_range.0, tracker);
    let observed_end = car_state(player, end_frame, interval.tick_range.1, tracker);
    let base_controls = solve_controls(player, start_frame, end_frame, interval, tracker, config);
    let seeded_edges = edges_for_interval_with_implied_liftoff(
        player,
        hints,
        segment,
        start_frame,
        end_frame,
        interval,
        config,
    );
    let candidates = generate_candidates(
        &state_k,
        &observed_end,
        tracker,
        interval,
        base_controls,
        seeded_edges,
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
fn edges_for_interval_with_implied_liftoff(
    player: &PlayerSeries,
    hints: &SeededHints,
    segment: &Segment,
    start_frame: u32,
    end_frame: u32,
    interval: &LatticeInterval,
    config: &EstimatorConfig,
) -> Vec<TimedSeededEdge> {
    let mut seeded_edges =
        hints.edges_for_interval(segment, start_frame, end_frame, interval.tick_range.0);
    if config.mode == Mode::Unseeded {
        if let Some(edge) = implied_liftoff_jump_edge(
            player,
            segment,
            start_frame,
            end_frame,
            interval,
            &seeded_edges,
        ) {
            seeded_edges.push(edge);
        }
    }
    seeded_edges
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
    // The event margin is a ranking prior, not a reason to skip candidate enumeration.
    if null_energy <= f64::from(config.fit.reject_threshold)
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
    if !first_jump_available(tracker) {
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
            specs.push((
                event,
                edge.event_frame_index,
                edge.tick_range,
                edge.fit_liftoff_release,
            ));
        }
    }
    if specs.is_empty() {
        return Vec::new();
    }

    let mut sets = vec![Vec::new()];
    for (idx, (event, frame_index, tick_range, fit_liftoff_release)) in
        specs.into_iter().enumerate()
    {
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
                    frame_index,
                };
                if !actions.contains(&action) {
                    actions.push(action.clone());
                }
                next.push(actions);
                if fit_liftoff_release && event == CandidateEvent::JumpPress {
                    for release_offset in liftoff_release_offsets(*tick_offset, tick_range.1) {
                        let mut actions = existing.clone();
                        actions.push(action.clone());
                        actions.push(CandidateAction {
                            tick_offset: release_offset,
                            event: CandidateEvent::JumpRelease,
                            frame_index,
                        });
                        next.push(actions);
                    }
                }
            }
        }
        sets = next;
    }
    sets
}

fn liftoff_release_offsets(press_offset: u32, max_offset: u32) -> impl Iterator<Item = u32> {
    let min = press_offset + seconds_to_ticks(crate::consts::JUMP_MIN_TIME, 120.0) as u32;
    let max = press_offset + seconds_to_ticks(crate::consts::JUMP_MAX_TIME, 120.0) as u32;
    let end = max.min(max_offset);
    (min..=end).step_by(2)
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
    let up_residual = dot(vel_residual, up(state_k.rot));
    let vertical_residual = vel_residual[2];
    let ang_residual = norm(diff(observed_end.ang_vel, state_k.ang_vel));

    if segment_kind == SegmentKind::Air
        && first_jump_available(tracker)
        && up_residual > crate::consts::JUMP_LIFTOFF_MIN_UP_VEL_STEP
    {
        push_unique_event(&mut events, CandidateEvent::JumpPress);
    }
    if matches!(tracker.jump, JumpState::Holding { .. }) {
        push_unique_event(&mut events, CandidateEvent::JumpRelease);
    }
    if segment_kind == SegmentKind::Air && second_available(tracker) {
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

fn car_state(
    player: &PlayerSeries,
    frame: u32,
    current_tick: u64,
    tracker: &CarTracker,
) -> CarPhysState {
    let base = frame_state(player, frame);
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
        has_jumped: !matches!(tracker.jump, JumpState::Idle),
        has_double_jumped: matches!(tracker.second, SecondAction::UsedDoubleJump { .. }),
        has_flipped: flip.is_some(),
        is_jumping: tracker.jump_hold_accel_at(current_tick).is_some(),
        is_flipping: flip.is_some_and(|phase| phase.start_tick <= 120),
        jump_time: match tracker.jump {
            JumpState::Holding { press_tick } => ticks_since_tick(current_tick, press_tick),
            JumpState::Released { press_tick, .. } => ticks_since_tick(current_tick, press_tick),
            JumpState::Idle => 0.0,
        },
        flip_time: flip
            .map(|phase| ticks_since_tick(current_tick, phase.start_tick))
            .unwrap_or(0.0),
        air_time_since_jump: match tracker.jump {
            JumpState::Released { jump_end_tick, .. } => {
                ticks_since_tick(current_tick, jump_end_tick)
            }
            _ => 0.0,
        },
        flip_rel_torque: flip
            .map(|phase| [phase.rel_torque[0], phase.rel_torque[1], 0.0])
            .unwrap_or([0.0, 0.0, 0.0]),
    }
}

fn implied_liftoff_jump_edge(
    player: &PlayerSeries,
    segment: &Segment,
    start_frame: u32,
    end_frame: u32,
    interval: &LatticeInterval,
    seeded_edges: &[TimedSeededEdge],
) -> Option<TimedSeededEdge> {
    let liftoff_frame = segment.frame_span.0;
    if segment.kind != SegmentKind::Air
        || !segment
            .summary
            .boundary_causes
            .contains(&crate::timeline::BoundaryCause::Liftoff)
        || liftoff_frame <= start_frame
        || liftoff_frame > end_frame
        || seeded_edges.iter().any(timed_edge_is_jump_press)
        || !press_liftoff(player, liftoff_frame)
    {
        return None;
    }
    let tick_range = segment
        .lattice
        .intervals
        .iter()
        .find(|candidate| candidate.frame_index == liftoff_frame)
        .map(|candidate| {
            (
                candidate
                    .tick_range
                    .0
                    .saturating_sub(interval.tick_range.0)
                    .min(u64::from(u32::MAX)) as u32,
                candidate
                    .tick_range
                    .1
                    .saturating_sub(interval.tick_range.0)
                    .min(u64::from(u32::MAX)) as u32,
            )
        })
        .unwrap_or((0, interval_ticks(interval)));
    Some(TimedSeededEdge {
        edge: ReconstructedEdge {
            frame_index: liftoff_frame,
            t: 0.0,
            component: ComponentKind::Jump,
            source: EdgeEvidence::RawCounter,
            vector: None,
            counter_delta: Some(CounterDelta {
                previous: 0,
                current: 1,
                delta_mod_256: 1,
                min_toggle_edges: 1,
                net_parity_flip: true,
                has_subframe_toggles: false,
            }),
        },
        tick_range,
        event_frame_index: None,
        fit_liftoff_release: true,
    })
}

fn timed_edge_is_jump_press(edge: &TimedSeededEdge) -> bool {
    edge.edge.component == ComponentKind::Jump
        && edge
            .edge
            .counter_delta
            .as_ref()
            .is_none_or(|delta| delta.current % 2 != 0)
}

fn implied_liftoff_boundary_press_event(
    player: &PlayerSeries,
    segment: &Segment,
    frame_times: &[f64],
) -> Option<SolvedEvent> {
    if segment.kind != SegmentKind::Air {
        return None;
    }
    let search_start = segment
        .frame_span
        .0
        .saturating_sub(LIFTOFF_PRESS_BOUNDARY_LOOKBACK_FRAMES)
        .max(1);
    let search_end = segment.frame_span.0.saturating_add(1);
    let liftoff_frame = (search_start..=search_end).find(|frame| press_liftoff(player, *frame))?;
    let tick = segment
        .lattice
        .intervals
        .iter()
        .find(|interval| interval.frame_index >= liftoff_frame)
        .map(|interval| interval.tick_range.0)
        .unwrap_or(segment.summary.tick_span.0);
    Some(SolvedEvent {
        kind: SolvedEventKind::JumpPress,
        tick,
        t: frame_times
            .get(liftoff_frame as usize)
            .copied()
            .unwrap_or_default(),
        frame_index: liftoff_frame,
        confidence: 0.3,
        flags: AmbiguityFlags::LOW_MARGIN,
    })
}

fn press_liftoff(player: &PlayerSeries, liftoff_frame: u32) -> bool {
    let frame = liftoff_frame as usize;
    if frame == 0
        || frame >= player.frames.vel.len()
        || frame >= player.frames.on_ground.len()
        || !player.frames.on_ground[frame - 1]
        || player.frames.on_ground[frame]
    {
        return false;
    }
    let prev = frame_state(player, liftoff_frame - 1);
    let curr = frame_state(player, liftoff_frame);
    dot(diff(curr.vel, prev.vel), up(prev.rot)) >= crate::consts::JUMP_LIFTOFF_MIN_UP_VEL_STEP
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
                out.extend(edges.iter().cloned().map(|edge| TimedSeededEdge {
                    event_frame_index: Some(edge.frame_index),
                    fit_liftoff_release: false,
                    edge,
                    tick_range,
                }));
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

fn first_jump_available(tracker: &CarTracker) -> bool {
    matches!(tracker.jump, JumpState::Idle)
        && matches!(
            tracker.contact,
            ContactState::Grounded { .. } | ContactState::Airborne { .. }
        )
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

fn ticks_since_tick(current_tick: u64, tick: u64) -> f32 {
    (current_tick.saturating_sub(tick) as f32) / 120.0
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

fn up(rot: RotationMatrix) -> [f32; 3] {
    [rot[0][2], rot[1][2], rot[2][2]]
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
    #[cfg(feature = "sim")]
    use std::collections::{BTreeMap, BTreeSet};

    #[cfg(feature = "sim")]
    const PRESS_BOUNDARY_TOLERANCE_FRAMES: u32 = 2;
    #[cfg(feature = "sim")]
    const FLIP_MATCH_TOLERANCE_INTERVALS: i32 = 1;
    #[cfg(feature = "sim")]
    const DIAG_SURFACE_FLOOR_Z: f32 = 40.0;
    #[cfg(feature = "sim")]
    const DIAG_SURFACE_CEILING_Z: f32 = 2044.0 - 40.0;
    #[cfg(feature = "sim")]
    const DIAG_SURFACE_SIDE_WALL_X: f32 = 4096.0 - 40.0;
    #[cfg(feature = "sim")]
    const DIAG_SURFACE_BACK_WALL_Y: f32 = 5120.0 - 40.0;
    #[cfg(feature = "sim")]
    const DIAG_SURFACE_CORNER_SUM: f32 = 8064.0 - 60.0;
    #[cfg(feature = "sim")]
    const DIAG_SURFACE_NEAR_UU: f32 = 256.0;
    #[cfg(feature = "sim")]
    const A3_TABLE_A_LIMIT: usize = 12;
    #[cfg(feature = "sim")]
    const A3_TABLE_B_LIMIT: usize = 6;
    #[cfg(feature = "sim")]
    const A5_LAG_LOOKAHEAD_FRAMES: u32 = 8;
    #[cfg(feature = "sim")]
    const A5_DODGE_ANG_DELTA: f32 = 0.5;
    #[cfg(feature = "sim")]
    const A5_BOUNDARY_WINDOW_FRAMES: u32 = 4;

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
        let state = car_state(player, 0, interval.tick_range.0, &tracker);
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
    fn liftoff_impulse_emits_unseeded_jump_press() {
        let start = base_state(false);
        let mut end = start;
        end.pos = [0.0, 0.0, 80.0];
        end.vel = [0.0, 0.0, crate::consts::JUMP_IMMEDIATE_FORCE + 20.0];
        let series = series_from_states(vec![start, end], vec![0.0, 1.0 / 30.0], vec![true, false]);
        let output = solve_series(
            &series,
            &EstimatorConfig {
                mode: Mode::Unseeded,
                ..default_estimator_config()
            },
        );
        assert!(press_liftoff(&series.players[0], 1));

        let press = output.timelines[0]
            .events
            .iter()
            .find(|event| matches!(event.kind, SolvedEventKind::JumpPress))
            .unwrap_or_else(|| {
                panic!(
                    "liftoff impulse should imply a first jump press, events={:?}, samples={:?}, segments={:?}",
                    output.timelines[0].events,
                    output.timelines[0].samples,
                    output.timelines[0].segments,
                )
            });
        assert_eq!(press.frame_index, 1);
        assert!(output.timelines[0].samples[0].jump.value);
    }

    #[test]
    fn drive_off_liftoff_keeps_first_jump_unused() {
        let mut start = base_state(false);
        start.vel = [300.0, 0.0, 40.0];
        let mut end = start;
        end.pos = [10.0, 0.0, 80.0];
        end.vel = [300.0, 0.0, 70.0];
        let series = series_from_states(vec![start, end], vec![0.0, 1.0 / 30.0], vec![true, false]);
        let segment = &crate::segment::segment_replay(&series).players[0].segments[0];
        let tracker = tracker_for_segment(&series.players[0], segment, 120.0);
        assert!(!press_liftoff(&series.players[0], 1));
        assert!(matches!(tracker.jump, JumpState::Idle));
        assert!(matches!(tracker.second, SecondAction::Unavailable));
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

    #[cfg(feature = "sim")]
    #[test]
    #[ignore = "set RLINPUT_DEV_SERIES_DIR to exported dev-set ReplaySeries JSON directory"]
    fn exported_dev_set_wp7c_unseeded_flip_taxonomy() {
        let dir = std::env::var("RLINPUT_DEV_SERIES_DIR")
            .expect("RLINPUT_DEV_SERIES_DIR should point to exported ReplaySeries JSONs");
        let replays = read_dev_series(&dir);
        assert_eq!(replays.len(), 10, "WP7c must run on all 10 dev replays");

        let mut pooled = Wp7cReplaySummary::default();
        let mut pooled_misses: BTreeMap<MissClass, usize> = BTreeMap::new();
        let mut pooled_hallucinations: Vec<HallucinationDiag> = Vec::new();
        let mut pooled_coverage: BTreeMap<&'static str, usize> = BTreeMap::new();
        let mut pooled_confidence = ConfidenceDiag::default();

        for (replay_name, series) in replays {
            let report = wp7c_replay_report(&replay_name, &series);
            pooled.add(&report.summary);
            pooled_confidence.add(&report.confidence);
            for miss in &report.misses {
                *pooled_misses.entry(miss.class).or_default() += 1;
            }
            for hallucination in &report.hallucinations {
                *pooled_coverage
                    .entry(hallucination.coverage_label)
                    .or_default() += 1;
            }
            pooled_hallucinations.extend(report.hallucinations.iter().cloned());

            println!(
                "wp7c_replay_summary,replay={},known_flips={},hits={},misses={},miss_recall={:.3},no_candidate={},illegal={},outscored_by_null={},outscored_by_event={},unscored={},press_known={},press_hits={},press_recall={:.3},hallucinations={}",
                report.replay,
                report.summary.known_flips,
                report.summary.flip_hits,
                report.summary.flip_misses,
                recall(report.summary.flip_hits, report.summary.known_flips),
                report.count_misses(MissClass::NoCandidate),
                report.count_misses(MissClass::Illegal),
                report.count_misses(MissClass::OutscoredByNull),
                report.count_misses(MissClass::OutscoredByEvent),
                report.count_misses(MissClass::Unscored),
                report.summary.press_known,
                report.summary.press_hits,
                recall(report.summary.press_hits, report.summary.press_known),
                report.hallucinations.len(),
            );
            println!(
                "wp7c_press_recall_fixed,replay={},known={},exact_hits={},exact_recall={:.3},coalesced_hits={},coalesced_recall={:.3},tolerance_frames={}",
                report.replay,
                report.summary.press_known,
                report.summary.press_exact_hits,
                recall(report.summary.press_exact_hits, report.summary.press_known),
                report.summary.press_hits,
                recall(report.summary.press_hits, report.summary.press_known),
                PRESS_BOUNDARY_TOLERANCE_FRAMES,
            );
            print_press_trace_summary(&report.replay, &report.press_traces);
            print_confidence_summary(&report.replay, &report.confidence);
            print_hallucination_summary(&report.replay, &report.hallucinations);
            for miss in &report.misses {
                println!(
                    "wp7c_miss_detail,replay={},player={},frames={}..{},span_frames={},span_ticks={},held_frames={},class={},reason={},winner={},margin={:.3},truth_press_window={},unseeded_press_window={},wrong_veto={},flags={:?},tracker={}",
                    report.replay,
                    miss.player_id,
                    miss.start_frame,
                    miss.end_frame,
                    miss.span_frames,
                    miss.span_ticks,
                    miss.held_frames,
                    miss.class.as_str(),
                    miss.reason,
                    miss.winner,
                    miss.margin.unwrap_or(f64::NAN),
                    miss.truth_press_in_window,
                    miss.unseeded_press_in_window,
                    miss.wrong_veto,
                    miss.flags,
                    miss.tracker_state,
                );
            }
            for hallucination in report.hallucinations.iter().take(50) {
                println!(
                    "wp7c_hallucination_sample,replay={},player={},frames={}..{},coverage={},dodge_vectors={},jump_edges={},dodge_edges={},double_jump_edges={},margin={:.3},pos_x={:.3},pos_y={:.3},pos_z={:.3},surface_margin={:.3},min_car_distance={:.3},planar_delta={:.3},vertical_delta={:.3},ang_delta={:.3},car_proximity={},flags={:?}",
                    report.replay,
                    hallucination.player_id,
                    hallucination.start_frame,
                    hallucination.end_frame,
                    hallucination.coverage_label,
                    hallucination.dodge_vector_events,
                    hallucination.jump_edges,
                    hallucination.dodge_edges,
                    hallucination.double_jump_edges,
                    hallucination.margin,
                    hallucination.pos[0],
                    hallucination.pos[1],
                    hallucination.pos[2],
                    hallucination.surface_margin,
                    hallucination.min_car_distance,
                    hallucination.planar_delta,
                    hallucination.vertical_delta,
                    hallucination.ang_delta,
                    hallucination.car_proximity,
                    hallucination.flags,
                );
            }
        }

        println!(
            "wp7c_pooled_miss_taxonomy,known_flips={},hits={},misses={},miss_recall={:.3},no_candidate={},illegal={},outscored_by_null={},outscored_by_event={},unscored={}",
            pooled.known_flips,
            pooled.flip_hits,
            pooled.flip_misses,
            recall(pooled.flip_hits, pooled.known_flips),
            pooled_misses
                .get(&MissClass::NoCandidate)
                .copied()
                .unwrap_or_default(),
            pooled_misses
                .get(&MissClass::Illegal)
                .copied()
                .unwrap_or_default(),
            pooled_misses
                .get(&MissClass::OutscoredByNull)
                .copied()
                .unwrap_or_default(),
            pooled_misses
                .get(&MissClass::OutscoredByEvent)
                .copied()
                .unwrap_or_default(),
            pooled_misses
                .get(&MissClass::Unscored)
                .copied()
                .unwrap_or_default(),
        );
        println!(
            "wp7c_pooled_press_recall,known={},exact_hits={},exact_recall={:.3},coalesced_hits={},coalesced_recall={:.3},tolerance_frames={}",
            pooled.press_known,
            pooled.press_exact_hits,
            recall(pooled.press_exact_hits, pooled.press_known),
            pooled.press_hits,
            recall(pooled.press_hits, pooled.press_known),
            PRESS_BOUNDARY_TOLERANCE_FRAMES,
        );
        print_confidence_summary("POOLED", &pooled_confidence);
        print_hallucination_summary("POOLED", &pooled_hallucinations);
        for (coverage, count) in pooled_coverage {
            println!(
                "wp7c_pooled_hallucination_coverage,coverage={coverage},count={count},share={:.3}",
                recall(count, pooled_hallucinations.len()),
            );
        }
    }

    #[cfg(feature = "sim")]
    #[test]
    #[ignore = "set RLINPUT_DEV_SERIES_DIR to exported dev-set ReplaySeries JSON directory"]
    fn exported_dev_set_wave_a4_flip_adjacency_probe() {
        let dir = std::env::var("RLINPUT_DEV_SERIES_DIR")
            .expect("RLINPUT_DEV_SERIES_DIR should point to exported dev-set ReplaySeries JSONs");
        let replays = read_dev_series(&dir);
        assert_eq!(replays.len(), 10, "A4 must run on all 10 dev replays");

        let mut pooled = AdjacencySummary::default();
        let mut by_bucket: BTreeMap<String, AdjacencySummary> = BTreeMap::new();

        for (replay, series) in replays {
            let known = coalesced_component_targets(&series, is_component_flip_edge, false);
            let solved = solved_flip_intervals(&solve_unseeded_reference(&series));
            let ordinals = coalesced_interval_ordinals(&series);
            let exact = match_flips(&known, &solved, &ordinals, FlipMatchTolerance::Exact);
            let exact_truth = matched_truth_keys(&exact);
            let exact_pred = matched_pred_keys(&exact);
            let misses: BTreeSet<_> = known
                .keys()
                .filter(|key| !exact_truth.contains(*key))
                .cloned()
                .collect();
            let hallucinations: BTreeSet<_> = solved
                .iter()
                .filter(|key| !exact_pred.contains(*key))
                .cloned()
                .collect();
            let miss_adjacent = misses
                .iter()
                .filter(|miss| {
                    hallucinations.iter().any(|hallucination| {
                        coalesced_interval_distance(miss, hallucination, &ordinals)
                            .is_some_and(|distance| distance.abs() == 1)
                    })
                })
                .count();
            let hallucination_adjacent = hallucinations
                .iter()
                .filter(|hallucination| {
                    misses.iter().any(|miss| {
                        coalesced_interval_distance(miss, hallucination, &ordinals)
                            .is_some_and(|distance| distance.abs() == 1)
                    })
                })
                .count();

            println!(
                "wave_a4_adjacency_cross_tab,replay={},build_bucket={},misses={},miss_adjacent_hallucination={},miss_adjacent_share={:.3},hallucinations={},hallucination_adjacent_miss={},hallucination_adjacent_share={:.3}",
                replay,
                series.build_bucket,
                misses.len(),
                miss_adjacent,
                recall(miss_adjacent, misses.len()),
                hallucinations.len(),
                hallucination_adjacent,
                recall(hallucination_adjacent, hallucinations.len()),
            );

            let interval_1_matches = match_flips(
                &known,
                &solved,
                &ordinals,
                FlipMatchTolerance::Interval(FLIP_MATCH_TOLERANCE_INTERVALS),
            );
            let frames_2_matches =
                match_flips(&known, &solved, &ordinals, FlipMatchTolerance::Frames(2));
            let frames_4_matches =
                match_flips(&known, &solved, &ordinals, FlipMatchTolerance::Frames(4));
            for (tolerance, matches) in [
                (FlipMatchTolerance::Exact, exact.clone()),
                (
                    FlipMatchTolerance::Interval(FLIP_MATCH_TOLERANCE_INTERVALS),
                    interval_1_matches.clone(),
                ),
                (FlipMatchTolerance::Frames(2), frames_2_matches.clone()),
                (FlipMatchTolerance::Frames(4), frames_4_matches.clone()),
            ] {
                println!(
                    "wave_a4_tolerance_curve,replay={},tolerance={},known_flips={},solved_flips={},matched={},recall={:.3},hallucinations={}",
                    replay,
                    tolerance.as_label(),
                    known.len(),
                    solved.len(),
                    matches.len(),
                    recall(matches.len(), known.len()),
                    solved.len().saturating_sub(matches.len()),
                );
            }

            let pairs = adjacency_pairs(&known, &misses, &hallucinations, &ordinals);
            let mut summary = AdjacencySummary::from_parts(
                known.len(),
                solved.len(),
                exact.len(),
                misses.len(),
                miss_adjacent,
                hallucinations.len(),
                hallucination_adjacent,
                &pairs,
            );
            summary.interval_1_matches = interval_1_matches.len();
            summary.frames_2_matches = frames_2_matches.len();
            summary.frames_4_matches = frames_4_matches.len();
            println!(
                "wave_a4_lag_distribution,replay={},build_bucket={},pairs={},offset_hist={},offset_p50={:.1},offset_p90={:.1}",
                replay,
                series.build_bucket,
                pairs.len(),
                frame_offset_histogram(&summary.frame_offsets),
                percentile_i32(summary.frame_offsets.clone(), 0.50),
                percentile_i32(summary.frame_offsets.clone(), 0.90),
            );

            pooled.add(&summary);
            by_bucket
                .entry(series.build_bucket.clone())
                .or_default()
                .add(&summary);
        }

        println!(
            "wave_a4_adjacency_cross_tab,replay=POOLED,build_bucket=ALL,misses={},miss_adjacent_hallucination={},miss_adjacent_share={:.3},hallucinations={},hallucination_adjacent_miss={},hallucination_adjacent_share={:.3}",
            pooled.misses,
            pooled.miss_adjacent,
            recall(pooled.miss_adjacent, pooled.misses),
            pooled.hallucinations,
            pooled.hallucination_adjacent,
            recall(pooled.hallucination_adjacent, pooled.hallucinations),
        );
        for tolerance in [
            FlipMatchTolerance::Exact,
            FlipMatchTolerance::Interval(1),
            FlipMatchTolerance::Frames(2),
            FlipMatchTolerance::Frames(4),
        ] {
            let matched = match tolerance {
                FlipMatchTolerance::Exact => pooled.exact_matches,
                FlipMatchTolerance::Interval(1) => pooled.interval_1_matches,
                FlipMatchTolerance::Frames(2) => pooled.frames_2_matches,
                FlipMatchTolerance::Frames(4) => pooled.frames_4_matches,
                _ => 0,
            };
            println!(
                "wave_a4_tolerance_curve,replay=POOLED,tolerance={},known_flips={},solved_flips={},matched={},recall={:.3},hallucinations={}",
                tolerance.as_label(),
                pooled.known,
                pooled.solved,
                matched,
                recall(matched, pooled.known),
                pooled.solved.saturating_sub(matched),
            );
        }
        println!(
            "wave_a4_lag_distribution,replay=POOLED,build_bucket=ALL,pairs={},offset_hist={},offset_p50={:.1},offset_p90={:.1}",
            pooled.frame_offsets.len(),
            frame_offset_histogram(&pooled.frame_offsets),
            percentile_i32(pooled.frame_offsets.clone(), 0.50),
            percentile_i32(pooled.frame_offsets.clone(), 0.90),
        );
        for (bucket, summary) in by_bucket {
            println!(
                "wave_a4_lag_distribution,replay=BUCKET,build_bucket={},pairs={},offset_hist={},offset_p50={:.1},offset_p90={:.1}",
                bucket,
                summary.frame_offsets.len(),
                frame_offset_histogram(&summary.frame_offsets),
                percentile_i32(summary.frame_offsets.clone(), 0.50),
                percentile_i32(summary.frame_offsets.clone(), 0.90),
            );
        }
    }

    #[cfg(feature = "sim")]
    #[test]
    #[ignore = "set RLINPUT_DEV_SERIES_DIR to exported dev-set ReplaySeries JSON directory"]
    fn exported_dev_set_wave_a5_three_cause_probe() {
        let dir = std::env::var("RLINPUT_DEV_SERIES_DIR")
            .expect("RLINPUT_DEV_SERIES_DIR should point to exported dev-set ReplaySeries JSONs");
        let replays = read_dev_series(&dir);
        assert_eq!(replays.len(), 10, "A5 must run on all 10 dev replays");

        let mut pooled = A5Summary::default();
        for (replay, series) in replays {
            let summary = a5_probe_replay(&replay, &series);
            print_a5_summary(&replay, &summary);
            pooled.add(&summary);
        }
        print_a5_summary("POOLED", &pooled);
    }

    #[cfg(feature = "sim")]
    #[test]
    #[ignore = "set RLINPUT_DEV_SERIES_DIR to exported dev-set ReplaySeries JSON directory"]
    fn exported_dev_set_wave_a3_flip_recall_microscope() {
        let dir = std::env::var("RLINPUT_DEV_SERIES_DIR")
            .expect("RLINPUT_DEV_SERIES_DIR should point to exported ReplaySeries JSONs");
        let replays = read_dev_series(&dir);
        assert_eq!(replays.len(), 10, "A3 must run on all 10 dev replays");

        let mut misses = Vec::new();
        for (replay_name, series) in replays {
            misses.extend(wave_a3_replay_misses(&replay_name, &series));
        }

        let no_candidate: Vec<_> = misses
            .iter()
            .filter(|miss| miss.class == MissClass::NoCandidate)
            .collect();
        let outscored_by_null: Vec<_> = misses
            .iter()
            .filter(|miss| miss.class == MissClass::OutscoredByNull)
            .collect();
        let table_a = stratified_a3_sample(&no_candidate, A3_TABLE_A_LIMIT);
        let table_b = stratified_a3_sample(&outscored_by_null, A3_TABLE_B_LIMIT);

        println!(
            "wave_a3_totals,no_candidate={},outscored_by_null={}",
            no_candidate.len(),
            outscored_by_null.len()
        );
        print_a3_failure_histogram("table_a_12", &table_a);
        print_a3_failure_histogram("all_no_candidate", &no_candidate);
        print_a3_table_a(&table_a);
        print_a3_table_b(&table_b);
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

    #[cfg(feature = "sim")]
    #[derive(Clone, Debug)]
    struct Wp7cReport {
        replay: String,
        summary: Wp7cReplaySummary,
        misses: Vec<MissDiag>,
        hallucinations: Vec<HallucinationDiag>,
        press_traces: Vec<PressTraceDiag>,
        confidence: ConfidenceDiag,
    }

    #[cfg(feature = "sim")]
    #[derive(Clone, Debug, Default)]
    struct Wp7cReplaySummary {
        known_flips: usize,
        flip_hits: usize,
        flip_misses: usize,
        press_known: usize,
        press_exact_hits: usize,
        press_hits: usize,
    }

    #[cfg(feature = "sim")]
    impl Wp7cReplaySummary {
        fn add(&mut self, other: &Self) {
            self.known_flips += other.known_flips;
            self.flip_hits += other.flip_hits;
            self.flip_misses += other.flip_misses;
            self.press_known += other.press_known;
            self.press_exact_hits += other.press_exact_hits;
            self.press_hits += other.press_hits;
        }
    }

    #[cfg(feature = "sim")]
    #[derive(Clone, Copy, Debug, PartialEq, Eq, PartialOrd, Ord)]
    enum MissClass {
        NoCandidate,
        Illegal,
        OutscoredByNull,
        OutscoredByEvent,
        Unscored,
    }

    #[cfg(feature = "sim")]
    impl MissClass {
        fn as_str(self) -> &'static str {
            match self {
                MissClass::NoCandidate => "NO_CANDIDATE",
                MissClass::Illegal => "ILLEGAL",
                MissClass::OutscoredByNull => "OUTSCORED_BY_NULL",
                MissClass::OutscoredByEvent => "OUTSCORED_BY_EVENT",
                MissClass::Unscored => "UNSCORED",
            }
        }
    }

    #[cfg(feature = "sim")]
    #[derive(Clone, Debug)]
    struct ComponentTarget {
        start_frame: u32,
        end_frame: u32,
        flags: AmbiguityFlags,
        held_frames: usize,
        span_frames: u32,
        span_ticks: u64,
        reached_scoring: bool,
        edge_frames: Vec<u32>,
    }

    #[cfg(feature = "sim")]
    #[derive(Clone, Debug)]
    struct MissDiag {
        player_id: String,
        start_frame: u32,
        end_frame: u32,
        span_frames: u32,
        span_ticks: u64,
        held_frames: usize,
        class: MissClass,
        reason: String,
        winner: &'static str,
        margin: Option<f64>,
        truth_press_in_window: bool,
        unseeded_press_in_window: bool,
        wrong_veto: bool,
        flags: AmbiguityFlags,
        tracker_state: String,
    }

    #[cfg(feature = "sim")]
    #[derive(Clone, Debug)]
    struct HallucinationDiag {
        player_id: String,
        start_frame: u32,
        end_frame: u32,
        coverage_label: &'static str,
        dodge_vector_events: usize,
        jump_edges: usize,
        dodge_edges: usize,
        double_jump_edges: usize,
        margin: f64,
        pos: [f32; 3],
        surface_margin: f32,
        min_car_distance: f32,
        planar_delta: f32,
        vertical_delta: f32,
        ang_delta: f32,
        car_proximity: bool,
        flags: AmbiguityFlags,
    }

    #[cfg(feature = "sim")]
    #[derive(Clone, Debug)]
    struct PressTraceDiag {
        player_id: String,
        start_frame: u32,
        end_frame: u32,
        injected_frames: Vec<u32>,
        raw_press_candidates: usize,
        legal_press_candidates: usize,
        selected: bool,
        winner: &'static str,
        rejection: &'static str,
        emitted_raw_frames: Vec<u32>,
        coalesced_hit: bool,
    }

    #[cfg(feature = "sim")]
    #[derive(Clone, Debug, Default)]
    struct ConfidenceDiag {
        sample_confidences: Vec<f32>,
        segment_confidences: Vec<f32>,
        event_confidences: Vec<f32>,
        sample_low_margin: usize,
        sample_long_gap: usize,
        sample_surface: usize,
        sample_car_or_collision: usize,
        event_low_margin: usize,
    }

    #[cfg(feature = "sim")]
    impl ConfidenceDiag {
        fn add(&mut self, other: &Self) {
            self.sample_confidences
                .extend(other.sample_confidences.iter().copied());
            self.segment_confidences
                .extend(other.segment_confidences.iter().copied());
            self.event_confidences
                .extend(other.event_confidences.iter().copied());
            self.sample_low_margin += other.sample_low_margin;
            self.sample_long_gap += other.sample_long_gap;
            self.sample_surface += other.sample_surface;
            self.sample_car_or_collision += other.sample_car_or_collision;
            self.event_low_margin += other.event_low_margin;
        }
    }

    #[cfg(feature = "sim")]
    #[derive(Clone, Debug)]
    struct ComponentCoverage {
        dodge_vector_events: usize,
        jump_edges: usize,
        dodge_edges: usize,
        double_jump_edges: usize,
    }

    #[cfg(feature = "sim")]
    impl ComponentCoverage {
        fn label(&self) -> &'static str {
            match (self.dodge_vector_events > 0, self.jump_edges > 0) {
                (true, true) => "full_component_stream",
                (false, true) => "no_dodge_vectors",
                (true, false) => "no_jump_edges",
                (false, false) => "absent_flip_and_jump",
            }
        }
    }

    #[cfg(feature = "sim")]
    #[derive(Clone, Debug)]
    struct CandidateGenerationDiag {
        null_fast_path: bool,
        null_energy: f64,
        null_gate_threshold: f32,
        seeded_edges_count: usize,
        long_gap: bool,
        kinematic_gate: KinematicGateDiag,
        kinematic_events: Vec<CandidateEvent>,
        raw_candidates: Vec<Candidate>,
        legal_candidates: Vec<Candidate>,
    }

    #[cfg(feature = "sim")]
    #[derive(Clone, Debug)]
    struct KinematicGateDiag {
        planar_delta: f32,
        vertical_delta: f32,
        ang_delta: f32,
        air_segment: bool,
        second_available: bool,
        double_jump_gate: bool,
        dodge_gate: bool,
        stall_gate: bool,
        gates: Vec<GateConjunctDiag>,
    }

    #[cfg(feature = "sim")]
    #[derive(Clone, Debug)]
    struct GateConjunctDiag {
        name: String,
        threshold: String,
        actual: String,
        passed: bool,
    }

    #[cfg(feature = "sim")]
    #[derive(Clone, Debug)]
    struct A3MissDiag {
        replay: String,
        player_id: String,
        start_frame: u32,
        end_frame: u32,
        span_frames: u32,
        span_ticks: u64,
        held_frames: usize,
        class: MissClass,
        reason: String,
        winner: &'static str,
        flags: AmbiguityFlags,
        tracker_state: String,
        observed: ObservedSpanDiag,
        truth: Option<ComponentTruthDiag>,
        gates: Vec<GateConjunctDiag>,
        failures: Vec<String>,
        legal_candidates: Vec<Candidate>,
        state_k: CarPhysState,
        observed_end: CarPhysState,
        ticks: u32,
        weights: FitWeights,
    }

    #[cfg(feature = "sim")]
    #[derive(Clone, Debug)]
    struct ObservedSpanDiag {
        ang_delta: f32,
        ang_axis: &'static str,
        planar_delta: f32,
        vertical_delta: f32,
        rotation_angle: f64,
        max_step_planar_delta: f32,
        max_step_ang_delta: f32,
    }

    #[cfg(feature = "sim")]
    #[derive(Clone, Debug)]
    struct ComponentTruthDiag {
        kind: &'static str,
        frame: u32,
        raw_vector: Option<[f32; 3]>,
        dir: Option<[f32; 2]>,
        tick_range: (u32, u32),
    }

    #[cfg(feature = "sim")]
    #[derive(Clone, Debug)]
    struct A3ScoredCandidate {
        candidate: Candidate,
        spec: String,
        energy: f64,
        delta_vs_null: f64,
        terms: [f64; 4],
    }

    #[cfg(feature = "sim")]
    type FlipKey = (String, u32);
    #[cfg(feature = "sim")]
    type FlipMatch = (FlipKey, FlipKey);

    #[cfg(feature = "sim")]
    #[derive(Clone, Copy)]
    enum FlipMatchTolerance {
        Exact,
        Interval(i32),
        Frames(u32),
    }

    #[cfg(feature = "sim")]
    impl FlipMatchTolerance {
        fn as_label(self) -> String {
            match self {
                FlipMatchTolerance::Exact => "exact".to_string(),
                FlipMatchTolerance::Interval(intervals) => format!("interval_{intervals}"),
                FlipMatchTolerance::Frames(frames) => format!("frames_{frames}"),
            }
        }
    }

    #[cfg(feature = "sim")]
    #[derive(Default)]
    struct AdjacencySummary {
        known: usize,
        solved: usize,
        exact_matches: usize,
        interval_1_matches: usize,
        frames_2_matches: usize,
        frames_4_matches: usize,
        misses: usize,
        miss_adjacent: usize,
        hallucinations: usize,
        hallucination_adjacent: usize,
        frame_offsets: Vec<i32>,
    }

    #[cfg(feature = "sim")]
    impl AdjacencySummary {
        #[allow(clippy::too_many_arguments)]
        fn from_parts(
            known: usize,
            solved: usize,
            exact_matches: usize,
            misses: usize,
            miss_adjacent: usize,
            hallucinations: usize,
            hallucination_adjacent: usize,
            pairs: &[FlipAdjacencyPair],
        ) -> Self {
            Self {
                known,
                solved,
                exact_matches,
                interval_1_matches: 0,
                frames_2_matches: 0,
                frames_4_matches: 0,
                misses,
                miss_adjacent,
                hallucinations,
                hallucination_adjacent,
                frame_offsets: pairs.iter().map(|pair| pair.frame_offset).collect(),
            }
        }

        fn add(&mut self, other: &Self) {
            self.known += other.known;
            self.solved += other.solved;
            self.exact_matches += other.exact_matches;
            self.interval_1_matches += other.interval_1_matches;
            self.frames_2_matches += other.frames_2_matches;
            self.frames_4_matches += other.frames_4_matches;
            self.misses += other.misses;
            self.miss_adjacent += other.miss_adjacent;
            self.hallucinations += other.hallucinations;
            self.hallucination_adjacent += other.hallucination_adjacent;
            self.frame_offsets
                .extend(other.frame_offsets.iter().copied());
        }
    }

    #[cfg(feature = "sim")]
    struct FlipAdjacencyPair {
        frame_offset: i32,
    }

    #[cfg(feature = "sim")]
    #[derive(Default)]
    struct A5Summary {
        scoped_misses: usize,
        no_candidate: usize,
        outscored_by_null: usize,
        lag_scanned: usize,
        lag_no_effect: usize,
        lag_effect_offsets: Vec<i32>,
        lag_fresh: usize,
        lag_held: usize,
        lag_solved_at_effect_interval: usize,
        cascade_total: usize,
        cascade_real_prior: usize,
        cascade_hallucinated_prior: usize,
        cascade_expired_timeout: usize,
        cascade_unknown: usize,
        cascade_liftoff_tick_zero: usize,
        cascade_hallucination_causes: BTreeMap<String, usize>,
        segment_total: usize,
        segment_surface_margins: Vec<f64>,
        segment_boundary_offsets: Vec<i32>,
        segment_after_raw_liftoff: usize,
        segment_before_raw_liftoff: usize,
        segment_far_from_liftoff: usize,
        overlap: BTreeMap<(bool, bool, bool), usize>,
    }

    #[cfg(feature = "sim")]
    impl A5Summary {
        fn add(&mut self, other: &Self) {
            self.scoped_misses += other.scoped_misses;
            self.no_candidate += other.no_candidate;
            self.outscored_by_null += other.outscored_by_null;
            self.lag_scanned += other.lag_scanned;
            self.lag_no_effect += other.lag_no_effect;
            self.lag_effect_offsets
                .extend(other.lag_effect_offsets.iter().copied());
            self.lag_fresh += other.lag_fresh;
            self.lag_held += other.lag_held;
            self.lag_solved_at_effect_interval += other.lag_solved_at_effect_interval;
            self.cascade_total += other.cascade_total;
            self.cascade_real_prior += other.cascade_real_prior;
            self.cascade_hallucinated_prior += other.cascade_hallucinated_prior;
            self.cascade_expired_timeout += other.cascade_expired_timeout;
            self.cascade_unknown += other.cascade_unknown;
            self.cascade_liftoff_tick_zero += other.cascade_liftoff_tick_zero;
            for (key, count) in &other.cascade_hallucination_causes {
                *self
                    .cascade_hallucination_causes
                    .entry(key.clone())
                    .or_default() += count;
            }
            self.segment_total += other.segment_total;
            self.segment_surface_margins
                .extend(other.segment_surface_margins.iter().copied());
            self.segment_boundary_offsets
                .extend(other.segment_boundary_offsets.iter().copied());
            self.segment_after_raw_liftoff += other.segment_after_raw_liftoff;
            self.segment_before_raw_liftoff += other.segment_before_raw_liftoff;
            self.segment_far_from_liftoff += other.segment_far_from_liftoff;
            for (key, count) in &other.overlap {
                *self.overlap.entry(*key).or_default() += count;
            }
        }
    }

    #[cfg(feature = "sim")]
    struct A5LagDiag {
        offset: Option<i32>,
        fresh: bool,
        solved_at_effect_interval: bool,
    }

    #[cfg(feature = "sim")]
    enum A5CascadeClass {
        RealPrior,
        HallucinatedPrior(String),
        ExpiredTimeout,
        Unknown,
    }

    #[cfg(feature = "sim")]
    fn read_dev_series(dir: &str) -> Vec<(String, ReplaySeries)> {
        let mut paths: Vec<_> = std::fs::read_dir(dir)
            .expect("dev series dir should read")
            .map(|entry| entry.expect("entry should read").path())
            .filter(|path| path.extension().and_then(|ext| ext.to_str()) == Some("json"))
            .collect();
        paths.sort();
        paths
            .into_iter()
            .map(|path| {
                let replay = path
                    .file_stem()
                    .and_then(|stem| stem.to_str())
                    .expect("json filename should be utf8")
                    .to_string();
                let file = std::fs::File::open(&path).expect("fixture should open");
                let series = serde_json::from_reader(file).expect("fixture should parse");
                (replay, series)
            })
            .collect()
    }

    #[cfg(feature = "sim")]
    fn solve_unseeded_reference(series: &ReplaySeries) -> SolveOutput {
        let mut config = default_estimator_config();
        config.mode = Mode::Unseeded;
        config.engine = EnginePreference::PreferReference;
        solve_series(series, &config)
    }

    #[cfg(feature = "sim")]
    fn a5_probe_replay(replay: &str, series: &ReplaySeries) -> A5Summary {
        let misses = wave_a3_replay_misses(replay, series);
        let output = solve_unseeded_reference(series);
        let solved_flips = solved_flip_intervals(&output);
        let solved_events = solved_flip_events_by_player(&output);
        let known_flips = coalesced_component_targets(series, is_component_flip_edge, false);
        let ordinals = coalesced_interval_ordinals(series);
        let segmentation = crate::segment::segment_replay(series);
        let freshness = freshness_by_player(series, &segmentation);
        let scoring_ends = scoring_end_by_player(series, &segmentation, &freshness);
        let mut summary = A5Summary::default();

        for miss in &misses {
            summary.scoped_misses += 1;
            match miss.class {
                MissClass::NoCandidate => summary.no_candidate += 1,
                MissClass::OutscoredByNull => summary.outscored_by_null += 1,
                MissClass::Illegal | MissClass::OutscoredByEvent | MissClass::Unscored => {}
            }

            let lag = a5_lag_diag(miss, series, &freshness, &scoring_ends, &solved_flips);
            let lagged = lag
                .as_ref()
                .and_then(|diag| diag.offset)
                .is_some_and(|offset| offset > 0);
            if let Some(lag) = lag {
                summary.lag_scanned += 1;
                if let Some(offset) = lag.offset {
                    summary.lag_effect_offsets.push(offset);
                    if lag.fresh {
                        summary.lag_fresh += 1;
                    } else {
                        summary.lag_held += 1;
                    }
                    if lag.solved_at_effect_interval {
                        summary.lag_solved_at_effect_interval += 1;
                    }
                } else {
                    summary.lag_no_effect += 1;
                }
            }

            let cascade = miss
                .failures
                .iter()
                .any(|failure| failure == "kinematic.second_available");
            if cascade {
                summary.cascade_total += 1;
                if miss.tracker_state.contains("liftoff_tick: 0") {
                    summary.cascade_liftoff_tick_zero += 1;
                }
                match a5_cascade_class(miss, &solved_events, &known_flips, &ordinals) {
                    A5CascadeClass::RealPrior => summary.cascade_real_prior += 1,
                    A5CascadeClass::HallucinatedPrior(key) => {
                        summary.cascade_hallucinated_prior += 1;
                        *summary.cascade_hallucination_causes.entry(key).or_default() += 1;
                    }
                    A5CascadeClass::ExpiredTimeout => summary.cascade_expired_timeout += 1,
                    A5CascadeClass::Unknown => summary.cascade_unknown += 1,
                }
            }

            let segment = miss
                .failures
                .iter()
                .any(|failure| failure == "kinematic.segment_is_air");
            if segment {
                summary.segment_total += 1;
                if let Some(diag) = a5_segment_diag(miss, series, &segmentation) {
                    summary
                        .segment_surface_margins
                        .push(f64::from(diag.surface_margin));
                    if let Some(offset) = diag.segment_boundary_offset {
                        summary.segment_boundary_offsets.push(offset);
                    }
                    match diag.raw_liftoff_offset {
                        Some(offset)
                            if offset <= 0 && offset.abs() <= A5_BOUNDARY_WINDOW_FRAMES as i32 =>
                        {
                            summary.segment_after_raw_liftoff += 1;
                        }
                        Some(offset)
                            if offset > 0 && offset <= A5_BOUNDARY_WINDOW_FRAMES as i32 =>
                        {
                            summary.segment_before_raw_liftoff += 1;
                        }
                        _ => summary.segment_far_from_liftoff += 1,
                    }
                }
            }

            *summary
                .overlap
                .entry((lagged, cascade, segment))
                .or_default() += 1;
        }

        summary
    }

    #[cfg(feature = "sim")]
    fn freshness_by_player(
        series: &ReplaySeries,
        segmentation: &crate::segment::SegmentationOutput,
    ) -> BTreeMap<String, KinematicFreshness> {
        let mut out = BTreeMap::new();
        for segmented_player in &segmentation.players {
            let Some(player) = series
                .players
                .iter()
                .find(|player| player.player_id == segmented_player.player_id)
            else {
                continue;
            };
            let mut freshness = KinematicFreshness::from_frames(&player.frames);
            for segment in &segmented_player.segments {
                freshness.mark_fresh(segment.frame_span.0);
            }
            out.insert(player.player_id.clone(), freshness);
        }
        out
    }

    #[cfg(feature = "sim")]
    fn scoring_end_by_player(
        series: &ReplaySeries,
        segmentation: &crate::segment::SegmentationOutput,
        freshness: &BTreeMap<String, KinematicFreshness>,
    ) -> BTreeMap<String, BTreeMap<u32, u32>> {
        let mut out = BTreeMap::new();
        for segmented_player in &segmentation.players {
            let Some(player) = series
                .players
                .iter()
                .find(|player| player.player_id == segmented_player.player_id)
            else {
                continue;
            };
            let Some(freshness) = freshness.get(&player.player_id) else {
                continue;
            };
            let mut frames = BTreeMap::new();
            for segment in &segmented_player.segments {
                for scoring in fresh_scoring_intervals(segment, freshness) {
                    for frame in
                        scoring.start_frame.saturating_add(1)..=scoring.interval.frame_index
                    {
                        frames.insert(frame, scoring.interval.frame_index);
                    }
                }
            }
            out.insert(player.player_id.clone(), frames);
        }
        out
    }

    #[cfg(feature = "sim")]
    fn a5_lag_diag(
        miss: &A3MissDiag,
        series: &ReplaySeries,
        freshness: &BTreeMap<String, KinematicFreshness>,
        scoring_ends: &BTreeMap<String, BTreeMap<u32, u32>>,
        solved_flips: &HashSet<(String, u32)>,
    ) -> Option<A5LagDiag> {
        let player = series
            .players
            .iter()
            .find(|player| player.player_id == miss.player_id)?;
        let truth_frame = miss
            .truth
            .as_ref()
            .map(|truth| truth.frame)
            .unwrap_or(miss.end_frame);
        let max_frame = player.frames.ang_vel.len().saturating_sub(1) as u32;
        let search_end = truth_frame
            .saturating_add(A5_LAG_LOOKAHEAD_FRAMES)
            .min(max_frame);
        let effect_frame = (truth_frame.saturating_add(1)..=search_end).find(|frame| {
            let prev = frame_state(player, frame.saturating_sub(1));
            let curr = frame_state(player, *frame);
            norm(diff(curr.ang_vel, prev.ang_vel)) >= A5_DODGE_ANG_DELTA
        });
        let Some(effect_frame) = effect_frame else {
            return Some(A5LagDiag {
                offset: None,
                fresh: false,
                solved_at_effect_interval: false,
            });
        };
        let interval_end = scoring_ends
            .get(&miss.player_id)
            .and_then(|frames| frames.get(&effect_frame))
            .copied()
            .unwrap_or(effect_frame);
        Some(A5LagDiag {
            offset: Some(effect_frame as i32 - truth_frame as i32),
            fresh: freshness
                .get(&miss.player_id)
                .is_some_and(|freshness| freshness.is_fresh(effect_frame)),
            solved_at_effect_interval: solved_flips
                .contains(&(miss.player_id.clone(), interval_end)),
        })
    }

    #[cfg(feature = "sim")]
    fn solved_flip_events_by_player(output: &SolveOutput) -> BTreeMap<String, Vec<u32>> {
        let mut out: BTreeMap<String, Vec<u32>> = BTreeMap::new();
        for timeline in &output.timelines {
            for event in &timeline.events {
                if matches!(
                    event.kind,
                    SolvedEventKind::Dodge { .. }
                        | SolvedEventKind::DoubleJump
                        | SolvedEventKind::Stall
                ) {
                    out.entry(timeline.player_id.clone())
                        .or_default()
                        .push(event.frame_index);
                }
            }
        }
        for frames in out.values_mut() {
            frames.sort_unstable();
        }
        out
    }

    #[cfg(feature = "sim")]
    fn a5_cascade_class(
        miss: &A3MissDiag,
        solved_events: &BTreeMap<String, Vec<u32>>,
        known_flips: &BTreeMap<FlipKey, ComponentTarget>,
        ordinals: &BTreeMap<String, BTreeMap<u32, i32>>,
    ) -> A5CascadeClass {
        if miss.tracker_state.contains("Expired") {
            return A5CascadeClass::ExpiredTimeout;
        }
        if !(miss.tracker_state.contains("UsedDodge")
            || miss.tracker_state.contains("UsedDoubleJump"))
        {
            return A5CascadeClass::Unknown;
        }
        let Some(frame) = solved_events
            .get(&miss.player_id)
            .and_then(|frames| frames.iter().rev().find(|frame| **frame < miss.end_frame))
            .copied()
        else {
            return A5CascadeClass::Unknown;
        };
        let pred = (miss.player_id.clone(), frame);
        let real = known_flips.contains_key(&pred)
            || known_flips.keys().any(|truth| {
                flip_match_distance(truth, &pred, ordinals, FlipMatchTolerance::Frames(4)).is_some()
            });
        if real {
            A5CascadeClass::RealPrior
        } else {
            A5CascadeClass::HallucinatedPrior(format!("{}@{}", miss.player_id, frame))
        }
    }

    #[cfg(feature = "sim")]
    struct A5SegmentDiag {
        surface_margin: f32,
        segment_boundary_offset: Option<i32>,
        raw_liftoff_offset: Option<i32>,
    }

    #[cfg(feature = "sim")]
    fn a5_segment_diag(
        miss: &A3MissDiag,
        series: &ReplaySeries,
        segmentation: &crate::segment::SegmentationOutput,
    ) -> Option<A5SegmentDiag> {
        let player = series
            .players
            .iter()
            .find(|player| player.player_id == miss.player_id)?;
        let truth_frame = miss
            .truth
            .as_ref()
            .map(|truth| truth.frame)
            .unwrap_or(miss.end_frame);
        let pos = player.frames.pos.get(truth_frame as usize).copied()?;
        let segmented_player = segmentation
            .players
            .iter()
            .find(|player| player.player_id == miss.player_id)?;
        Some(A5SegmentDiag {
            surface_margin: nearest_arena_surface_margin(pos),
            segment_boundary_offset: nearest_air_boundary_offset(segmented_player, truth_frame),
            raw_liftoff_offset: nearest_raw_liftoff_offset(player, truth_frame),
        })
    }

    #[cfg(feature = "sim")]
    fn nearest_air_boundary_offset(
        segmented_player: &crate::segment::PlayerSegmentation,
        frame: u32,
    ) -> Option<i32> {
        segmented_player
            .segments
            .iter()
            .filter(|segment| segment.kind == SegmentKind::Air)
            .map(|segment| segment.frame_span.0 as i32 - frame as i32)
            .min_by_key(|offset| offset.abs())
    }

    #[cfg(feature = "sim")]
    fn nearest_raw_liftoff_offset(player: &PlayerSeries, frame: u32) -> Option<i32> {
        (1..player.frames.on_ground.len())
            .filter(|idx| player.frames.on_ground[idx - 1] && !player.frames.on_ground[*idx])
            .map(|idx| idx as i32 - frame as i32)
            .min_by_key(|offset| offset.abs())
    }

    #[cfg(feature = "sim")]
    fn print_a5_summary(replay: &str, summary: &A5Summary) {
        println!(
            "wave_a5_scope,replay={replay},scoped_misses={},no_candidate={},outscored_by_null={}",
            summary.scoped_misses, summary.no_candidate, summary.outscored_by_null
        );
        println!(
            "wave_a5_lag_summary,replay={replay},scanned={},effect_found={},no_effect={},offset_hist={},fresh={},held={},solved_at_effect_interval={}",
            summary.lag_scanned,
            summary.lag_effect_offsets.len(),
            summary.lag_no_effect,
            hist_i32(&summary.lag_effect_offsets),
            summary.lag_fresh,
            summary.lag_held,
            summary.lag_solved_at_effect_interval,
        );
        println!(
            "wave_a5_cascade_summary,replay={replay},second_available_fail={},real_prior={},hallucinated_prior={},expired_timeout={},unknown={},liftoff_tick_zero={},hallucination_causes={},hallucination_downstream_misses={}",
            summary.cascade_total,
            summary.cascade_real_prior,
            summary.cascade_hallucinated_prior,
            summary.cascade_expired_timeout,
            summary.cascade_unknown,
            summary.cascade_liftoff_tick_zero,
            summary.cascade_hallucination_causes.len(),
            summary.cascade_hallucination_causes.values().sum::<usize>(),
        );
        for (idx, (cause, count)) in summary
            .cascade_hallucination_causes
            .iter()
            .collect::<Vec<_>>()
            .into_iter()
            .take(12)
            .enumerate()
        {
            println!(
                "wave_a5_cascade_hallucination_cause,replay={replay},rank={},event={},downstream_misses={}",
                idx + 1,
                cause,
                count
            );
        }
        println!(
            "wave_a5_segment_summary,replay={replay},segment_air_fail={},surface_p10={:.3},surface_p50={:.3},surface_p90={:.3},boundary_hist={},after_raw_liftoff_within_{}f={},before_raw_liftoff_within_{}f={},far_from_raw_liftoff={}",
            summary.segment_total,
            percentile(summary.segment_surface_margins.clone(), 0.10),
            percentile(summary.segment_surface_margins.clone(), 0.50),
            percentile(summary.segment_surface_margins.clone(), 0.90),
            hist_i32(&summary.segment_boundary_offsets),
            A5_BOUNDARY_WINDOW_FRAMES,
            summary.segment_after_raw_liftoff,
            A5_BOUNDARY_WINDOW_FRAMES,
            summary.segment_before_raw_liftoff,
            summary.segment_far_from_liftoff,
        );
        for lag in [false, true] {
            for cascade in [false, true] {
                for segment in [false, true] {
                    let count = summary
                        .overlap
                        .get(&(lag, cascade, segment))
                        .copied()
                        .unwrap_or_default();
                    println!(
                        "wave_a5_overlap,replay={replay},lag={lag},cascade={cascade},segment={segment},count={count}"
                    );
                }
            }
        }
    }

    #[cfg(feature = "sim")]
    fn hist_i32(values: &[i32]) -> String {
        let mut hist = BTreeMap::new();
        for value in values {
            *hist.entry(*value).or_insert(0usize) += 1;
        }
        if hist.is_empty() {
            return "none".to_string();
        }
        hist.into_iter()
            .map(|(value, count)| format!("{value}:{count}"))
            .collect::<Vec<_>>()
            .join("|")
    }

    #[cfg(feature = "sim")]
    fn coalesced_interval_ordinals(series: &ReplaySeries) -> BTreeMap<String, BTreeMap<u32, i32>> {
        let segmentation = crate::segment::segment_replay(series);
        let mut out = BTreeMap::new();
        for segmented_player in &segmentation.players {
            let Some(player) = series
                .players
                .iter()
                .find(|player| player.player_id == segmented_player.player_id)
            else {
                continue;
            };
            let mut freshness = KinematicFreshness::from_frames(&player.frames);
            for segment in &segmented_player.segments {
                freshness.mark_fresh(segment.frame_span.0);
            }
            let mut ordinals = BTreeMap::new();
            let mut ordinal = 0;
            for segment in &segmented_player.segments {
                for scoring in fresh_scoring_intervals(segment, &freshness) {
                    ordinals.insert(scoring.interval.frame_index, ordinal);
                    ordinal += 1;
                }
            }
            out.insert(player.player_id.clone(), ordinals);
        }
        out
    }

    #[cfg(feature = "sim")]
    fn match_flips(
        truth: &BTreeMap<FlipKey, ComponentTarget>,
        predicted: &HashSet<FlipKey>,
        ordinals: &BTreeMap<String, BTreeMap<u32, i32>>,
        tolerance: FlipMatchTolerance,
    ) -> Vec<FlipMatch> {
        let mut unmatched: BTreeSet<_> = truth.keys().cloned().collect();
        let mut predictions: Vec<_> = predicted.iter().cloned().collect();
        predictions.sort();
        let mut matches = Vec::new();
        for pred in predictions {
            let Some(best) = unmatched
                .iter()
                .filter(|candidate| {
                    flip_match_distance(candidate, &pred, ordinals, tolerance).is_some()
                })
                .min_by_key(|candidate| {
                    let distance = flip_match_distance(candidate, &pred, ordinals, tolerance)
                        .unwrap_or(i32::MAX);
                    (distance.abs(), candidate.1.abs_diff(pred.1), candidate.1)
                })
                .cloned()
            else {
                continue;
            };
            unmatched.remove(&best);
            matches.push((best, pred));
        }
        matches
    }

    #[cfg(feature = "sim")]
    fn flip_match_distance(
        truth: &FlipKey,
        predicted: &FlipKey,
        ordinals: &BTreeMap<String, BTreeMap<u32, i32>>,
        tolerance: FlipMatchTolerance,
    ) -> Option<i32> {
        if truth.0 != predicted.0 {
            return None;
        }
        match tolerance {
            FlipMatchTolerance::Exact => (truth.1 == predicted.1).then_some(0),
            FlipMatchTolerance::Interval(intervals) => {
                let distance = coalesced_interval_distance(truth, predicted, ordinals)?;
                (distance.abs() <= intervals).then_some(distance)
            }
            FlipMatchTolerance::Frames(frames) => {
                let distance = predicted.1 as i32 - truth.1 as i32;
                (truth.1.abs_diff(predicted.1) <= frames).then_some(distance)
            }
        }
    }

    #[cfg(feature = "sim")]
    fn coalesced_interval_distance(
        truth: &FlipKey,
        predicted: &FlipKey,
        ordinals: &BTreeMap<String, BTreeMap<u32, i32>>,
    ) -> Option<i32> {
        if truth.0 != predicted.0 {
            return None;
        }
        let player_ordinals = ordinals.get(&truth.0)?;
        Some(player_ordinals.get(&predicted.1)? - player_ordinals.get(&truth.1)?)
    }

    #[cfg(feature = "sim")]
    fn matched_truth_keys(matches: &[FlipMatch]) -> BTreeSet<FlipKey> {
        matches.iter().map(|(truth, _pred)| truth.clone()).collect()
    }

    #[cfg(feature = "sim")]
    fn matched_pred_keys(matches: &[FlipMatch]) -> BTreeSet<FlipKey> {
        matches.iter().map(|(_truth, pred)| pred.clone()).collect()
    }

    #[cfg(feature = "sim")]
    fn adjacency_pairs(
        known: &BTreeMap<FlipKey, ComponentTarget>,
        misses: &BTreeSet<FlipKey>,
        hallucinations: &BTreeSet<FlipKey>,
        ordinals: &BTreeMap<String, BTreeMap<u32, i32>>,
    ) -> Vec<FlipAdjacencyPair> {
        let mut unused_hallucinations = hallucinations.clone();
        let mut pairs = Vec::new();
        for miss in misses {
            let Some(hallucination) = unused_hallucinations
                .iter()
                .filter(|hallucination| {
                    coalesced_interval_distance(miss, hallucination, ordinals)
                        .is_some_and(|distance| distance.abs() == 1)
                })
                .min_by_key(|hallucination| miss.1.abs_diff(hallucination.1))
                .cloned()
            else {
                continue;
            };
            unused_hallucinations.remove(&hallucination);
            let component_frame = known
                .get(miss)
                .and_then(|target| {
                    target
                        .edge_frames
                        .iter()
                        .min_by_key(|frame| frame.abs_diff(hallucination.1))
                        .copied()
                })
                .unwrap_or(miss.1);
            pairs.push(FlipAdjacencyPair {
                frame_offset: hallucination.1 as i32 - component_frame as i32,
            });
        }
        pairs
    }

    #[cfg(feature = "sim")]
    fn frame_offset_histogram(offsets: &[i32]) -> String {
        let mut hist = BTreeMap::new();
        for offset in offsets {
            *hist.entry(*offset).or_insert(0usize) += 1;
        }
        hist.into_iter()
            .map(|(offset, count)| format!("{offset}:{count}"))
            .collect::<Vec<_>>()
            .join("|")
    }

    #[cfg(feature = "sim")]
    fn percentile_i32(mut values: Vec<i32>, percentile_value: f64) -> f64 {
        if values.is_empty() {
            return f64::NAN;
        }
        values.sort_unstable();
        let idx = ((values.len() - 1) as f64 * percentile_value).round() as usize;
        f64::from(values[idx])
    }

    #[cfg(feature = "sim")]
    fn wp7c_replay_report(replay: &str, series: &ReplaySeries) -> Wp7cReport {
        let known_flips = coalesced_component_targets(series, is_component_flip_edge, false);
        let known_presses =
            coalesced_component_targets(series, is_component_jump_press_edge, false);
        let component_press_frames = component_jump_press_frames(series);
        let component_coverage = component_coverage_by_player(series);

        let mut config = default_estimator_config();
        config.mode = Mode::Unseeded;
        config.engine = EnginePreference::PreferReference;
        let masked = masked_series_for_solving(series, &config);
        let first = solve_pass(&masked, &config, &[], true);
        let retro_splits = first.retro_splits.clone();
        let output = if retro_splits.is_empty() {
            first.output
        } else {
            solve_pass(&masked, &config, &retro_splits, false).output
        };
        let solved_flips = solved_flip_intervals(&output);
        let solved_jump_presses =
            solved_event_frame_sets(&output, |kind| matches!(kind, SolvedEventKind::JumpPress));
        let solved_jump_press_targets = coalesced_solved_press_targets(
            &known_presses,
            &output,
            |kind| matches!(kind, SolvedEventKind::JumpPress),
            PRESS_BOUNDARY_TOLERANCE_FRAMES,
        );

        let summary = Wp7cReplaySummary {
            known_flips: known_flips.len(),
            flip_hits: known_flips
                .keys()
                .filter(|key| solved_flips.contains(*key))
                .count(),
            flip_misses: known_flips
                .keys()
                .filter(|key| !solved_flips.contains(*key))
                .count(),
            press_known: known_presses.len(),
            press_exact_hits: known_presses
                .keys()
                .filter(|key| solved_jump_presses.contains_key(*key))
                .count(),
            press_hits: known_presses
                .keys()
                .filter(|key| solved_jump_press_targets.contains_key(*key))
                .count(),
        };

        let (mut misses, hallucinations, press_traces) = wp7c_interval_diagnostics(
            series,
            &masked,
            &config,
            &retro_splits,
            &known_flips,
            &known_presses,
            &solved_flips,
            &solved_jump_presses,
            &solved_jump_press_targets,
            &component_press_frames,
            &component_coverage,
        );
        let seen_misses: BTreeSet<_> = misses
            .iter()
            .map(|miss| (miss.player_id.clone(), miss.end_frame))
            .collect();
        for ((player_id, end_frame), target) in &known_flips {
            if solved_flips.contains(&(player_id.clone(), *end_frame))
                || seen_misses.contains(&(player_id.clone(), *end_frame))
            {
                continue;
            }
            misses.push(unscored_miss(
                player_id,
                target,
                &component_press_frames,
                &solved_jump_presses,
            ));
        }

        Wp7cReport {
            replay: replay.to_string(),
            summary,
            misses,
            hallucinations,
            press_traces,
            confidence: confidence_diag(&output),
        }
    }

    #[cfg(feature = "sim")]
    impl Wp7cReport {
        fn count_misses(&self, class: MissClass) -> usize {
            self.misses
                .iter()
                .filter(|miss| miss.class == class)
                .count()
        }
    }

    #[cfg(feature = "sim")]
    #[allow(clippy::too_many_arguments)]
    fn wp7c_interval_diagnostics(
        original: &ReplaySeries,
        masked: &ReplaySeries,
        config: &EstimatorConfig,
        retro_splits: &[RetroactiveSplit],
        known_flips: &BTreeMap<(String, u32), ComponentTarget>,
        known_presses: &BTreeMap<(String, u32), ComponentTarget>,
        solved_flips: &HashSet<(String, u32)>,
        solved_jump_presses: &BTreeMap<(String, u32), ()>,
        solved_jump_press_targets: &BTreeMap<(String, u32), Vec<u32>>,
        component_press_frames: &BTreeMap<String, BTreeSet<u32>>,
        coverage: &BTreeMap<String, ComponentCoverage>,
    ) -> (Vec<MissDiag>, Vec<HallucinationDiag>, Vec<PressTraceDiag>) {
        let segmentation = segment_replay_with_splits_and_confidences(
            masked,
            retro_splits,
            CONFIDENT_SEGMENT_THRESHOLD,
            |_player_id, _segment| None,
        );
        let mut misses = Vec::new();
        let mut hallucinations = Vec::new();
        let mut press_traces = BTreeMap::new();
        let mut seen_press_targets = BTreeSet::new();

        for segmented_player in &segmentation.players {
            let Some(player_index) = masked
                .players
                .iter()
                .position(|player| player.player_id == segmented_player.player_id)
            else {
                continue;
            };
            let player = &masked.players[player_index];
            let original_player = &original.players[player_index];
            let hints = SeededHints::new(&player.component);
            let mut reference = ReferenceScorer::new();
            let mut freshness = KinematicFreshness::from_frames(&player.frames);
            for segment in &segmented_player.segments {
                freshness.mark_fresh(segment.frame_span.0);
            }

            for segment in &segmented_player.segments {
                let tracker = tracker_for_segment(player, segment, masked.tick_rate);
                let mut branching = BranchingTracker::new(tracker.clone());
                for scoring in fresh_scoring_intervals(segment, &freshness) {
                    let start_frame = scoring.start_frame;
                    let interval = &scoring.interval;
                    let end_frame = interval.frame_index;
                    let key = (player.player_id.clone(), end_frame);
                    if frame_out_of_bounds(player, start_frame)
                        || frame_out_of_bounds(player, end_frame)
                    {
                        continue;
                    }
                    let interval_tracker = branching.best_tracker().clone();
                    let ticks = interval_ticks(interval);
                    let state_k = car_state(
                        player,
                        start_frame,
                        interval.tick_range.0,
                        &interval_tracker,
                    );
                    let observed_end =
                        car_state(player, end_frame, interval.tick_range.1, &interval_tracker);
                    let base_controls = solve_controls(
                        player,
                        start_frame,
                        end_frame,
                        interval,
                        &interval_tracker,
                        config,
                    );
                    let seeded_edges = edges_for_interval_with_implied_liftoff(
                        player,
                        &hints,
                        segment,
                        start_frame,
                        end_frame,
                        interval,
                        config,
                    );
                    let injected_press_frames: Vec<_> = seeded_edges
                        .iter()
                        .filter(|edge| timed_edge_is_jump_press(edge))
                        .map(|edge| edge.edge.frame_index)
                        .collect();
                    let generation = generate_candidates_for_wp7c_diag(
                        &state_k,
                        &observed_end,
                        &interval_tracker,
                        interval,
                        base_controls,
                        seeded_edges,
                        config,
                        segment.kind,
                    );
                    let (mut scored, _portable_best, _reference_best) = score_candidates_for_diag(
                        &state_k,
                        &observed_end,
                        ticks,
                        &generation.legal_candidates,
                        config,
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

                    if let Some(target) = known_flips.get(&key) {
                        if !solved_flips.contains(&key) {
                            misses.push(classify_miss(
                                player,
                                target,
                                &generation,
                                &scored,
                                &interval_tracker,
                                component_press_frames,
                                solved_jump_presses,
                            ));
                        }
                    } else if solved_flips.contains(&key)
                        && scored
                            .first()
                            .is_some_and(|item| candidate_has_flip(&item.candidate))
                    {
                        let null_energy = scored
                            .iter()
                            .find(|item| item.candidate.is_null())
                            .map(|item| item.energy)
                            .unwrap_or(f64::NAN);
                        let best_flip = scored
                            .iter()
                            .filter(|item| candidate_has_flip(&item.candidate))
                            .min_by(|a, b| a.energy.total_cmp(&b.energy));
                        if let (Some(best_flip), Some(player_coverage)) =
                            (best_flip, coverage.get(&original_player.player_id))
                        {
                            let delta_v = diff(observed_end.vel, state_k.vel);
                            let pos = original_player
                                .frames
                                .pos
                                .get(end_frame as usize)
                                .copied()
                                .unwrap_or(observed_end.pos);
                            hallucinations.push(HallucinationDiag {
                                player_id: player.player_id.clone(),
                                start_frame,
                                end_frame,
                                coverage_label: player_coverage.label(),
                                dodge_vector_events: player_coverage.dodge_vector_events,
                                jump_edges: player_coverage.jump_edges,
                                dodge_edges: player_coverage.dodge_edges,
                                double_jump_edges: player_coverage.double_jump_edges,
                                margin: null_energy - best_flip.energy,
                                pos,
                                surface_margin: nearest_arena_surface_margin(pos),
                                min_car_distance: min_other_car_distance(
                                    original,
                                    player_index,
                                    start_frame,
                                    end_frame,
                                ),
                                planar_delta: norm2([delta_v[0], delta_v[1]]),
                                vertical_delta: delta_v[2],
                                ang_delta: norm(diff(observed_end.ang_vel, state_k.ang_vel)),
                                car_proximity: best_flip.flags.intersects(
                                    AmbiguityFlags::CAR_PROXIMITY
                                        | AmbiguityFlags::COLLISION_SUSPECTED,
                                ),
                                flags: best_flip.flags,
                            });
                        }
                    }

                    if let Some(target) = known_presses.get(&key) {
                        seen_press_targets.insert(key.clone());
                        record_press_trace(
                            &mut press_traces,
                            key.clone(),
                            trace_press_target(
                                player,
                                target,
                                &injected_press_frames,
                                &generation,
                                &scored,
                                solved_jump_presses,
                                solved_jump_press_targets,
                            ),
                        );
                    }
                    if !injected_press_frames.is_empty()
                        || generation
                            .raw_candidates
                            .iter()
                            .any(candidate_has_jump_press)
                    {
                        let mut match_frames = injected_press_frames.clone();
                        match_frames.push(end_frame);
                        for ((target_player_id, target_end_frame), target) in known_presses {
                            if target_player_id != &player.player_id
                                || !match_frames.iter().any(|frame| {
                                    frame_in_press_target_window(
                                        *frame,
                                        target,
                                        PRESS_BOUNDARY_TOLERANCE_FRAMES,
                                    )
                                })
                            {
                                continue;
                            }
                            let target_key = (target_player_id.clone(), *target_end_frame);
                            seen_press_targets.insert(target_key.clone());
                            record_press_trace(
                                &mut press_traces,
                                target_key,
                                trace_press_target(
                                    player,
                                    target,
                                    &injected_press_frames,
                                    &generation,
                                    &scored,
                                    solved_jump_presses,
                                    solved_jump_press_targets,
                                ),
                            );
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

        for ((player_id, end_frame), target) in known_presses {
            if seen_press_targets.contains(&(player_id.clone(), *end_frame)) {
                continue;
            }
            record_press_trace(
                &mut press_traces,
                (player_id.clone(), *end_frame),
                unscored_press_trace(
                    player_id,
                    target,
                    solved_jump_presses,
                    solved_jump_press_targets,
                ),
            );
        }

        (misses, hallucinations, press_traces.into_values().collect())
    }

    #[cfg(feature = "sim")]
    #[allow(clippy::too_many_arguments)]
    fn generate_candidates_for_wp7c_diag(
        state_k: &CarPhysState,
        observed_end: &CarPhysState,
        tracker: &CarTracker,
        interval: &LatticeInterval,
        base_controls: Vec<Controls>,
        seeded_edges: Vec<TimedSeededEdge>,
        config: &EstimatorConfig,
        segment_kind: SegmentKind,
    ) -> CandidateGenerationDiag {
        let ticks = interval_ticks(interval);
        let null = Candidate::null(base_controls.clone(), interval.flags);
        let null_energy = score_null(state_k, observed_end, ticks, &null, &config.fit);
        let null_gate_threshold = config.fit.reject_threshold;
        let seeded_edges_count = seeded_edges.len();
        let long_gap = interval.flags.contains(AmbiguityFlags::LONG_GAP);
        let kinematic_gate = kinematic_gate_diag(state_k, observed_end, tracker, segment_kind);
        if null_energy <= f64::from(null_gate_threshold) && seeded_edges.is_empty() && !long_gap {
            return CandidateGenerationDiag {
                null_fast_path: true,
                null_energy,
                null_gate_threshold,
                seeded_edges_count,
                long_gap,
                kinematic_gate,
                kinematic_events: Vec::new(),
                raw_candidates: vec![null.clone()],
                legal_candidates: vec![null],
            };
        }

        let mut raw_candidates = vec![null];
        let mut kinematic_events = Vec::new();
        let seeded = seeded_candidate_action_sets(&seeded_edges);
        if seeded.is_empty() {
            kinematic_events =
                kinematic_candidate_events(state_k, observed_end, tracker, segment_kind);
            if interval.flags.contains(AmbiguityFlags::LONG_GAP) && second_available(tracker) {
                push_unique_event(&mut kinematic_events, CandidateEvent::Stall);
            }
            for event in &kinematic_events {
                for tick_offset in 0..ticks {
                    if let Some(candidate) = single_event_candidate(
                        *event,
                        tick_offset,
                        base_controls.clone(),
                        interval.flags,
                    ) {
                        raw_candidates.push(candidate);
                    }
                }
            }
        } else {
            for actions in seeded {
                if let Some(candidate) =
                    candidate_from_actions(actions, base_controls.clone(), interval.flags)
                {
                    raw_candidates.push(candidate);
                }
            }
        }

        if interval.flags.contains(AmbiguityFlags::LONG_GAP) {
            add_long_gap_composites_for_wp7c_diag(
                &mut raw_candidates,
                interval,
                base_controls,
                dodge_dir_from_signature(state_k, observed_end),
            );
        }

        raw_candidates.truncate(HYPOTHESIS_CAP);
        let legal_candidates = raw_candidates
            .iter()
            .filter(|candidate| {
                candidate.is_null() || candidate_legal(tracker, candidate, interval.tick_range.0)
            })
            .cloned()
            .collect();
        CandidateGenerationDiag {
            null_fast_path: false,
            null_energy,
            null_gate_threshold,
            seeded_edges_count,
            long_gap,
            kinematic_gate,
            kinematic_events,
            raw_candidates,
            legal_candidates,
        }
    }

    #[cfg(feature = "sim")]
    fn kinematic_gate_diag(
        state_k: &CarPhysState,
        observed_end: &CarPhysState,
        tracker: &CarTracker,
        segment_kind: SegmentKind,
    ) -> KinematicGateDiag {
        let vel_residual = diff(observed_end.vel, state_k.vel);
        let planar_delta = norm2([vel_residual[0], vel_residual[1]]);
        let up_delta = dot(vel_residual, up(state_k.rot));
        let vertical_delta = vel_residual[2];
        let ang_delta = norm(diff(observed_end.ang_vel, state_k.ang_vel));
        let air_segment = segment_kind == SegmentKind::Air;
        let first_jump = first_jump_available(tracker);
        let jump_holding = matches!(tracker.jump, JumpState::Holding { .. });
        let second = second_available(tracker);
        let double_jump_vertical = vertical_delta > 120.0;
        let double_jump_ang = ang_delta < 0.3;
        let double_jump_planar = planar_delta < 250.0;
        let double_jump_gate =
            air_segment && second && double_jump_vertical && double_jump_ang && double_jump_planar;
        let dodge_planar = planar_delta > 150.0;
        let dodge_ang = ang_delta > 0.5;
        let dodge_gate = air_segment && second && (dodge_planar || dodge_ang);
        let stall_gate = air_segment && second && vertical_delta < -30.0;
        let mut gates = Vec::new();
        push_gate(
            &mut gates,
            "kinematic.segment_is_air",
            "segment_kind == Air",
            format!("{segment_kind:?}"),
            air_segment,
        );
        push_gate(
            &mut gates,
            "kinematic.first_jump_available",
            "tracker.jump == Idle && contact grounded/airborne",
            tracker_state(tracker),
            first_jump,
        );
        push_gate(
            &mut gates,
            "kinematic.liftoff_up_delta",
            format!(
                "up_delta > {:.3}",
                crate::consts::JUMP_LIFTOFF_MIN_UP_VEL_STEP
            ),
            format!("{up_delta:.3}"),
            up_delta > crate::consts::JUMP_LIFTOFF_MIN_UP_VEL_STEP,
        );
        push_gate(
            &mut gates,
            "kinematic.jump_holding_for_release",
            "tracker.jump == Holding",
            tracker_state(tracker),
            jump_holding,
        );
        push_gate(
            &mut gates,
            "kinematic.second_available",
            "tracker.second == Available",
            tracker_state(tracker),
            second,
        );
        push_gate(
            &mut gates,
            "kinematic.doublejump_vertical_delta",
            "vertical_delta > 120.000",
            format!("{vertical_delta:.3}"),
            double_jump_vertical,
        );
        push_gate(
            &mut gates,
            "kinematic.doublejump_ang_delta",
            "ang_delta < 0.300",
            format!("{ang_delta:.3}"),
            double_jump_ang,
        );
        push_gate(
            &mut gates,
            "kinematic.doublejump_planar_delta",
            "planar_delta < 250.000",
            format!("{planar_delta:.3}"),
            double_jump_planar,
        );
        push_gate(
            &mut gates,
            "kinematic.doublejump_gate",
            "Air && second && vertical>120 && ang<0.3 && planar<250",
            format!(
                "air={air_segment};second={second};vertical={vertical_delta:.3};ang={ang_delta:.3};planar={planar_delta:.3}"
            ),
            double_jump_gate,
        );
        push_gate(
            &mut gates,
            "kinematic.dodge_planar_delta",
            "planar_delta > 150.000",
            format!("{planar_delta:.3}"),
            dodge_planar,
        );
        push_gate(
            &mut gates,
            "kinematic.dodge_ang_delta",
            "ang_delta > 0.500",
            format!("{ang_delta:.3}"),
            dodge_ang,
        );
        push_gate(
            &mut gates,
            "kinematic.dodge_gate",
            "Air && second && (planar>150 || ang>0.5)",
            format!(
                "air={air_segment};second={second};planar={planar_delta:.3};ang={ang_delta:.3}"
            ),
            dodge_gate,
        );
        push_gate(
            &mut gates,
            "kinematic.stall_vertical_delta",
            "vertical_delta < -30.000",
            format!("{vertical_delta:.3}"),
            vertical_delta < -30.0,
        );
        push_gate(
            &mut gates,
            "kinematic.stall_gate",
            "Air && second && vertical<-30",
            format!("air={air_segment};second={second};vertical={vertical_delta:.3}"),
            stall_gate,
        );

        KinematicGateDiag {
            planar_delta,
            vertical_delta,
            ang_delta,
            air_segment,
            second_available: second,
            double_jump_gate,
            dodge_gate,
            stall_gate,
            gates,
        }
    }

    #[cfg(feature = "sim")]
    fn push_gate(
        gates: &mut Vec<GateConjunctDiag>,
        name: &str,
        threshold: impl Into<String>,
        actual: impl Into<String>,
        passed: bool,
    ) {
        gates.push(GateConjunctDiag {
            name: name.to_string(),
            threshold: threshold.into(),
            actual: actual.into(),
            passed,
        });
    }

    #[cfg(feature = "sim")]
    fn add_long_gap_composites_for_wp7c_diag(
        candidates: &mut Vec<Candidate>,
        interval: &LatticeInterval,
        base_controls: Vec<Controls>,
        dodge_dir: [f32; 2],
    ) {
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
                        candidates.push(Candidate {
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
                        });
                    }
                }
            }
        }
    }

    #[cfg(feature = "sim")]
    fn classify_miss(
        player: &PlayerSeries,
        target: &ComponentTarget,
        generation: &CandidateGenerationDiag,
        scored: &[ScoredCandidate],
        tracker: &CarTracker,
        component_press_frames: &BTreeMap<String, BTreeSet<u32>>,
        solved_jump_presses: &BTreeMap<(String, u32), ()>,
    ) -> MissDiag {
        let raw_flip_count = generation
            .raw_candidates
            .iter()
            .filter(|candidate| candidate_has_flip(candidate))
            .count();
        let legal_flip_count = generation
            .legal_candidates
            .iter()
            .filter(|candidate| candidate_has_flip(candidate))
            .count();
        let best = scored.first();
        let best_flip_energy = scored
            .iter()
            .filter(|item| candidate_has_flip(&item.candidate))
            .map(|item| item.energy)
            .min_by(|a, b| a.total_cmp(b));
        let null_energy = scored
            .iter()
            .find(|item| item.candidate.is_null())
            .map(|item| item.energy);
        let truth_press_in_window = press_in_window(
            component_press_frames.get(&player.player_id),
            target.end_frame,
        );
        let unseeded_press_in_window =
            solved_press_in_window(solved_jump_presses, &player.player_id, target.end_frame);

        let (class, reason, winner) = if legal_flip_count == 0 {
            if raw_flip_count > 0 {
                (
                    MissClass::Illegal,
                    "candidate_legal_rejected_all_flip_candidates".to_string(),
                    best.map_or("none", |item| candidate_name(&item.candidate)),
                )
            } else {
                (
                    MissClass::NoCandidate,
                    no_candidate_reason(generation, tracker),
                    best.map_or("none", |item| candidate_name(&item.candidate)),
                )
            }
        } else if best.is_some_and(|item| item.candidate.is_null()) {
            (
                MissClass::OutscoredByNull,
                "null_ranked_first_after_margin".to_string(),
                "Null",
            )
        } else if best.is_some_and(|item| !candidate_has_flip(&item.candidate)) {
            (
                MissClass::OutscoredByEvent,
                "different_event_ranked_first".to_string(),
                best.map_or("none", |item| candidate_name(&item.candidate)),
            )
        } else {
            (
                MissClass::OutscoredByEvent,
                "flip_ranked_first_in_diagnostic_but_not_emitted".to_string(),
                best.map_or("none", |item| candidate_name(&item.candidate)),
            )
        };

        MissDiag {
            player_id: player.player_id.clone(),
            start_frame: target.start_frame,
            end_frame: target.end_frame,
            span_frames: target.span_frames,
            span_ticks: target.span_ticks,
            held_frames: target.held_frames,
            class,
            reason,
            winner,
            margin: null_energy
                .zip(best_flip_energy)
                .map(|(null, flip)| null - flip),
            truth_press_in_window,
            unseeded_press_in_window,
            wrong_veto: class == MissClass::Illegal && truth_press_in_window,
            flags: target.flags,
            tracker_state: tracker_state(tracker),
        }
    }

    #[cfg(feature = "sim")]
    fn unscored_miss(
        player_id: &str,
        target: &ComponentTarget,
        component_press_frames: &BTreeMap<String, BTreeSet<u32>>,
        solved_jump_presses: &BTreeMap<(String, u32), ()>,
    ) -> MissDiag {
        MissDiag {
            player_id: player_id.to_string(),
            start_frame: target.start_frame,
            end_frame: target.end_frame,
            span_frames: target.span_frames,
            span_ticks: target.span_ticks,
            held_frames: target.held_frames,
            class: MissClass::Unscored,
            reason: if target.reached_scoring {
                "not_seen_in_final_unseeded_scoring_pass".to_string()
            } else {
                "component_flip_not_in_fresh_scoring_interval".to_string()
            },
            winner: "none",
            margin: None,
            truth_press_in_window: press_in_window(
                component_press_frames.get(player_id),
                target.end_frame,
            ),
            unseeded_press_in_window: solved_press_in_window(
                solved_jump_presses,
                player_id,
                target.end_frame,
            ),
            wrong_veto: false,
            flags: target.flags,
            tracker_state: "unscored".to_string(),
        }
    }

    #[cfg(feature = "sim")]
    fn wave_a3_replay_misses(replay: &str, series: &ReplaySeries) -> Vec<A3MissDiag> {
        let known_flips = coalesced_component_targets(series, is_component_flip_edge, false);
        let component_press_frames = component_jump_press_frames(series);

        let mut config = default_estimator_config();
        config.mode = Mode::Unseeded;
        config.engine = EnginePreference::PreferReference;
        let masked = masked_series_for_solving(series, &config);
        let first = solve_pass(&masked, &config, &[], true);
        let retro_splits = first.retro_splits.clone();
        let output = if retro_splits.is_empty() {
            first.output
        } else {
            solve_pass(&masked, &config, &retro_splits, false).output
        };
        let solved_flips = solved_flip_intervals(&output);
        let solved_jump_presses =
            solved_event_frame_sets(&output, |kind| matches!(kind, SolvedEventKind::JumpPress));
        let segmentation = segment_replay_with_splits_and_confidences(
            &masked,
            &retro_splits,
            CONFIDENT_SEGMENT_THRESHOLD,
            |_player_id, _segment| None,
        );
        let mut misses = Vec::new();

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
            let hints = SeededHints::new(&player.component);
            let mut reference = ReferenceScorer::new();
            let mut freshness = KinematicFreshness::from_frames(&player.frames);
            for segment in &segmented_player.segments {
                freshness.mark_fresh(segment.frame_span.0);
            }

            for segment in &segmented_player.segments {
                let tracker = tracker_for_segment(player, segment, masked.tick_rate);
                let mut branching = BranchingTracker::new(tracker.clone());
                for scoring in fresh_scoring_intervals(segment, &freshness) {
                    let start_frame = scoring.start_frame;
                    let interval = &scoring.interval;
                    let end_frame = interval.frame_index;
                    let key = (player.player_id.clone(), end_frame);
                    if frame_out_of_bounds(player, start_frame)
                        || frame_out_of_bounds(player, end_frame)
                    {
                        continue;
                    }

                    let interval_tracker = branching.best_tracker().clone();
                    let ticks = interval_ticks(interval);
                    let state_k = car_state(
                        player,
                        start_frame,
                        interval.tick_range.0,
                        &interval_tracker,
                    );
                    let observed_end =
                        car_state(player, end_frame, interval.tick_range.1, &interval_tracker);
                    let base_controls = solve_controls(
                        player,
                        start_frame,
                        end_frame,
                        interval,
                        &interval_tracker,
                        &config,
                    );
                    let seeded_edges = edges_for_interval_with_implied_liftoff(
                        player,
                        &hints,
                        segment,
                        start_frame,
                        end_frame,
                        interval,
                        &config,
                    );
                    let generation = generate_candidates_for_wp7c_diag(
                        &state_k,
                        &observed_end,
                        &interval_tracker,
                        interval,
                        base_controls,
                        seeded_edges,
                        &config,
                        segment.kind,
                    );
                    let (mut scored, _portable_best, _reference_best) = score_candidates_for_diag(
                        &state_k,
                        &observed_end,
                        ticks,
                        &generation.legal_candidates,
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

                    if let Some(target) = known_flips.get(&key) {
                        if !solved_flips.contains(&key) {
                            let miss = classify_miss(
                                player,
                                target,
                                &generation,
                                &scored,
                                &interval_tracker,
                                &component_press_frames,
                                &solved_jump_presses,
                            );
                            if matches!(
                                miss.class,
                                MissClass::NoCandidate | MissClass::OutscoredByNull
                            ) {
                                let truth = component_truth_for_target(
                                    original_player,
                                    segment,
                                    target,
                                    interval,
                                );
                                misses.push(A3MissDiag {
                                    replay: replay.to_string(),
                                    player_id: player.player_id.clone(),
                                    start_frame: target.start_frame,
                                    end_frame: target.end_frame,
                                    span_frames: target.span_frames,
                                    span_ticks: target.span_ticks,
                                    held_frames: target.held_frames,
                                    class: miss.class,
                                    reason: miss.reason,
                                    winner: miss.winner,
                                    flags: target.flags,
                                    tracker_state: tracker_state(&interval_tracker),
                                    observed: observed_span_diag(
                                        original_player,
                                        start_frame,
                                        end_frame,
                                        &state_k,
                                        &observed_end,
                                    ),
                                    gates: a3_gate_conjuncts(&generation),
                                    failures: a3_blocking_failures(&generation, truth.as_ref()),
                                    truth,
                                    legal_candidates: generation.legal_candidates.clone(),
                                    state_k,
                                    observed_end,
                                    ticks,
                                    weights: config.fit,
                                });
                            }
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

        misses
    }

    #[cfg(feature = "sim")]
    fn a3_gate_conjuncts(generation: &CandidateGenerationDiag) -> Vec<GateConjunctDiag> {
        let mut gates = Vec::new();
        push_gate(
            &mut gates,
            "upstream.null_fast_path_not_taken",
            format!(
                "null_energy > {:.3} OR seeded_edges>0 OR LONG_GAP",
                generation.null_gate_threshold
            ),
            format!(
                "null_energy={:.3};seeded_edges={};long_gap={}",
                generation.null_energy, generation.seeded_edges_count, generation.long_gap
            ),
            !generation.null_fast_path,
        );
        push_gate(
            &mut gates,
            "upstream.kinematic_path_not_bypassed_by_seeded_edges",
            "seeded_edges == 0",
            generation.seeded_edges_count.to_string(),
            generation.seeded_edges_count == 0,
        );
        gates.extend(generation.kinematic_gate.gates.clone());
        gates
    }

    #[cfg(feature = "sim")]
    fn a3_blocking_failures(
        generation: &CandidateGenerationDiag,
        truth: Option<&ComponentTruthDiag>,
    ) -> Vec<String> {
        if generation.null_fast_path {
            return vec!["upstream.null_fast_path_not_taken".to_string()];
        }
        if generation.seeded_edges_count > 0 {
            return vec!["upstream.kinematic_path_not_bypassed_by_seeded_edges".to_string()];
        }
        let gate = &generation.kinematic_gate;
        let mut failures = Vec::new();
        if !gate.air_segment {
            failures.push("kinematic.segment_is_air".to_string());
        }
        if !gate.second_available {
            failures.push("kinematic.second_available".to_string());
        }
        match truth.map(|truth| truth.kind) {
            Some("Dodge") => {
                if gate.air_segment && gate.second_available && !gate.dodge_gate {
                    failures.push("kinematic.dodge_gate".to_string());
                }
            }
            Some("DoubleJump") => {
                if gate.air_segment && gate.second_available && !gate.double_jump_gate {
                    if gate.vertical_delta <= 120.0 {
                        failures.push("kinematic.doublejump_vertical_delta".to_string());
                    }
                    if gate.ang_delta >= 0.3 {
                        failures.push("kinematic.doublejump_ang_delta".to_string());
                    }
                    if gate.planar_delta >= 250.0 {
                        failures.push("kinematic.doublejump_planar_delta".to_string());
                    }
                }
            }
            Some("Stall") => {
                if gate.air_segment && gate.second_available && !gate.stall_gate {
                    failures.push("kinematic.stall_gate".to_string());
                }
            }
            _ => {
                if gate.air_segment
                    && gate.second_available
                    && !gate.dodge_gate
                    && !gate.double_jump_gate
                {
                    failures.push("kinematic.flip_signature_gate".to_string());
                }
            }
        }
        if failures.is_empty() {
            failures.push("candidate_builder_or_later_filter".to_string());
        }
        failures
    }

    #[cfg(feature = "sim")]
    fn no_candidate_reason(generation: &CandidateGenerationDiag, tracker: &CarTracker) -> String {
        if !second_available(tracker) {
            "TRACKER_SECOND_NOT_AVAILABLE".to_string()
        } else if generation.null_fast_path {
            "NULL_FAST_PATH".to_string()
        } else if generation.kinematic_events.is_empty() {
            "KINEMATIC_GATE_DID_NOT_FIRE".to_string()
        } else if !generation
            .kinematic_events
            .iter()
            .any(candidate_event_is_flip)
        {
            format!(
                "EVENT_KIND_FILTERED:{}",
                generation
                    .kinematic_events
                    .iter()
                    .map(|event| candidate_event_name(*event))
                    .collect::<Vec<_>>()
                    .join("|")
            )
        } else {
            "NO_FLIP_CANDIDATE_AFTER_CANDIDATE_BUILD".to_string()
        }
    }

    #[cfg(feature = "sim")]
    fn component_truth_for_target(
        player: &PlayerSeries,
        segment: &Segment,
        target: &ComponentTarget,
        interval: &LatticeInterval,
    ) -> Option<ComponentTruthDiag> {
        crate::tracker::reconstruct_seeded_edges(&player.component)
            .into_iter()
            .filter(is_component_flip_edge)
            .filter(|edge| {
                edge.frame_index > target.start_frame && edge.frame_index <= target.end_frame
            })
            .min_by_key(|edge| target.end_frame.abs_diff(edge.frame_index))
            .map(|edge| {
                let (kind, dir) = match edge.component {
                    ComponentKind::DoubleJumpImpulse => ("DoubleJump", None),
                    ComponentKind::DodgeTorque => {
                        match edge.vector.map(classify_dodge_torque_vector) {
                            Some(SecondActionClass::Dodge { dir, .. }) => ("Dodge", Some(dir)),
                            Some(SecondActionClass::DoubleJump) => ("DoubleJump", None),
                            Some(SecondActionClass::Stall) => ("Stall", None),
                            None => ("Dodge", None),
                        }
                    }
                    _ => ("unknown", None),
                };
                ComponentTruthDiag {
                    kind,
                    frame: edge.frame_index,
                    raw_vector: edge.vector,
                    dir,
                    tick_range: truth_tick_range(segment, edge.frame_index, interval),
                }
            })
    }

    #[cfg(feature = "sim")]
    fn truth_tick_range(
        segment: &Segment,
        frame_index: u32,
        scoring_interval: &LatticeInterval,
    ) -> (u32, u32) {
        segment
            .lattice
            .intervals
            .iter()
            .find(|interval| interval.frame_index == frame_index)
            .map(|interval| {
                (
                    interval
                        .tick_range
                        .0
                        .saturating_sub(scoring_interval.tick_range.0)
                        .min(u64::from(u32::MAX)) as u32,
                    interval
                        .tick_range
                        .1
                        .saturating_sub(scoring_interval.tick_range.0)
                        .min(u64::from(u32::MAX)) as u32,
                )
            })
            .unwrap_or((0, interval_ticks(scoring_interval)))
    }

    #[cfg(feature = "sim")]
    fn observed_span_diag(
        player: &PlayerSeries,
        start_frame: u32,
        end_frame: u32,
        state_k: &CarPhysState,
        observed_end: &CarPhysState,
    ) -> ObservedSpanDiag {
        let delta_v = diff(observed_end.vel, state_k.vel);
        let delta_ang = diff(observed_end.ang_vel, state_k.ang_vel);
        let mut max_step_planar_delta = 0.0_f32;
        let mut max_step_ang_delta = 0.0_f32;
        for frame in start_frame.saturating_add(1)..=end_frame {
            let prev = frame_state(player, frame - 1);
            let curr = frame_state(player, frame);
            let step_v = diff(curr.vel, prev.vel);
            max_step_planar_delta = max_step_planar_delta.max(norm2([step_v[0], step_v[1]]));
            max_step_ang_delta = max_step_ang_delta.max(norm(diff(curr.ang_vel, prev.ang_vel)));
        }
        ObservedSpanDiag {
            ang_delta: norm(delta_ang),
            ang_axis: dominant_axis(delta_ang),
            planar_delta: norm2([delta_v[0], delta_v[1]]),
            vertical_delta: delta_v[2],
            rotation_angle: crate::fit::rotation_distance_rad(state_k.rot, observed_end.rot),
            max_step_planar_delta,
            max_step_ang_delta,
        }
    }

    #[cfg(feature = "sim")]
    fn dominant_axis(v: [f32; 3]) -> &'static str {
        let x = v[0].abs();
        let y = v[1].abs();
        let z = v[2].abs();
        if x >= y && x >= z {
            "x"
        } else if y >= z {
            "y"
        } else {
            "z"
        }
    }

    #[cfg(feature = "sim")]
    fn stratified_a3_sample<'a>(rows: &[&'a A3MissDiag], limit: usize) -> Vec<&'a A3MissDiag> {
        let mut by_replay: BTreeMap<&str, Vec<&A3MissDiag>> = BTreeMap::new();
        for row in rows {
            by_replay.entry(row.replay.as_str()).or_default().push(*row);
        }
        let mut out = Vec::new();
        while out.len() < limit {
            let mut progressed = false;
            for replay_rows in by_replay.values_mut() {
                if replay_rows.is_empty() {
                    continue;
                }
                out.push(replay_rows.remove(0));
                progressed = true;
                if out.len() >= limit {
                    break;
                }
            }
            if !progressed {
                break;
            }
        }
        out
    }

    #[cfg(feature = "sim")]
    fn print_a3_failure_histogram(label: &str, rows: &[&A3MissDiag]) {
        let mut counts = BTreeMap::new();
        for row in rows {
            for failure in &row.failures {
                *counts.entry(failure.as_str()).or_insert(0usize) += 1;
            }
        }
        for (failure, count) in counts {
            println!(
                "wave_a3_failure_histogram,label={label},failure={failure},count={count},share={:.3}",
                recall(count, rows.len())
            );
        }
    }

    #[cfg(feature = "sim")]
    fn print_a3_table_a(rows: &[&A3MissDiag]) {
        println!("wave_a3_table_a_begin");
        println!(
            "| replay | player | frames | span | observed deltas | truth | failures | reason/winner/tracker | gates |"
        );
        println!("| --- | --- | ---: | --- | --- | --- | --- | --- | --- |");
        for row in rows {
            println!(
                "| {} | {} | {}..{} | frames={} span_frames={} held={} ticks={} flags={:?} | |d_ang|={:.3} axis={} planar_dv={:.3} vertical_dv={:.3} rot={:.5} max_step_planar={:.3} max_step_ang={:.3} | {} | {} | reason={} winner={} tracker={} | {} |",
                row.replay,
                row.player_id,
                row.start_frame,
                row.end_frame,
                row.end_frame.saturating_sub(row.start_frame),
                row.span_frames,
                row.held_frames,
                row.span_ticks,
                row.flags,
                row.observed.ang_delta,
                row.observed.ang_axis,
                row.observed.planar_delta,
                row.observed.vertical_delta,
                row.observed.rotation_angle,
                row.observed.max_step_planar_delta,
                row.observed.max_step_ang_delta,
                truth_summary(row.truth.as_ref()),
                row.failures.join(";"),
                row.reason,
                row.winner,
                row.tracker_state,
                gate_summary(&row.gates)
            );
        }
        println!("wave_a3_table_a_end");
    }

    #[cfg(feature = "sim")]
    fn print_a3_table_b(rows: &[&A3MissDiag]) {
        println!("wave_a3_table_b_begin");
        println!("| replay | player | frames | truth | true candidate? / dominant residual | candidates |");
        println!("| --- | --- | ---: | --- | --- | --- |");
        for row in rows {
            let scored = score_a3_candidates(row);
            println!(
                "| {} | {} | {}..{} | {} | {} | {} |",
                row.replay,
                row.player_id,
                row.start_frame,
                row.end_frame,
                truth_summary(row.truth.as_ref()),
                true_candidate_note(row, &scored),
                scored
                    .iter()
                    .map(|item| format!(
                        "{} E={:.3} dE_null={:.3}",
                        item.spec, item.energy, item.delta_vs_null
                    ))
                    .collect::<Vec<_>>()
                    .join("; ")
            );
        }
        println!("wave_a3_table_b_end");
    }

    #[cfg(feature = "sim")]
    fn truth_summary(truth: Option<&ComponentTruthDiag>) -> String {
        match truth {
            Some(truth) => format!(
                "kind={} frame={} tick_range={:?} dir={} raw_vector={}",
                truth.kind,
                truth.frame,
                truth.tick_range,
                truth
                    .dir
                    .map(|dir| format!("[{:.3},{:.3}]", dir[0], dir[1]))
                    .unwrap_or_else(|| "none".to_string()),
                truth
                    .raw_vector
                    .map(|v| format!("[{:.3},{:.3},{:.3}]", v[0], v[1], v[2]))
                    .unwrap_or_else(|| "none".to_string())
            ),
            None => "none".to_string(),
        }
    }

    #[cfg(feature = "sim")]
    fn gate_summary(gates: &[GateConjunctDiag]) -> String {
        gates
            .iter()
            .map(|gate| {
                format!(
                    "{} threshold=({}) actual=({}) {}",
                    gate.name,
                    gate.threshold,
                    gate.actual,
                    if gate.passed { "PASS" } else { "FAIL" }
                )
            })
            .collect::<Vec<_>>()
            .join("; ")
    }

    #[cfg(feature = "sim")]
    fn score_a3_candidates(row: &A3MissDiag) -> Vec<A3ScoredCandidate> {
        let mut engine = crate::engine::rocketsim::RocketSimEngine::new();
        let scored: Vec<_> = row
            .legal_candidates
            .iter()
            .cloned()
            .map(|candidate| {
                score_one(
                    &mut engine,
                    &row.state_k,
                    &row.observed_end,
                    row.ticks,
                    candidate,
                    &row.weights,
                )
            })
            .collect();
        let null_energy = scored
            .iter()
            .find(|item| item.candidate.is_null())
            .map(|item| item.energy)
            .unwrap_or(f64::NAN);
        let mut out: Vec<_> = scored
            .into_iter()
            .map(|item| A3ScoredCandidate {
                spec: candidate_spec(&item.candidate),
                terms: residual_terms(&item.sim_end, &row.observed_end, &row.weights),
                delta_vs_null: item.energy - null_energy,
                energy: item.energy,
                candidate: item.candidate,
            })
            .collect();
        out.sort_by(|a, b| a.energy.total_cmp(&b.energy));
        out
    }

    #[cfg(feature = "sim")]
    fn true_candidate_note(row: &A3MissDiag, scored: &[A3ScoredCandidate]) -> String {
        let Some(truth) = row.truth.as_ref() else {
            return "false; no component truth edge found".to_string();
        };
        let Some(null) = scored.iter().find(|item| item.candidate.is_null()) else {
            return "false; null candidate missing".to_string();
        };
        let Some(best_true) = scored
            .iter()
            .filter(|item| candidate_matches_truth(&item.candidate, truth))
            .min_by(|a, b| a.energy.total_cmp(&b.energy))
        else {
            return "false; no legal candidate matched kind+dir_dot>=0.95+truth_tick_range"
                .to_string();
        };
        let term_deltas = [
            ("pos", best_true.terms[0] - null.terms[0]),
            ("vel", best_true.terms[1] - null.terms[1]),
            ("rot", best_true.terms[2] - null.terms[2]),
            ("ang_vel", best_true.terms[3] - null.terms[3]),
        ];
        let dominant = term_deltas
            .into_iter()
            .max_by(|a, b| a.1.total_cmp(&b.1))
            .unwrap_or(("unknown", f64::NAN));
        if best_true.energy < null.energy {
            format!(
                "true; raw event beats null by {:.3} but margin {:.3} not cleared; largest residual delta {}={:.3}",
                null.energy - best_true.energy,
                row.weights.null_event_accept_margin,
                dominant.0,
                dominant.1
            )
        } else {
            format!(
                "true; true E worse than null by {:.3}; dominated by {}={:.3}",
                best_true.energy - null.energy,
                dominant.0,
                dominant.1
            )
        }
    }

    #[cfg(feature = "sim")]
    fn residual_terms(
        sim_end: &CarPhysState,
        observed_end: &CarPhysState,
        weights: &FitWeights,
    ) -> [f64; 4] {
        [
            f64::from(norm(diff(sim_end.pos, observed_end.pos))).powi(2)
                / f64::from(weights.position_sigma).powi(2),
            f64::from(norm(diff(sim_end.vel, observed_end.vel))).powi(2)
                / f64::from(weights.velocity_sigma).powi(2),
            crate::fit::rotation_distance_rad(sim_end.rot, observed_end.rot).powi(2)
                / f64::from(weights.rotation_sigma).powi(2),
            f64::from(norm(diff(sim_end.ang_vel, observed_end.ang_vel))).powi(2)
                / f64::from(weights.angular_velocity_sigma).powi(2),
        ]
    }

    #[cfg(feature = "sim")]
    fn candidate_matches_truth(candidate: &Candidate, truth: &ComponentTruthDiag) -> bool {
        candidate.actions.iter().any(|action| {
            let tick_matches = action.tick_offset >= truth.tick_range.0
                && action.tick_offset < truth.tick_range.1.max(truth.tick_range.0 + 1);
            if !tick_matches {
                return false;
            }
            match (action.event, truth.kind, truth.dir) {
                (CandidateEvent::DoubleJump, "DoubleJump", _) => true,
                (CandidateEvent::Stall, "Stall", _) => true,
                (CandidateEvent::Dodge { dir }, "Dodge", Some(truth_dir)) => {
                    dot2(dir, truth_dir) >= 0.95
                }
                (CandidateEvent::Dodge { .. }, "Dodge", None) => true,
                _ => false,
            }
        })
    }

    #[cfg(feature = "sim")]
    fn candidate_spec(candidate: &Candidate) -> String {
        if candidate.is_null() {
            return "Null".to_string();
        }
        candidate
            .actions
            .iter()
            .map(|action| match action.event {
                CandidateEvent::JumpPress => format!("JumpPress(tick={})", action.tick_offset),
                CandidateEvent::JumpRelease => format!("JumpRelease(tick={})", action.tick_offset),
                CandidateEvent::DoubleJump => format!("DoubleJump(tick={})", action.tick_offset),
                CandidateEvent::Dodge { dir } => {
                    format!(
                        "Dodge(dir=[{:.3},{:.3}],tick={})",
                        dir[0], dir[1], action.tick_offset
                    )
                }
                CandidateEvent::Stall => format!("Stall(tick={})", action.tick_offset),
            })
            .collect::<Vec<_>>()
            .join("+")
    }

    #[cfg(feature = "sim")]
    fn dot2(a: [f32; 2], b: [f32; 2]) -> f32 {
        a[0] * b[0] + a[1] * b[1]
    }

    #[cfg(feature = "sim")]
    fn coalesced_component_targets(
        series: &ReplaySeries,
        keep: fn(&ReconstructedEdge) -> bool,
        include_unscored: bool,
    ) -> BTreeMap<(String, u32), ComponentTarget> {
        let segmentation = crate::segment::segment_replay(series);
        let mut targets = BTreeMap::new();
        for segmented_player in &segmentation.players {
            let Some(player) = series
                .players
                .iter()
                .find(|player| player.player_id == segmented_player.player_id)
            else {
                continue;
            };
            let edges: Vec<_> = crate::tracker::reconstruct_seeded_edges(&player.component)
                .into_iter()
                .filter(keep)
                .collect();
            let mut covered = BTreeSet::new();
            let mut freshness = KinematicFreshness::from_frames(&player.frames);
            for segment in &segmented_player.segments {
                freshness.mark_fresh(segment.frame_span.0);
            }
            for segment in &segmented_player.segments {
                for scoring in fresh_scoring_intervals(segment, &freshness) {
                    let edge_frames: Vec<_> = edges
                        .iter()
                        .map(|edge| edge.frame_index)
                        .filter(|frame| {
                            *frame > scoring.start_frame && *frame <= scoring.interval.frame_index
                        })
                        .collect();
                    if edge_frames.is_empty() {
                        continue;
                    }
                    covered.extend(edge_frames.iter().copied());
                    let key = (player.player_id.clone(), scoring.interval.frame_index);
                    targets
                        .entry(key)
                        .and_modify(|target: &mut ComponentTarget| {
                            target.flags |= scoring.interval.flags;
                            for frame in &edge_frames {
                                if !target.edge_frames.contains(frame) {
                                    target.edge_frames.push(*frame);
                                }
                            }
                        })
                        .or_insert_with(|| ComponentTarget {
                            start_frame: scoring.start_frame,
                            end_frame: scoring.interval.frame_index,
                            flags: scoring.interval.flags,
                            held_frames: held_frames(
                                &freshness,
                                scoring.start_frame,
                                scoring.interval.frame_index,
                            ),
                            span_frames: scoring.interval.frame_index - scoring.start_frame,
                            span_ticks: scoring
                                .interval
                                .tick_range
                                .1
                                .saturating_sub(scoring.interval.tick_range.0),
                            reached_scoring: true,
                            edge_frames,
                        });
                }
            }
            if include_unscored {
                for edge in edges {
                    if covered.contains(&edge.frame_index) {
                        continue;
                    }
                    let flags = flags_for_frame(segmented_player, edge.frame_index);
                    targets
                        .entry((player.player_id.clone(), edge.frame_index))
                        .or_insert_with(|| ComponentTarget {
                            start_frame: edge.frame_index.saturating_sub(1),
                            end_frame: edge.frame_index,
                            flags,
                            held_frames: 0,
                            span_frames: u32::from(edge.frame_index > 0),
                            span_ticks: 0,
                            reached_scoring: false,
                            edge_frames: vec![edge.frame_index],
                        });
                }
            }
        }
        targets
    }

    #[cfg(feature = "sim")]
    fn flags_for_frame(
        player: &crate::segment::PlayerSegmentation,
        frame_index: u32,
    ) -> AmbiguityFlags {
        player
            .interval_flags
            .iter()
            .find(|flags| flags.frame_index == frame_index)
            .map(|flags| flags.flags)
            .unwrap_or_default()
    }

    #[cfg(feature = "sim")]
    fn held_frames(freshness: &KinematicFreshness, start_frame: u32, end_frame: u32) -> usize {
        (start_frame.saturating_add(1)..=end_frame)
            .filter(|frame| !freshness.is_fresh(*frame))
            .count()
    }

    #[cfg(feature = "sim")]
    fn is_component_flip_edge(edge: &ReconstructedEdge) -> bool {
        matches!(
            edge.component,
            ComponentKind::DodgeTorque | ComponentKind::DoubleJumpImpulse
        )
    }

    #[cfg(feature = "sim")]
    fn is_component_jump_press_edge(edge: &ReconstructedEdge) -> bool {
        if edge.component != ComponentKind::Jump {
            return false;
        }
        match edge.counter_delta {
            Some(delta) => delta.current % 2 != 0,
            None => true,
        }
    }

    #[cfg(feature = "sim")]
    fn component_jump_press_frames(series: &ReplaySeries) -> BTreeMap<String, BTreeSet<u32>> {
        let mut out = BTreeMap::new();
        for player in &series.players {
            let frames = crate::tracker::reconstruct_seeded_edges(&player.component)
                .into_iter()
                .filter(is_component_jump_press_edge)
                .map(|edge| edge.frame_index)
                .collect();
            out.insert(player.player_id.clone(), frames);
        }
        out
    }

    #[cfg(feature = "sim")]
    fn component_coverage_by_player(series: &ReplaySeries) -> BTreeMap<String, ComponentCoverage> {
        let mut out = BTreeMap::new();
        for player in &series.players {
            let edges = crate::tracker::reconstruct_seeded_edges(&player.component);
            out.insert(
                player.player_id.clone(),
                ComponentCoverage {
                    dodge_vector_events: player
                        .component
                        .events
                        .iter()
                        .filter(|event| {
                            event.component == ComponentKind::DodgeTorque && event.vector.is_some()
                        })
                        .count(),
                    jump_edges: edges
                        .iter()
                        .filter(|edge| edge.component == ComponentKind::Jump)
                        .count(),
                    dodge_edges: edges
                        .iter()
                        .filter(|edge| edge.component == ComponentKind::DodgeTorque)
                        .count(),
                    double_jump_edges: edges
                        .iter()
                        .filter(|edge| edge.component == ComponentKind::DoubleJumpImpulse)
                        .count(),
                },
            );
        }
        out
    }

    #[cfg(feature = "sim")]
    fn solved_event_frame_sets(
        output: &SolveOutput,
        keep: fn(&SolvedEventKind) -> bool,
    ) -> BTreeMap<(String, u32), ()> {
        let mut out = BTreeMap::new();
        for timeline in &output.timelines {
            for event in &timeline.events {
                if keep(&event.kind) {
                    out.insert((timeline.player_id.clone(), event.frame_index), ());
                }
            }
        }
        out
    }

    #[cfg(feature = "sim")]
    fn coalesced_solved_press_targets(
        known_presses: &BTreeMap<(String, u32), ComponentTarget>,
        output: &SolveOutput,
        keep: fn(&SolvedEventKind) -> bool,
        tolerance_frames: u32,
    ) -> BTreeMap<(String, u32), Vec<u32>> {
        let mut out: BTreeMap<(String, u32), Vec<u32>> = BTreeMap::new();
        for timeline in &output.timelines {
            for event in &timeline.events {
                if !keep(&event.kind) {
                    continue;
                }
                if let Some((key, _target)) = known_presses
                    .iter()
                    .filter(|((player_id, _end_frame), target)| {
                        player_id == &timeline.player_id
                            && frame_in_press_target_window(
                                event.frame_index,
                                target,
                                tolerance_frames,
                            )
                    })
                    .min_by_key(|((_player_id, end_frame), _target)| {
                        end_frame.abs_diff(event.frame_index)
                    })
                {
                    out.entry(key.clone()).or_default().push(event.frame_index);
                }
            }
        }
        out
    }

    #[cfg(feature = "sim")]
    fn frame_in_press_target_window(
        frame_index: u32,
        target: &ComponentTarget,
        tolerance_frames: u32,
    ) -> bool {
        let start = target.start_frame.saturating_sub(tolerance_frames);
        let end = target.end_frame.saturating_add(tolerance_frames);
        (start..=end).contains(&frame_index)
    }

    #[cfg(feature = "sim")]
    fn trace_press_target(
        player: &PlayerSeries,
        target: &ComponentTarget,
        injected_press_frames: &[u32],
        generation: &CandidateGenerationDiag,
        scored: &[ScoredCandidate],
        solved_jump_presses: &BTreeMap<(String, u32), ()>,
        solved_jump_press_targets: &BTreeMap<(String, u32), Vec<u32>>,
    ) -> PressTraceDiag {
        let key = (player.player_id.clone(), target.end_frame);
        let raw_press_candidates = generation
            .raw_candidates
            .iter()
            .filter(|candidate| candidate_has_jump_press(candidate))
            .count();
        let legal_press_candidates = generation
            .legal_candidates
            .iter()
            .filter(|candidate| candidate_has_jump_press(candidate))
            .count();
        let selected = scored
            .first()
            .is_some_and(|item| candidate_has_jump_press(&item.candidate));
        let winner = scored
            .first()
            .map_or("none", |item| candidate_name(&item.candidate));
        let mut emitted_raw_frames = solved_jump_press_targets
            .get(&key)
            .cloned()
            .unwrap_or_default();
        emitted_raw_frames.extend(
            solved_jump_presses
                .keys()
                .filter(|(player_id, frame)| {
                    player_id == &player.player_id
                        && frame_in_press_target_window(
                            *frame,
                            target,
                            PRESS_BOUNDARY_TOLERANCE_FRAMES,
                        )
                })
                .map(|(_player_id, frame)| *frame),
        );
        emitted_raw_frames.sort_unstable();
        emitted_raw_frames.dedup();
        let rejection = if selected {
            "SELECTED"
        } else if injected_press_frames.is_empty() && !emitted_raw_frames.is_empty() {
            "BOUNDARY_EMITTED"
        } else if injected_press_frames.is_empty() {
            "NOT_INJECTED"
        } else if raw_press_candidates == 0 {
            "NO_PRESS_CANDIDATE"
        } else if legal_press_candidates == 0 {
            "ILLEGAL"
        } else if winner == "Null" {
            "OUTSCORED_BY_NULL"
        } else {
            "OUTSCORED_BY_EVENT"
        };

        PressTraceDiag {
            player_id: player.player_id.clone(),
            start_frame: target.start_frame,
            end_frame: target.end_frame,
            injected_frames: injected_press_frames.to_vec(),
            raw_press_candidates,
            legal_press_candidates,
            selected,
            winner,
            rejection,
            emitted_raw_frames,
            coalesced_hit: solved_jump_press_targets.contains_key(&key),
        }
    }

    #[cfg(feature = "sim")]
    fn unscored_press_trace(
        player_id: &str,
        target: &ComponentTarget,
        solved_jump_presses: &BTreeMap<(String, u32), ()>,
        solved_jump_press_targets: &BTreeMap<(String, u32), Vec<u32>>,
    ) -> PressTraceDiag {
        let key = (player_id.to_string(), target.end_frame);
        let mut emitted_raw_frames = solved_jump_press_targets
            .get(&key)
            .cloned()
            .unwrap_or_default();
        emitted_raw_frames.extend(
            solved_jump_presses
                .keys()
                .filter(|(event_player_id, frame)| {
                    event_player_id.as_str() == player_id
                        && frame_in_press_target_window(
                            *frame,
                            target,
                            PRESS_BOUNDARY_TOLERANCE_FRAMES,
                        )
                })
                .map(|(_player_id, frame)| *frame),
        );
        emitted_raw_frames.sort_unstable();
        emitted_raw_frames.dedup();
        let rejection = if emitted_raw_frames.is_empty() {
            "UNSCORED"
        } else {
            "BOUNDARY_EMITTED"
        };
        PressTraceDiag {
            player_id: player_id.to_string(),
            start_frame: target.start_frame,
            end_frame: target.end_frame,
            injected_frames: Vec::new(),
            raw_press_candidates: 0,
            legal_press_candidates: 0,
            selected: false,
            winner: "none",
            rejection,
            emitted_raw_frames,
            coalesced_hit: solved_jump_press_targets.contains_key(&key),
        }
    }

    #[cfg(feature = "sim")]
    fn record_press_trace(
        traces: &mut BTreeMap<(String, u32), PressTraceDiag>,
        key: (String, u32),
        trace: PressTraceDiag,
    ) {
        match traces.get(&key) {
            Some(existing) if press_trace_rank(existing) >= press_trace_rank(&trace) => {}
            _ => {
                traces.insert(key, trace);
            }
        }
    }

    #[cfg(feature = "sim")]
    fn press_trace_rank(trace: &PressTraceDiag) -> u8 {
        let mut rank = 0;
        if trace.coalesced_hit {
            rank += 32;
        }
        if !trace.emitted_raw_frames.is_empty() {
            rank += 16;
        }
        if trace.selected {
            rank += 8;
        }
        if trace.legal_press_candidates > 0 {
            rank += 4;
        }
        if trace.raw_press_candidates > 0 {
            rank += 2;
        }
        if !trace.injected_frames.is_empty() {
            rank += 1;
        }
        rank
    }

    #[cfg(feature = "sim")]
    fn confidence_diag(output: &SolveOutput) -> ConfidenceDiag {
        let mut diag = ConfidenceDiag::default();
        for timeline in &output.timelines {
            for sample in &timeline.samples {
                diag.sample_confidences.push(sample.pitch.confidence);
                if sample.pitch.flags.contains(AmbiguityFlags::LOW_MARGIN) {
                    diag.sample_low_margin += 1;
                }
                if sample.pitch.flags.contains(AmbiguityFlags::LONG_GAP) {
                    diag.sample_long_gap += 1;
                }
                if sample
                    .pitch
                    .flags
                    .contains(AmbiguityFlags::SURFACE_PROXIMITY)
                {
                    diag.sample_surface += 1;
                }
                if sample
                    .pitch
                    .flags
                    .intersects(AmbiguityFlags::CAR_PROXIMITY | AmbiguityFlags::COLLISION_SUSPECTED)
                {
                    diag.sample_car_or_collision += 1;
                }
            }
            for segment in &timeline.segments {
                diag.segment_confidences.push(segment.confidence);
            }
            for event in &timeline.events {
                diag.event_confidences.push(event.confidence);
                if event.flags.contains(AmbiguityFlags::LOW_MARGIN) {
                    diag.event_low_margin += 1;
                }
            }
        }
        diag
    }

    #[cfg(feature = "sim")]
    fn nearest_arena_surface_margin(pos: [f32; 3]) -> f32 {
        let ax = pos[0].abs();
        let ay = pos[1].abs();
        [
            pos[2] - DIAG_SURFACE_FLOOR_Z,
            DIAG_SURFACE_CEILING_Z - pos[2],
            DIAG_SURFACE_SIDE_WALL_X - ax,
            DIAG_SURFACE_BACK_WALL_Y - ay,
            DIAG_SURFACE_CORNER_SUM - (ax + ay),
        ]
        .into_iter()
        .fold(f32::INFINITY, f32::min)
    }

    #[cfg(feature = "sim")]
    fn min_other_car_distance(
        series: &ReplaySeries,
        player_index: usize,
        start_frame: u32,
        end_frame: u32,
    ) -> f32 {
        let mut min_distance = f32::INFINITY;
        for frame in start_frame..=end_frame {
            let frame = frame as usize;
            let Some(pos) = series.players[player_index].frames.pos.get(frame).copied() else {
                continue;
            };
            for (other_index, other) in series.players.iter().enumerate() {
                if other_index == player_index {
                    continue;
                }
                if let Some(other_pos) = other.frames.pos.get(frame).copied() {
                    min_distance = min_distance.min(norm(diff(pos, other_pos)));
                }
            }
        }
        if min_distance.is_finite() {
            min_distance
        } else {
            f32::NAN
        }
    }

    #[cfg(feature = "sim")]
    fn legal_press_window_frames() -> u32 {
        ((crate::consts::JUMP_MAX_TIME + crate::consts::DOUBLEJUMP_MAX_DELAY) * 30.0).ceil() as u32
            + 1
    }

    #[cfg(feature = "sim")]
    fn press_in_window(frames: Option<&BTreeSet<u32>>, end_frame: u32) -> bool {
        let Some(frames) = frames else {
            return false;
        };
        let start = end_frame.saturating_sub(legal_press_window_frames());
        frames.range(start..=end_frame).next().is_some()
    }

    #[cfg(feature = "sim")]
    fn solved_press_in_window(
        frames: &BTreeMap<(String, u32), ()>,
        player_id: &str,
        end_frame: u32,
    ) -> bool {
        let start = end_frame.saturating_sub(legal_press_window_frames());
        (start..=end_frame).any(|frame| frames.contains_key(&(player_id.to_string(), frame)))
    }

    #[cfg(feature = "sim")]
    fn tracker_state(tracker: &CarTracker) -> String {
        format!(
            "contact={:?};jump={:?};second={:?}",
            tracker.contact, tracker.jump, tracker.second
        )
    }

    #[cfg(feature = "sim")]
    fn candidate_event_is_flip(event: &CandidateEvent) -> bool {
        matches!(
            event,
            CandidateEvent::DoubleJump | CandidateEvent::Dodge { .. } | CandidateEvent::Stall
        )
    }

    #[cfg(feature = "sim")]
    fn candidate_event_name(event: CandidateEvent) -> &'static str {
        match event {
            CandidateEvent::JumpPress => "JumpPress",
            CandidateEvent::JumpRelease => "JumpRelease",
            CandidateEvent::DoubleJump => "DoubleJump",
            CandidateEvent::Dodge { .. } => "Dodge",
            CandidateEvent::Stall => "Stall",
        }
    }

    #[cfg(feature = "sim")]
    fn print_hallucination_summary(replay: &str, hallucinations: &[HallucinationDiag]) {
        let full = hallucinations
            .iter()
            .filter(|diag| diag.coverage_label == "full_component_stream")
            .count();
        let sparse_or_absent = hallucinations.len().saturating_sub(full);
        let car_prox = hallucinations
            .iter()
            .filter(|diag| diag.car_proximity)
            .count();
        let near_surface = hallucinations
            .iter()
            .filter(|diag| diag.surface_margin <= DIAG_SURFACE_NEAR_UU)
            .count();
        let near_car = hallucinations
            .iter()
            .filter(|diag| diag.min_car_distance <= 350.0)
            .count();
        println!(
            "wp7c_hallucination_summary,replay={},count={},full_component_stream={},sparse_or_absent={},sparse_or_absent_share={:.3},car_proximity={},near_surface={},near_car={},margin_p50={:.3},margin_p68={:.3},margin_p90={:.3},surface_margin_p10={:.3},surface_margin_p50={:.3},surface_margin_p90={:.3},min_car_p10={:.3},min_car_p50={:.3},min_car_p90={:.3},planar_p50={:.3},ang_p50={:.3}",
            replay,
            hallucinations.len(),
            full,
            sparse_or_absent,
            recall(sparse_or_absent, hallucinations.len()),
            car_prox,
            near_surface,
            near_car,
            percentile(hallucinations.iter().map(|diag| diag.margin).collect(), 0.50),
            percentile(hallucinations.iter().map(|diag| diag.margin).collect(), 0.68),
            percentile(hallucinations.iter().map(|diag| diag.margin).collect(), 0.90),
            percentile(
                hallucinations
                    .iter()
                    .map(|diag| f64::from(diag.surface_margin))
                    .collect(),
                0.10,
            ),
            percentile(
                hallucinations
                    .iter()
                    .map(|diag| f64::from(diag.surface_margin))
                    .collect(),
                0.50,
            ),
            percentile(
                hallucinations
                    .iter()
                    .map(|diag| f64::from(diag.surface_margin))
                    .collect(),
                0.90,
            ),
            percentile(
                hallucinations
                    .iter()
                    .map(|diag| f64::from(diag.min_car_distance))
                    .collect(),
                0.10,
            ),
            percentile(
                hallucinations
                    .iter()
                    .map(|diag| f64::from(diag.min_car_distance))
                    .collect(),
                0.50,
            ),
            percentile(
                hallucinations
                    .iter()
                    .map(|diag| f64::from(diag.min_car_distance))
                    .collect(),
                0.90,
            ),
            percentile(
                hallucinations
                    .iter()
                    .map(|diag| f64::from(diag.planar_delta))
                    .collect(),
                0.50,
            ),
            percentile(
                hallucinations
                    .iter()
                    .map(|diag| f64::from(diag.ang_delta))
                    .collect(),
                0.50,
            ),
        );
        let mut coverage = BTreeMap::new();
        for diag in hallucinations {
            *coverage.entry(diag.coverage_label).or_insert(0usize) += 1;
        }
        for (label, count) in coverage {
            println!(
                "wp7c_hallucination_coverage,replay={replay},coverage={label},count={count},share={:.3}",
                recall(count, hallucinations.len()),
            );
        }
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
                    let state_k = car_state(
                        player,
                        start_frame,
                        interval.tick_range.0,
                        &interval_tracker,
                    );
                    let observed_end =
                        car_state(player, end_frame, interval.tick_range.1, &interval_tracker);
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
                        edges_for_interval_with_implied_liftoff(
                            player,
                            &hints,
                            segment,
                            start_frame,
                            end_frame,
                            interval,
                            &config,
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

    #[cfg(feature = "sim")]
    fn candidate_has_jump_press(candidate: &Candidate) -> bool {
        candidate
            .actions
            .iter()
            .any(|action| action.event == CandidateEvent::JumpPress)
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
        } else if candidate
            .actions
            .iter()
            .any(|action| action.event == CandidateEvent::JumpPress)
        {
            "JumpPress"
        } else if candidate
            .actions
            .iter()
            .any(|action| action.event == CandidateEvent::JumpRelease)
        {
            "JumpRelease"
        } else {
            "Other"
        }
    }

    #[cfg(feature = "sim")]
    fn print_press_trace_summary(replay: &str, traces: &[PressTraceDiag]) {
        let injected = traces
            .iter()
            .filter(|trace| !trace.injected_frames.is_empty())
            .count();
        let raw_candidate = traces
            .iter()
            .filter(|trace| trace.raw_press_candidates > 0)
            .count();
        let legal_candidate = traces
            .iter()
            .filter(|trace| trace.legal_press_candidates > 0)
            .count();
        let selected = traces.iter().filter(|trace| trace.selected).count();
        let emitted = traces
            .iter()
            .filter(|trace| !trace.emitted_raw_frames.is_empty())
            .count();
        let coalesced_hits = traces.iter().filter(|trace| trace.coalesced_hit).count();
        println!(
            "wp7c_press_trace_summary,replay={},known={},injected={},raw_candidate={},legal_candidate={},selected={},emitted_near_target={},coalesced_hits={}",
            replay,
            traces.len(),
            injected,
            raw_candidate,
            legal_candidate,
            selected,
            emitted,
            coalesced_hits,
        );

        let mut rejections = BTreeMap::new();
        for trace in traces {
            *rejections.entry(trace.rejection).or_insert(0usize) += 1;
        }
        for (reason, count) in rejections {
            println!(
                "wp7c_press_trace_rejection,replay={},reason={},count={},share={:.3}",
                replay,
                reason,
                count,
                recall(count, traces.len()),
            );
        }
        for trace in traces {
            println!(
                "wp7c_press_trace,replay={},player={},frames={}..{},injected_frames={:?},raw_candidates={},legal_candidates={},selected={},winner={},rejection={},emitted_raw_frames={:?},coalesced_hit={}",
                replay,
                trace.player_id,
                trace.start_frame,
                trace.end_frame,
                trace.injected_frames,
                trace.raw_press_candidates,
                trace.legal_press_candidates,
                trace.selected,
                trace.winner,
                trace.rejection,
                trace.emitted_raw_frames,
                trace.coalesced_hit,
            );
        }
    }

    #[cfg(feature = "sim")]
    fn print_confidence_summary(replay: &str, diag: &ConfidenceDiag) {
        let sample_le_03 = diag
            .sample_confidences
            .iter()
            .filter(|confidence| **confidence <= 0.3)
            .count();
        let sample_le_05 = diag
            .sample_confidences
            .iter()
            .filter(|confidence| **confidence <= 0.5)
            .count();
        let segment_le_03 = diag
            .segment_confidences
            .iter()
            .filter(|confidence| **confidence <= 0.3)
            .count();
        let segment_le_05 = diag
            .segment_confidences
            .iter()
            .filter(|confidence| **confidence <= 0.5)
            .count();
        let event_le_03 = diag
            .event_confidences
            .iter()
            .filter(|confidence| **confidence <= 0.3)
            .count();
        println!(
            "wp7c_confidence_summary,replay={},samples={},sample_p10={:.3},sample_p50={:.3},sample_p90={:.3},sample_le_0_3={},sample_le_0_5={},sample_low_margin={},sample_long_gap={},sample_surface={},sample_car_or_collision={},segments={},segment_p10={:.3},segment_p50={:.3},segment_p90={:.3},segment_le_0_3={},segment_le_0_5={},events={},event_le_0_3={},event_low_margin={}",
            replay,
            diag.sample_confidences.len(),
            percentile(
                diag.sample_confidences
                    .iter()
                    .map(|confidence| f64::from(*confidence))
                    .collect(),
                0.10,
            ),
            percentile(
                diag.sample_confidences
                    .iter()
                    .map(|confidence| f64::from(*confidence))
                    .collect(),
                0.50,
            ),
            percentile(
                diag.sample_confidences
                    .iter()
                    .map(|confidence| f64::from(*confidence))
                    .collect(),
                0.90,
            ),
            sample_le_03,
            sample_le_05,
            diag.sample_low_margin,
            diag.sample_long_gap,
            diag.sample_surface,
            diag.sample_car_or_collision,
            diag.segment_confidences.len(),
            percentile(
                diag.segment_confidences
                    .iter()
                    .map(|confidence| f64::from(*confidence))
                    .collect(),
                0.10,
            ),
            percentile(
                diag.segment_confidences
                    .iter()
                    .map(|confidence| f64::from(*confidence))
                    .collect(),
                0.50,
            ),
            percentile(
                diag.segment_confidences
                    .iter()
                    .map(|confidence| f64::from(*confidence))
                    .collect(),
                0.90,
            ),
            segment_le_03,
            segment_le_05,
            diag.event_confidences.len(),
            event_le_03,
            diag.event_low_margin,
        );
        print_confidence_hist(replay, "sample", &diag.sample_confidences);
        print_confidence_hist(replay, "segment", &diag.segment_confidences);
        print_confidence_hist(replay, "event", &diag.event_confidences);
    }

    #[cfg(feature = "sim")]
    fn print_confidence_hist(replay: &str, kind: &str, values: &[f32]) {
        let mut bins = [0usize; 10];
        for value in values {
            let idx = ((*value * 10.0).floor() as usize).min(9);
            bins[idx] += 1;
        }
        for (idx, count) in bins.iter().enumerate() {
            println!(
                "wp7c_confidence_hist,replay={},kind={},bin={:.1}-{:.1},count={},share={:.3}",
                replay,
                kind,
                idx as f32 / 10.0,
                (idx + 1) as f32 / 10.0,
                count,
                recall(*count, values.len()),
            );
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
