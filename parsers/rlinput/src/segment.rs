//! Per-player contact-free segmentation and coverage statistics.
//!
//! Intervals are addressed by their terminating replay frame, matching
//! [`crate::lattice::LatticeInterval::frame_index`].

use crate::consts::{
    SURFACE_BACK_WALL_Y, SURFACE_CEILING_Z, SURFACE_CORNER_SUM, SURFACE_FLOOR_Z,
    SURFACE_SIDE_WALL_X, SURFACE_TRANSITION_DIST, SURFACE_TRANSITION_Z,
};
use crate::lattice::{build_segment_lattice, SegmentLattice};
use crate::model::{PlayerSeries, ReplaySeries};
use crate::timeline::{
    AmbiguityFlags, BoundaryCause, CoverageReport, ExclusionBreakdown, SegmentSummary,
};
use serde::{Deserialize, Serialize};

const BALL_PROXIMITY_UU: f32 = 190.0;
// Design §2.1 does not specify a numeric kink threshold; mirror the §2.2
// residual threshold until the solver owns residual-driven upgrades.
const BALL_VELOCITY_KINK_UU_PER_S: f32 = 150.0;
const CAR_CONTACT_UU: f32 = 170.0;
const CAR_PROXIMITY_UU: f32 = 350.0;
const RESPAWN_TELEPORT_UU: f32 = 500.0;

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct SegmentationOutput {
    pub players: Vec<PlayerSegmentation>,
    pub coverage: CoverageReport,
    pub boundary_counts_by_cause: Vec<BoundaryCount>,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct PlayerSegmentation {
    pub player_id: String,
    pub segments: Vec<Segment>,
    pub interval_flags: Vec<IntervalFlags>,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct Segment {
    pub summary: SegmentSummary,
    pub kind: SegmentKind,
    /// Terminating replay-frame range, `[start, end)`.
    pub frame_span: (u32, u32),
    pub lattice: SegmentLattice,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
pub enum SegmentKind {
    Air,
    Ground,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct IntervalFlags {
    /// Terminating replay frame for this observed interval.
    pub frame_index: u32,
    pub flags: AmbiguityFlags,
    pub causes: Vec<BoundaryCause>,
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
pub struct BoundaryCount {
    pub cause: BoundaryCause,
    pub count: u64,
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
pub struct RetroactiveSplit {
    pub player_id: String,
    pub interval_terminating_frame: u32,
    pub cause: BoundaryCause,
}

/// Re-entry point for solver-driven retroactive contact upgrades.
///
/// Design §2.2(5) is intentionally outside WP2: the solver owns the velocity
/// residual test. When it upgrades an interval, call this helper for each
/// affected player and pass the returned splits to
/// [`segment_replay_with_splits_and_confidences`]. The frame index is the
/// interval-terminating frame on the 120 Hz lattice contract.
pub fn split_segment_at(
    player_id: impl Into<String>,
    interval_terminating_frame: u32,
) -> RetroactiveSplit {
    RetroactiveSplit {
        player_id: player_id.into(),
        interval_terminating_frame,
        cause: BoundaryCause::CarContactSuspected,
    }
}

pub fn segment_replay(series: &ReplaySeries) -> SegmentationOutput {
    segment_replay_with_splits_and_confidences(series, &[], 0.7, |_player_id, _segment| None)
}

pub fn segment_replay_with_confidences<F>(
    series: &ReplaySeries,
    confidence_threshold: f32,
    confidence: F,
) -> SegmentationOutput
where
    F: FnMut(&str, &Segment) -> Option<f32>,
{
    segment_replay_with_splits_and_confidences(series, &[], confidence_threshold, confidence)
}

pub fn segment_replay_with_splits_and_confidences<F>(
    series: &ReplaySeries,
    extra_splits: &[RetroactiveSplit],
    confidence_threshold: f32,
    mut confidence: F,
) -> SegmentationOutput
where
    F: FnMut(&str, &Segment) -> Option<f32>,
{
    let mut states_by_player: Vec<Vec<IntervalState>> = series
        .players
        .iter()
        .map(|player| vec![IntervalState::default(); player_frame_count(player)])
        .collect();

    detect_series_boundaries(series, extra_splits, &mut states_by_player);

    let mut players = Vec::with_capacity(series.players.len());
    let mut excluded_by_cause: Vec<(BoundaryCause, f64)> = Vec::new();
    let mut boundary_counts: Vec<(BoundaryCause, u64)> = Vec::new();

    for (player_index, player) in series.players.iter().enumerate() {
        let mut built = build_player_segments(player, series, &states_by_player[player_index]);
        for segment in &mut built.segmentation.segments {
            segment.summary.confidence =
                confidence(&built.segmentation.player_id, segment).unwrap_or(0.0);
        }
        merge_duration_breakdown(&mut excluded_by_cause, built.excluded_by_cause);
        merge_count_breakdown(&mut boundary_counts, built.boundary_counts);
        players.push(built.segmentation);
    }

    let coverage = build_coverage_report(&players, confidence_threshold, excluded_by_cause);
    SegmentationOutput {
        players,
        coverage,
        boundary_counts_by_cause: ordered_counts(boundary_counts),
    }
}

#[derive(Clone, Debug, Default)]
struct IntervalState {
    split_before: Vec<BoundaryCause>,
    exclude_causes: Vec<BoundaryCause>,
    flags: AmbiguityFlags,
}

struct BuiltPlayer {
    segmentation: PlayerSegmentation,
    excluded_by_cause: Vec<(BoundaryCause, f64)>,
    boundary_counts: Vec<(BoundaryCause, u64)>,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum IntervalKind {
    Air,
    Ground,
    Excluded,
}

fn detect_series_boundaries(
    series: &ReplaySeries,
    extra_splits: &[RetroactiveSplit],
    states_by_player: &mut [Vec<IntervalState>],
) {
    for (player_index, player) in series.players.iter().enumerate() {
        detect_player_boundaries(series, player, &mut states_by_player[player_index]);
    }
    detect_car_contact_boundaries(series, states_by_player);
    for split in extra_splits {
        if let Some((player_index, _)) = series
            .players
            .iter()
            .enumerate()
            .find(|(_, player)| player.player_id == split.player_id)
        {
            if let Some(state) =
                states_by_player[player_index].get_mut(split.interval_terminating_frame as usize)
            {
                add_cause(&mut state.exclude_causes, split.cause.clone());
                state.flags |= AmbiguityFlags::COLLISION_SUSPECTED;
            }
        }
    }
}

fn detect_player_boundaries(
    series: &ReplaySeries,
    player: &PlayerSeries,
    states: &mut [IntervalState],
) {
    let frame_count = states.len();
    if frame_count < 2 {
        return;
    }
    let times = frame_times(series, frame_count);

    for event in &series.touch_events {
        if event.player_id == player.player_id {
            if let Some(frame) = event_interval(event.frame_index, event.t, &times, frame_count) {
                add_exclusion(
                    states,
                    frame,
                    BoundaryCause::BallTouch,
                    AmbiguityFlags::empty(),
                );
            }
        }
    }

    for event in &series.demo_events {
        if event.victim_id == player.player_id
            || event.attacker_id.as_ref() == Some(&player.player_id)
        {
            if let Some(frame) = event_interval(event.frame_index, event.t, &times, frame_count) {
                add_exclusion(
                    states,
                    frame,
                    BoundaryCause::Demolition,
                    AmbiguityFlags::empty(),
                );
            }
        }
    }

    for marker in &series.kickoff_markers {
        if let Some(frame) = event_interval(marker.frame_index, marker.t, &times, frame_count) {
            add_exclusion(
                states,
                frame,
                BoundaryCause::KickoffReset,
                AmbiguityFlags::empty(),
            );
        }
    }

    for frame in 1..frame_count {
        let prev = frame - 1;
        if is_demolished(player, frame) {
            add_exclusion(
                states,
                frame,
                BoundaryCause::Demolition,
                AmbiguityFlags::empty(),
            );
        }
        if !is_demolished(player, frame) && is_demolished(player, prev) {
            add_exclusion(
                states,
                frame,
                BoundaryCause::Respawn,
                AmbiguityFlags::empty(),
            );
        }
        if distance(player.frames.pos[prev], player.frames.pos[frame]) > RESPAWN_TELEPORT_UU {
            add_exclusion(
                states,
                frame,
                BoundaryCause::Respawn,
                AmbiguityFlags::empty(),
            );
        }

        let was_ground_or_sleeping = is_on_ground(player, prev) || is_sleeping(player, prev);
        let is_ground_or_sleeping = is_on_ground(player, frame) || is_sleeping(player, frame);
        if was_ground_or_sleeping != is_ground_or_sleeping {
            add_cause(
                &mut states[frame].split_before,
                if was_ground_or_sleeping {
                    BoundaryCause::Liftoff
                } else {
                    BoundaryCause::Landing
                },
            );
        }

        if is_surface_excluded(player, frame) {
            add_exclusion(
                states,
                frame,
                BoundaryCause::SurfaceProximity,
                AmbiguityFlags::SURFACE_PROXIMITY,
            );
        }

        detect_ball_proximity(series, player, states, frame);
    }
}

fn detect_ball_proximity(
    series: &ReplaySeries,
    player: &PlayerSeries,
    states: &mut [IntervalState],
    frame: usize,
) {
    if frame >= series.ball.pos.len() || frame >= series.ball.vel.len() {
        return;
    }
    let prev = frame - 1;
    let dt = delta_for(series, frame);
    let d_min = hermite_min_distance(
        HermiteMotion {
            p0: player.frames.pos[prev],
            v0: player.frames.vel[prev],
            p1: player.frames.pos[frame],
            v1: player.frames.vel[frame],
        },
        HermiteMotion {
            p0: series.ball.pos[prev],
            v0: series.ball.vel[prev],
            p1: series.ball.pos[frame],
            v1: series.ball.vel[frame],
        },
        dt,
    );
    if d_min >= BALL_PROXIMITY_UU {
        return;
    }

    states[frame].flags |= AmbiguityFlags::BALL_PROXIMITY;
    if distance(player.frames.vel[prev], player.frames.vel[frame]) > BALL_VELOCITY_KINK_UU_PER_S {
        add_exclusion(
            states,
            frame,
            BoundaryCause::BallProximity,
            AmbiguityFlags::BALL_PROXIMITY,
        );
    }
}

fn detect_car_contact_boundaries(
    series: &ReplaySeries,
    states_by_player: &mut [Vec<IntervalState>],
) {
    for left_index in 0..series.players.len() {
        for right_index in (left_index + 1)..series.players.len() {
            let left = &series.players[left_index];
            let right = &series.players[right_index];
            let frame_count = player_frame_count(left).min(player_frame_count(right));
            for frame in 1..frame_count {
                let dt = delta_for(series, frame);
                let d_min = hermite_min_distance(
                    HermiteMotion {
                        p0: left.frames.pos[frame - 1],
                        v0: left.frames.vel[frame - 1],
                        p1: left.frames.pos[frame],
                        v1: left.frames.vel[frame],
                    },
                    HermiteMotion {
                        p0: right.frames.pos[frame - 1],
                        v0: right.frames.vel[frame - 1],
                        p1: right.frames.pos[frame],
                        v1: right.frames.vel[frame],
                    },
                    dt,
                );
                if d_min < CAR_CONTACT_UU {
                    add_exclusion(
                        &mut states_by_player[left_index],
                        frame,
                        BoundaryCause::CarContactSuspected,
                        AmbiguityFlags::COLLISION_SUSPECTED,
                    );
                    add_exclusion(
                        &mut states_by_player[right_index],
                        frame,
                        BoundaryCause::CarContactSuspected,
                        AmbiguityFlags::COLLISION_SUSPECTED,
                    );
                } else if d_min < CAR_PROXIMITY_UU {
                    states_by_player[left_index][frame].flags |= AmbiguityFlags::CAR_PROXIMITY;
                    states_by_player[right_index][frame].flags |= AmbiguityFlags::CAR_PROXIMITY;
                }
            }
        }
    }
}

fn build_player_segments(
    player: &PlayerSeries,
    series: &ReplaySeries,
    states: &[IntervalState],
) -> BuiltPlayer {
    let mut segments = Vec::new();
    let mut interval_flags = Vec::new();
    let mut excluded_by_cause: Vec<(BoundaryCause, f64)> = Vec::new();
    let mut boundary_counts: Vec<(BoundaryCause, u64)> = Vec::new();
    let mut pending_left_causes = vec![BoundaryCause::StreamEdge];
    let mut open: Option<OpenSegment> = None;

    add_count(&mut boundary_counts, BoundaryCause::StreamEdge, 1);

    for (frame, state) in states.iter().enumerate().skip(1) {
        if !state.flags.is_empty()
            || !state.split_before.is_empty()
            || !state.exclude_causes.is_empty()
        {
            interval_flags.push(IntervalFlags {
                frame_index: frame as u32,
                flags: state.flags,
                causes: ordered_causes(union_causes(&state.split_before, &state.exclude_causes)),
            });
        }
        for cause in union_causes(&state.split_before, &state.exclude_causes) {
            add_count(&mut boundary_counts, cause, 1);
        }

        if !state.split_before.is_empty() {
            close_open(&mut open, &mut segments, series, &state.split_before);
            pending_left_causes = merge_causes(pending_left_causes, state.split_before.clone());
        }

        if !state.exclude_causes.is_empty() {
            close_open(&mut open, &mut segments, series, &state.exclude_causes);
            let duration = f64::from(delta_for(series, frame));
            for cause in &state.exclude_causes {
                add_duration(&mut excluded_by_cause, cause.clone(), duration);
            }
            pending_left_causes = merge_causes(pending_left_causes, state.exclude_causes.clone());
            continue;
        }

        let kind = interval_kind(player, frame);
        if kind == IntervalKind::Excluded {
            continue;
        }
        let segment_kind = match kind {
            IntervalKind::Air => SegmentKind::Air,
            IntervalKind::Ground => SegmentKind::Ground,
            IntervalKind::Excluded => unreachable!("excluded intervals are skipped"),
        };

        if open
            .as_ref()
            .is_some_and(|segment| segment.kind != segment_kind)
        {
            let cause = if segment_kind == SegmentKind::Air {
                BoundaryCause::Liftoff
            } else {
                BoundaryCause::Landing
            };
            let causes = vec![cause.clone()];
            close_open(&mut open, &mut segments, series, &causes);
            pending_left_causes = merge_causes(pending_left_causes, causes);
            add_count(&mut boundary_counts, cause, 1);
        }

        if open.is_none() {
            open = Some(OpenSegment {
                id: segments.len() as u32,
                start_frame: frame as u32,
                end_frame: frame as u32 + 1,
                kind: segment_kind,
                left_causes: std::mem::take(&mut pending_left_causes),
            });
        } else if let Some(segment) = &mut open {
            segment.end_frame = frame as u32 + 1;
        }
    }

    close_open(
        &mut open,
        &mut segments,
        series,
        &[BoundaryCause::StreamEdge],
    );
    if !segments.is_empty() {
        add_count(&mut boundary_counts, BoundaryCause::StreamEdge, 1);
    }

    BuiltPlayer {
        segmentation: PlayerSegmentation {
            player_id: player.player_id.clone(),
            segments,
            interval_flags,
        },
        excluded_by_cause,
        boundary_counts,
    }
}

struct OpenSegment {
    id: u32,
    start_frame: u32,
    end_frame: u32,
    kind: SegmentKind,
    left_causes: Vec<BoundaryCause>,
}

fn close_open(
    open: &mut Option<OpenSegment>,
    segments: &mut Vec<Segment>,
    series: &ReplaySeries,
    right_causes: &[BoundaryCause],
) {
    let Some(open_segment) = open.take() else {
        return;
    };
    let deltas = deltas_for_span(
        series,
        open_segment.start_frame as usize,
        open_segment.end_frame as usize,
    );
    let lattice = build_segment_lattice(open_segment.start_frame, &deltas);
    let tick_span = lattice
        .intervals
        .first()
        .zip(lattice.intervals.last())
        .map(|(first, last)| (first.tick_range.0, last.tick_range.1))
        .unwrap_or((0, 0));
    let causes = ordered_causes(merge_causes(
        open_segment.left_causes,
        right_causes.to_vec(),
    ));
    segments.push(Segment {
        summary: SegmentSummary {
            id: open_segment.id,
            tick_span,
            boundary_causes: causes,
            confidence: 0.0,
        },
        kind: open_segment.kind,
        frame_span: (open_segment.start_frame, open_segment.end_frame),
        lattice,
    });
}

fn build_coverage_report(
    players: &[PlayerSegmentation],
    confidence_threshold: f32,
    excluded_by_cause: Vec<(BoundaryCause, f64)>,
) -> CoverageReport {
    let mut air_segments = 0u64;
    let mut air_segments_confident = 0u64;
    let mut air_duration = 0.0f64;
    let mut confident_air_duration = 0.0f64;

    for player in players {
        for segment in &player.segments {
            if segment.kind != SegmentKind::Air {
                continue;
            }
            air_segments += 1;
            let duration = segment
                .lattice
                .intervals
                .last()
                .map(|interval| interval.time_range.1)
                .unwrap_or(0.0);
            air_duration += duration;
            if segment.summary.confidence >= confidence_threshold {
                air_segments_confident += 1;
                confident_air_duration += duration;
            }
        }
    }

    CoverageReport {
        air_segments,
        air_segments_confident,
        coverage: if air_segments == 0 {
            0.0
        } else {
            air_segments_confident as f32 / air_segments as f32
        },
        duration_weighted_coverage: if air_duration == 0.0 {
            0.0
        } else {
            (confident_air_duration / air_duration) as f32
        },
        excluded_player_seconds_by_cause: ordered_durations(excluded_by_cause),
    }
}

fn interval_kind(player: &PlayerSeries, frame: usize) -> IntervalKind {
    if is_demolished(player, frame) || is_surface_excluded(player, frame) {
        IntervalKind::Excluded
    } else if is_air_frame(player, frame) {
        IntervalKind::Air
    } else {
        IntervalKind::Ground
    }
}

fn is_air_frame(player: &PlayerSeries, frame: usize) -> bool {
    !is_on_ground(player, frame)
        && !is_sleeping(player, frame)
        && !is_demolished(player, frame)
        && !in_surface_proximity(player.frames.pos[frame])
}

fn is_surface_excluded(player: &PlayerSeries, frame: usize) -> bool {
    !is_on_ground(player, frame)
        && !is_sleeping(player, frame)
        && !is_demolished(player, frame)
        && in_surface_proximity(player.frames.pos[frame])
}

fn in_surface_proximity([x, y, z]: [f32; 3]) -> bool {
    let ax = x.abs();
    let ay = y.abs();
    !(SURFACE_FLOOR_Z..=SURFACE_CEILING_Z).contains(&z)
        || ax > SURFACE_SIDE_WALL_X
        || ay > SURFACE_BACK_WALL_Y
        || ax + ay > SURFACE_CORNER_SUM
        || (z < SURFACE_TRANSITION_Z
            && (4096.0 - ax < SURFACE_TRANSITION_DIST || 5120.0 - ay < SURFACE_TRANSITION_DIST))
}

fn player_frame_count(player: &PlayerSeries) -> usize {
    [
        player.frames.pos.len(),
        player.frames.vel.len(),
        player.frames.quat_xyzw.len(),
        player.frames.ang_vel.len(),
        player.frames.on_ground.len(),
        player.frames.sleeping.len(),
        player.frames.demolished.len(),
    ]
    .into_iter()
    .min()
    .unwrap_or(0)
}

fn is_on_ground(player: &PlayerSeries, frame: usize) -> bool {
    player.frames.on_ground.get(frame).copied().unwrap_or(true)
}

fn is_sleeping(player: &PlayerSeries, frame: usize) -> bool {
    player.frames.sleeping.get(frame).copied().unwrap_or(false)
}

fn is_demolished(player: &PlayerSeries, frame: usize) -> bool {
    player
        .frames
        .demolished
        .get(frame)
        .copied()
        .unwrap_or(false)
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

fn deltas_for_span(series: &ReplaySeries, start: usize, end: usize) -> Vec<f32> {
    (start..end).map(|frame| delta_for(series, frame)).collect()
}

fn frame_times(series: &ReplaySeries, frame_count: usize) -> Vec<f64> {
    let mut out = vec![0.0; frame_count];
    for frame in 1..frame_count {
        out[frame] = out[frame - 1] + f64::from(delta_for(series, frame));
    }
    out
}

fn event_interval(
    frame_index: Option<u32>,
    t: f64,
    times: &[f64],
    frame_count: usize,
) -> Option<usize> {
    if frame_count < 2 {
        return None;
    }
    if let Some(frame) = frame_index {
        return Some((frame as usize).clamp(1, frame_count - 1));
    }
    times
        .iter()
        .enumerate()
        .skip(1)
        .find_map(|(frame, frame_t)| (t <= *frame_t).then_some(frame))
        .or(Some(frame_count - 1))
}

fn add_exclusion(
    states: &mut [IntervalState],
    frame: usize,
    cause: BoundaryCause,
    flags: AmbiguityFlags,
) {
    if let Some(state) = states.get_mut(frame) {
        add_cause(&mut state.exclude_causes, cause);
        state.flags |= flags;
    }
}

fn add_cause(causes: &mut Vec<BoundaryCause>, cause: BoundaryCause) {
    if !causes.contains(&cause) {
        causes.push(cause);
    }
}

fn merge_causes(mut left: Vec<BoundaryCause>, right: Vec<BoundaryCause>) -> Vec<BoundaryCause> {
    for cause in right {
        add_cause(&mut left, cause);
    }
    left
}

fn union_causes(left: &[BoundaryCause], right: &[BoundaryCause]) -> Vec<BoundaryCause> {
    merge_causes(left.to_vec(), right.to_vec())
}

fn cause_rank(cause: &BoundaryCause) -> usize {
    match cause {
        BoundaryCause::BallTouch => 0,
        BoundaryCause::BallProximity => 1,
        BoundaryCause::CarContactSuspected => 2,
        BoundaryCause::Demolition => 3,
        BoundaryCause::Respawn => 4,
        BoundaryCause::KickoffReset => 5,
        BoundaryCause::Liftoff => 6,
        BoundaryCause::Landing => 7,
        BoundaryCause::SurfaceProximity => 8,
        BoundaryCause::StreamEdge => 9,
    }
}

fn ordered_causes(mut causes: Vec<BoundaryCause>) -> Vec<BoundaryCause> {
    causes.sort_by_key(cause_rank);
    causes
}

fn add_duration(items: &mut Vec<(BoundaryCause, f64)>, cause: BoundaryCause, seconds: f64) {
    if let Some((_, total)) = items.iter_mut().find(|(existing, _)| *existing == cause) {
        *total += seconds;
    } else {
        items.push((cause, seconds));
    }
}

fn add_count(items: &mut Vec<(BoundaryCause, u64)>, cause: BoundaryCause, count: u64) {
    if let Some((_, total)) = items.iter_mut().find(|(existing, _)| *existing == cause) {
        *total += count;
    } else {
        items.push((cause, count));
    }
}

fn merge_duration_breakdown(
    target: &mut Vec<(BoundaryCause, f64)>,
    source: Vec<(BoundaryCause, f64)>,
) {
    for (cause, seconds) in source {
        add_duration(target, cause, seconds);
    }
}

fn merge_count_breakdown(
    target: &mut Vec<(BoundaryCause, u64)>,
    source: Vec<(BoundaryCause, u64)>,
) {
    for (cause, count) in source {
        add_count(target, cause, count);
    }
}

fn ordered_durations(items: Vec<(BoundaryCause, f64)>) -> Vec<ExclusionBreakdown> {
    let mut out: Vec<_> = items
        .into_iter()
        .map(|(cause, player_seconds)| ExclusionBreakdown {
            cause,
            player_seconds,
        })
        .collect();
    out.sort_by_key(|item| cause_rank(&item.cause));
    out
}

fn ordered_counts(items: Vec<(BoundaryCause, u64)>) -> Vec<BoundaryCount> {
    let mut out: Vec<_> = items
        .into_iter()
        .map(|(cause, count)| BoundaryCount { cause, count })
        .collect();
    out.sort_by_key(|item| cause_rank(&item.cause));
    out
}

#[derive(Clone, Copy)]
struct HermiteMotion {
    p0: [f32; 3],
    v0: [f32; 3],
    p1: [f32; 3],
    v1: [f32; 3],
}

fn hermite_min_distance(a: HermiteMotion, b: HermiteMotion, dt: f32) -> f32 {
    let ticks = (dt.max(0.0) * 120.0).round().max(1.0) as usize;
    (0..=ticks)
        .map(|tick| {
            let u = tick as f32 / ticks as f32;
            distance(
                hermite(a.p0, a.v0, a.p1, a.v1, dt, u),
                hermite(b.p0, b.v0, b.p1, b.v1, dt, u),
            )
        })
        .fold(f32::INFINITY, f32::min)
}

fn hermite(p0: [f32; 3], v0: [f32; 3], p1: [f32; 3], v1: [f32; 3], dt: f32, u: f32) -> [f32; 3] {
    let u2 = u * u;
    let u3 = u2 * u;
    let h00 = 2.0 * u3 - 3.0 * u2 + 1.0;
    let h10 = u3 - 2.0 * u2 + u;
    let h01 = -2.0 * u3 + 3.0 * u2;
    let h11 = u3 - u2;
    [
        h00 * p0[0] + h10 * dt * v0[0] + h01 * p1[0] + h11 * dt * v1[0],
        h00 * p0[1] + h10 * dt * v0[1] + h01 * p1[1] + h11 * dt * v1[1],
        h00 * p0[2] + h10 * dt * v0[2] + h01 * p1[2] + h11 * dt * v1[2],
    ]
}

fn distance(a: [f32; 3], b: [f32; 3]) -> f32 {
    let dx = a[0] - b[0];
    let dy = a[1] - b[1];
    let dz = a[2] - b[2];
    (dx * dx + dy * dy + dz * dz).sqrt()
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::model::{BallSeries, ComponentStream, Kinematics, PlayerSeries, ReplicatedChannels};

    fn player(
        id: &str,
        pos: Vec<[f32; 3]>,
        vel: Vec<[f32; 3]>,
        on_ground: Vec<bool>,
    ) -> PlayerSeries {
        let n = pos.len();
        PlayerSeries {
            player_id: id.to_string(),
            frames: Kinematics {
                pos,
                vel,
                quat_xyzw: vec![[0.0, 0.0, 0.0, 1.0]; n],
                ang_vel: vec![[0.0, 0.0, 0.0]; n],
                on_ground,
                sleeping: vec![false; n],
                demolished: vec![false; n],
            },
            replicated: ReplicatedChannels {
                throttle_raw: vec![128; n],
                steer_raw: vec![128; n],
                handbrake: vec![false; n],
                boost_amount_raw: vec![0; n],
                boost_active_raw: vec![false; n],
            },
            component: ComponentStream {
                jump_raw: vec![0; n],
                dodge_raw: vec![0; n],
                double_jump_raw: vec![0; n],
                boost_raw: vec![0; n],
                events: Vec::new(),
            },
        }
    }

    fn series(players: Vec<PlayerSeries>) -> ReplaySeries {
        let n = players.first().map(player_frame_count).unwrap_or(3);
        ReplaySeries {
            tick_rate: 120.0,
            build_bucket: "synthetic".to_string(),
            players,
            ball: BallSeries {
                pos: vec![[5000.0, 0.0, 100.0]; n],
                vel: vec![[0.0, 0.0, 0.0]; n],
            },
            deltas: {
                let mut deltas = vec![1.0 / 30.0; n];
                if let Some(first) = deltas.first_mut() {
                    *first = 0.0;
                }
                deltas
            },
            demo_events: Vec::new(),
            touch_events: Vec::new(),
            kickoff_markers: Vec::new(),
        }
    }

    fn one_player_series() -> ReplaySeries {
        series(vec![player(
            "p0",
            vec![[0.0, 0.0, 100.0], [10.0, 0.0, 100.0], [20.0, 0.0, 100.0]],
            vec![[0.0, 0.0, 0.0]; 3],
            vec![false; 3],
        )])
    }

    fn has_cause(output: &SegmentationOutput, cause: BoundaryCause) -> bool {
        output.players.iter().any(|player| {
            player
                .segments
                .iter()
                .any(|segment| segment.summary.boundary_causes.contains(&cause))
        })
    }

    #[test]
    fn ball_touch_is_hard_boundary() {
        let mut replay = one_player_series();
        replay.touch_events.push(crate::model::TouchEventIn {
            t: 1.0 / 30.0,
            frame_index: Some(1),
            player_id: "p0".to_string(),
            team: Some(0),
        });

        assert!(has_cause(
            &segment_replay(&replay),
            BoundaryCause::BallTouch
        ));
    }

    #[test]
    fn ball_proximity_with_velocity_kink_is_hard_boundary() {
        let mut replay = one_player_series();
        replay.players[0].frames.vel[1] = [200.0, 0.0, 0.0];
        replay.players[0].frames.vel[2] = [200.0, 0.0, 0.0];
        replay.ball.pos = vec![[30.0, 0.0, 100.0]; 3];

        assert!(has_cause(
            &segment_replay(&replay),
            BoundaryCause::BallProximity
        ));
    }

    #[test]
    fn hermite_car_contact_splits_when_mid_interval_distance_crosses_threshold() {
        let p0 = player(
            "p0",
            vec![[0.0, 0.0, 100.0], [400.0, 0.0, 100.0], [500.0, 0.0, 100.0]],
            vec![[0.0, 0.0, 0.0]; 3],
            vec![false; 3],
        );
        let p1 = player(
            "p1",
            vec![[400.0, 0.0, 100.0], [0.0, 0.0, 100.0], [-100.0, 0.0, 100.0]],
            vec![[0.0, 0.0, 0.0]; 3],
            vec![false; 3],
        );

        let output = segment_replay(&series(vec![p0, p1]));

        assert!(has_cause(&output, BoundaryCause::CarContactSuspected));
        assert_eq!(
            output
                .players
                .iter()
                .filter(|player| player.segments.iter().any(|segment| segment
                    .summary
                    .boundary_causes
                    .contains(&BoundaryCause::CarContactSuspected)))
                .count(),
            2
        );
    }

    #[test]
    fn hermite_car_near_miss_sets_proximity_flag_without_split() {
        let p0 = player(
            "p0",
            vec![[0.0, 0.0, 100.0], [100.0, 0.0, 100.0]],
            vec![[0.0, 0.0, 0.0]; 2],
            vec![false; 2],
        );
        let p1 = player(
            "p1",
            vec![[0.0, 250.0, 100.0], [100.0, 250.0, 100.0]],
            vec![[0.0, 0.0, 0.0]; 2],
            vec![false; 2],
        );

        let output = segment_replay(&series(vec![p0, p1]));

        assert!(!has_cause(&output, BoundaryCause::CarContactSuspected));
        assert!(output.players.iter().all(|player| player
            .interval_flags
            .iter()
            .any(|interval| interval.flags.contains(AmbiguityFlags::CAR_PROXIMITY))));
    }

    #[test]
    fn demolition_event_is_hard_boundary() {
        let mut replay = one_player_series();
        replay.demo_events.push(crate::model::DemoEventIn {
            t: 1.0 / 30.0,
            frame_index: Some(1),
            victim_id: "p0".to_string(),
            attacker_id: None,
        });

        assert!(has_cause(
            &segment_replay(&replay),
            BoundaryCause::Demolition
        ));
    }

    #[test]
    fn respawn_teleport_is_hard_boundary() {
        let replay = series(vec![player(
            "p0",
            vec![[0.0, 0.0, 100.0], [600.1, 0.0, 100.0], [610.0, 0.0, 100.0]],
            vec![[0.0, 0.0, 0.0]; 3],
            vec![false; 3],
        )]);

        assert!(has_cause(&segment_replay(&replay), BoundaryCause::Respawn));
    }

    #[test]
    fn kickoff_marker_is_hard_boundary() {
        let mut replay = one_player_series();
        replay.kickoff_markers.push(crate::model::KickoffMarkerIn {
            t: 1.0 / 30.0,
            frame_index: Some(1),
            phase: "INITIAL".to_string(),
        });

        assert!(has_cause(
            &segment_replay(&replay),
            BoundaryCause::KickoffReset
        ));
    }

    #[test]
    fn liftoff_edge_splits_segments() {
        let replay = series(vec![player(
            "p0",
            vec![[0.0, 0.0, 17.0], [0.0, 0.0, 100.0], [0.0, 0.0, 110.0]],
            vec![[0.0, 0.0, 0.0]; 3],
            vec![true, false, false],
        )]);

        assert!(has_cause(&segment_replay(&replay), BoundaryCause::Liftoff));
    }

    #[test]
    fn landing_edge_splits_segments() {
        let replay = series(vec![player(
            "p0",
            vec![[0.0, 0.0, 100.0], [0.0, 0.0, 110.0], [0.0, 0.0, 17.0]],
            vec![[0.0, 0.0, 0.0]; 3],
            vec![false, false, true],
        )]);

        assert!(has_cause(&segment_replay(&replay), BoundaryCause::Landing));
    }

    #[test]
    fn surface_proximity_terminates_air_segments() {
        let replay = series(vec![player(
            "p0",
            vec![[0.0, 0.0, 100.0], [0.0, 0.0, 35.0], [0.0, 0.0, 100.0]],
            vec![[0.0, 0.0, 0.0]; 3],
            vec![false; 3],
        )]);

        assert!(has_cause(
            &segment_replay(&replay),
            BoundaryCause::SurfaceProximity
        ));
    }

    #[test]
    fn stream_edges_are_recorded_on_segments() {
        let replay = one_player_series();
        assert!(has_cause(
            &segment_replay(&replay),
            BoundaryCause::StreamEdge
        ));
    }

    #[test]
    fn coverage_counts_air_segments_duration_and_exclusions() {
        let mut replay = series(vec![player(
            "p0",
            vec![
                [0.0, 0.0, 17.0],
                [0.0, 0.0, 100.0],
                [0.0, 0.0, 110.0],
                [0.0, 0.0, 17.0],
                [0.0, 0.0, 17.0],
            ],
            vec![[0.0, 0.0, 0.0]; 5],
            vec![true, false, false, true, true],
        )]);
        replay.touch_events.push(crate::model::TouchEventIn {
            t: 1.0 / 30.0,
            frame_index: Some(2),
            player_id: "p0".to_string(),
            team: Some(0),
        });

        let output = segment_replay_with_confidences(&replay, 0.7, |_player_id, segment| {
            (segment.kind == SegmentKind::Air && segment.frame_span.0 == 1).then_some(0.8)
        });

        assert_eq!(output.coverage.air_segments, 1);
        assert_eq!(output.coverage.air_segments_confident, 1);
        assert_eq!(output.coverage.coverage, 1.0);
        assert_eq!(output.coverage.duration_weighted_coverage, 1.0);
        assert!(output
            .coverage
            .excluded_player_seconds_by_cause
            .iter()
            .any(|item| item.cause == BoundaryCause::BallTouch && item.player_seconds > 0.03));
    }

    #[test]
    fn retroactive_split_api_adds_car_contact_boundary() {
        let replay = one_player_series();
        let split = split_segment_at("p0", 1);
        let output = segment_replay_with_splits_and_confidences(
            &replay,
            &[split],
            0.7,
            |_player_id, _segment| None,
        );

        assert!(has_cause(&output, BoundaryCause::CarContactSuspected));
    }

    #[test]
    #[ignore = "requires scripts/export_series_json.py and RLINPUT_SERIES_JSON=/path/to/0925.json"]
    fn pinned_0925_segmentation_counts() {
        let path = std::env::var("RLINPUT_SERIES_JSON")
            .expect("set RLINPUT_SERIES_JSON to exported 0925 ReplaySeries JSON");
        let json = std::fs::read_to_string(path).expect("read exported ReplaySeries JSON");
        let replay: ReplaySeries = serde_json::from_str(&json).expect("parse ReplaySeries JSON");
        let output = segment_replay(&replay);

        let segment_count: usize = output
            .players
            .iter()
            .map(|player| player.segments.len())
            .sum();
        let boundary_counts: Vec<_> = output
            .boundary_counts_by_cause
            .iter()
            .map(|item| (item.cause.clone(), item.count))
            .collect();

        assert_eq!(segment_count, 858);
        assert_eq!(output.coverage.air_segments, 522);
        assert_eq!(
            boundary_counts,
            vec![
                (BoundaryCause::BallTouch, 161),
                (BoundaryCause::BallProximity, 142),
                (BoundaryCause::CarContactSuspected, 670),
                (BoundaryCause::Demolition, 481),
                (BoundaryCause::Respawn, 51),
                (BoundaryCause::KickoffReset, 28),
                (BoundaryCause::Liftoff, 299),
                (BoundaryCause::Landing, 298),
                (BoundaryCause::SurfaceProximity, 4074),
                (BoundaryCause::StreamEdge, 8),
            ]
        );
    }
}
