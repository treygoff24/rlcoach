//! Calibration oracle and V1 metric helpers.
//!
//! The oracle intentionally separates the solve input from scoring truth: the
//! solver receives only a [`BlindSolverInput`] whose replicated/component priors
//! have already been masked by [`WithheldChannels`]. Scoring code gets the
//! original [`ReplaySeries`] only after solving.

use std::collections::{BTreeMap, HashMap, HashSet};

use serde::{Deserialize, Serialize};

use crate::{
    lattice::LatticeInterval,
    model::{
        ComponentKind, EnginePreference, EstimatorConfig, KinematicFreshness, Mode, ReplaySeries,
        WithheldChannels,
    },
    segment::{segment_replay, Segment},
    solver::{default_estimator_config, masked_series_for_solving, solve_series},
    timeline::{InputSample, InputTimeline, SolveOutput, SolvedEventKind},
    tracker::reconstruct_seeded_edges,
};

const STRICT_BLIND: WithheldChannels = WithheldChannels::THROTTLE
    .union(WithheldChannels::STEER)
    .union(WithheldChannels::HANDBRAKE)
    .union(WithheldChannels::BOOST_ACTIVE)
    .union(WithheldChannels::BOOST_AMOUNT)
    .union(WithheldChannels::JUMP_EDGES)
    .union(WithheldChannels::COMPONENT_EVENTS);
const THROTTLE_DEADZONE_RAW: i16 = 13;
const STEER_TOLERANCE: f32 = 0.15;
const CONFIDENCE_BINS: usize = 10;

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct OracleReport {
    pub replay_count: usize,
    pub player_count: usize,
    pub flip_raw: F1Metric,
    pub flip_coalesced: F1Metric,
    pub flip_correct_interval_rate_raw: f32,
    pub flip_correct_interval_rate_coalesced: f32,
    pub blind: BlindChannelMetrics,
    pub amount_derived_boost_edges: F1Metric,
    pub coverage: CoverageMetric,
    pub calibration: Vec<ChannelCalibration>,
    pub per_replay: Vec<ReplayOracleReport>,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct ReplayOracleReport {
    pub replay: String,
    pub build_bucket: String,
    pub player_count: usize,
    pub flip_raw: F1Metric,
    pub flip_coalesced: F1Metric,
    pub blind: BlindChannelMetrics,
    pub amount_derived_boost_edges: F1Metric,
    pub coverage: CoverageMetric,
}

#[derive(Clone, Copy, Debug, Default, Serialize, Deserialize)]
pub struct F1Metric {
    pub truth: usize,
    pub predicted: usize,
    pub matched: usize,
    pub precision: f32,
    pub recall: f32,
    pub f1: f32,
}

#[derive(Clone, Copy, Debug, Default, Serialize, Deserialize)]
pub struct ShareMetric {
    pub numerator: usize,
    pub denominator: usize,
    pub share: f32,
}

#[derive(Clone, Debug, Default, Serialize, Deserialize)]
pub struct BlindChannelMetrics {
    pub boost_edge_f1: F1Metric,
    pub jump_edge_f1: F1Metric,
    pub throttle_sign: ShareMetric,
    pub steer_abs_error_le_0_15: ShareMetric,
    pub handbrake_f1: F1Metric,
}

#[derive(Clone, Copy, Debug, Default, Serialize, Deserialize)]
pub struct CoverageMetric {
    pub air_segments: u64,
    pub air_segments_confident: u64,
    pub coverage: f32,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct ChannelCalibration {
    pub channel: String,
    pub bins: Vec<CalibrationBin>,
}

#[derive(Clone, Copy, Debug, Default, Serialize, Deserialize)]
pub struct CalibrationBin {
    pub lower: f32,
    pub upper: f32,
    pub count: usize,
    pub predicted_confidence: f32,
    pub empirical_agreement: f32,
}

#[derive(Clone, Debug)]
pub struct BlindSolverInput {
    masked: ReplaySeries,
    config: EstimatorConfig,
}

impl BlindSolverInput {
    pub fn strict(series: &ReplaySeries) -> Self {
        let config = strict_blind_config();
        Self {
            masked: masked_series_for_solving(series, &config),
            config,
        }
    }

    pub fn solve(&self) -> SolveOutput {
        solve_series(&self.masked, &self.config)
    }

    pub fn masked_series(&self) -> &ReplaySeries {
        &self.masked
    }
}

pub fn strict_blind_config() -> EstimatorConfig {
    EstimatorConfig {
        mode: Mode::Unseeded,
        withhold: STRICT_BLIND,
        engine: EnginePreference::PortableOnly,
        ..default_estimator_config()
    }
}

pub fn run_oracle(named_series: &[(String, ReplaySeries)]) -> OracleReport {
    let mut acc = Accumulator::default();
    let mut per_replay = Vec::with_capacity(named_series.len());

    for (name, series) in named_series {
        let input = BlindSolverInput::strict(series);
        let output = input.solve();
        let replay = score_replay(name, series, &output, &mut acc.calibration);
        acc.add_replay(&replay);
        per_replay.push(replay);
    }

    OracleReport {
        replay_count: named_series.len(),
        player_count: acc.player_count,
        flip_raw: acc.flip_raw.finish(),
        flip_coalesced: acc.flip_coalesced.finish(),
        flip_correct_interval_rate_raw: acc.flip_raw.correct_interval_rate(),
        flip_correct_interval_rate_coalesced: acc.flip_coalesced.correct_interval_rate(),
        blind: acc.blind.finish(),
        amount_derived_boost_edges: acc.amount_derived_boost_edges.finish(),
        coverage: acc.coverage.finish(),
        calibration: acc.calibration.finish(),
        per_replay,
    }
}

pub fn score_replay(
    name: &str,
    series: &ReplaySeries,
    output: &SolveOutput,
    calibration: &mut CalibrationAcc,
) -> ReplayOracleReport {
    let raw_truth = flip_truth_raw(series);
    let coalesced_truth = coalesced_flip_truth(series, output);
    let flip_pred = solved_flip_intervals(output);
    let jump_truth = component_truth(series, &[ComponentKind::Jump]);
    let jump_pred = solved_jump_intervals(output);
    let boost_truth = replicated_bool_edges(series, |player| &player.replicated.boost_active_raw);
    let boost_pred = solved_bool_edges(output, |sample| sample.boost.value);
    let handbrake_truth = replicated_bool_edges(series, |player| &player.replicated.handbrake);
    let handbrake_pred = solved_bool_edges(output, |sample| sample.handbrake.value);
    let amount_edges = amount_derived_boost_edges(series);

    let blind = BlindChannelMetrics {
        boost_edge_f1: f1_with_tolerance(&boost_truth, &boost_pred, 1),
        jump_edge_f1: f1_with_tolerance(&jump_truth, &jump_pred, 1),
        throttle_sign: throttle_sign(series, output, calibration),
        steer_abs_error_le_0_15: steer_accuracy(series, output, calibration),
        handbrake_f1: f1_with_tolerance(&handbrake_truth, &handbrake_pred, 1),
    };
    add_bool_calibration(series, output, calibration, "boost_active", |sample| {
        sample.boost.value
    });
    add_bool_calibration(series, output, calibration, "handbrake", |sample| {
        sample.handbrake.value
    });

    ReplayOracleReport {
        replay: name.to_string(),
        build_bucket: series.build_bucket.clone(),
        player_count: series.players.len(),
        flip_raw: f1_with_tolerance(&raw_truth, &flip_pred, 0),
        flip_coalesced: f1_with_tolerance(&coalesced_truth, &flip_pred, 0),
        blind,
        amount_derived_boost_edges: f1_with_tolerance(&boost_truth, &amount_edges, 1),
        coverage: coverage_from_output(output),
    }
}

#[derive(Default)]
struct Accumulator {
    player_count: usize,
    flip_raw: CountF1,
    flip_coalesced: CountF1,
    blind: BlindAcc,
    amount_derived_boost_edges: CountF1,
    coverage: CoverageAcc,
    calibration: CalibrationAcc,
}

impl Accumulator {
    fn add_replay(&mut self, replay: &ReplayOracleReport) {
        self.player_count += replay.player_count;
        self.flip_raw.add(replay.flip_raw);
        self.flip_coalesced.add(replay.flip_coalesced);
        self.blind.add(&replay.blind);
        self.amount_derived_boost_edges
            .add(replay.amount_derived_boost_edges);
        self.coverage.add(replay.coverage);
    }
}

#[derive(Clone, Copy, Debug, Default)]
struct CountF1 {
    truth: usize,
    predicted: usize,
    matched: usize,
}

impl CountF1 {
    fn add(&mut self, metric: F1Metric) {
        self.truth += metric.truth;
        self.predicted += metric.predicted;
        self.matched += metric.matched;
    }

    fn finish(self) -> F1Metric {
        metric(self.truth, self.predicted, self.matched)
    }

    fn correct_interval_rate(self) -> f32 {
        share(self.matched, self.truth)
    }
}

#[derive(Default)]
struct BlindAcc {
    boost_edge_f1: CountF1,
    jump_edge_f1: CountF1,
    throttle_sign: ShareAcc,
    steer: ShareAcc,
    handbrake_f1: CountF1,
}

impl BlindAcc {
    fn add(&mut self, metric: &BlindChannelMetrics) {
        self.boost_edge_f1.add(metric.boost_edge_f1);
        self.jump_edge_f1.add(metric.jump_edge_f1);
        self.throttle_sign.add(metric.throttle_sign);
        self.steer.add(metric.steer_abs_error_le_0_15);
        self.handbrake_f1.add(metric.handbrake_f1);
    }

    fn finish(self) -> BlindChannelMetrics {
        BlindChannelMetrics {
            boost_edge_f1: self.boost_edge_f1.finish(),
            jump_edge_f1: self.jump_edge_f1.finish(),
            throttle_sign: self.throttle_sign.finish(),
            steer_abs_error_le_0_15: self.steer.finish(),
            handbrake_f1: self.handbrake_f1.finish(),
        }
    }
}

#[derive(Clone, Copy, Debug, Default)]
struct ShareAcc {
    numerator: usize,
    denominator: usize,
}

impl ShareAcc {
    fn add(&mut self, metric: ShareMetric) {
        self.numerator += metric.numerator;
        self.denominator += metric.denominator;
    }

    fn finish(self) -> ShareMetric {
        ShareMetric {
            numerator: self.numerator,
            denominator: self.denominator,
            share: share(self.numerator, self.denominator),
        }
    }
}

#[derive(Default)]
struct CoverageAcc {
    air_segments: u64,
    air_segments_confident: u64,
}

impl CoverageAcc {
    fn add(&mut self, metric: CoverageMetric) {
        self.air_segments += metric.air_segments;
        self.air_segments_confident += metric.air_segments_confident;
    }

    fn finish(self) -> CoverageMetric {
        CoverageMetric {
            air_segments: self.air_segments,
            air_segments_confident: self.air_segments_confident,
            coverage: if self.air_segments == 0 {
                0.0
            } else {
                self.air_segments_confident as f32 / self.air_segments as f32
            },
        }
    }
}

#[derive(Default)]
pub struct CalibrationAcc {
    channels: BTreeMap<String, [BinAcc; CONFIDENCE_BINS]>,
}

impl CalibrationAcc {
    fn add(&mut self, channel: &str, confidence: f32, correct: bool) {
        let idx = ((confidence.clamp(0.0, 0.999_999) * CONFIDENCE_BINS as f32) as usize)
            .min(CONFIDENCE_BINS - 1);
        self.channels.entry(channel.to_string()).or_default()[idx].add(confidence, correct);
    }

    fn finish(self) -> Vec<ChannelCalibration> {
        self.channels
            .into_iter()
            .map(|(channel, bins)| ChannelCalibration {
                channel,
                bins: bins
                    .into_iter()
                    .enumerate()
                    .map(|(idx, bin)| bin.finish(idx))
                    .collect(),
            })
            .collect()
    }
}

#[derive(Clone, Copy, Debug, Default)]
struct BinAcc {
    count: usize,
    confidence_sum: f32,
    hits: usize,
}

impl BinAcc {
    fn add(&mut self, confidence: f32, correct: bool) {
        self.count += 1;
        self.confidence_sum += confidence;
        self.hits += usize::from(correct);
    }

    fn finish(self, idx: usize) -> CalibrationBin {
        CalibrationBin {
            lower: idx as f32 / CONFIDENCE_BINS as f32,
            upper: (idx + 1) as f32 / CONFIDENCE_BINS as f32,
            count: self.count,
            predicted_confidence: if self.count == 0 {
                0.0
            } else {
                self.confidence_sum / self.count as f32
            },
            empirical_agreement: share(self.hits, self.count),
        }
    }
}

fn flip_truth_raw(series: &ReplaySeries) -> HashSet<(String, u32)> {
    component_truth(
        series,
        &[ComponentKind::DodgeTorque, ComponentKind::DoubleJumpImpulse],
    )
}

fn component_truth(series: &ReplaySeries, kinds: &[ComponentKind]) -> HashSet<(String, u32)> {
    let mut out = HashSet::new();
    for player in &series.players {
        for edge in reconstruct_seeded_edges(&player.component) {
            if kinds.contains(&edge.component) {
                out.insert((player.player_id.clone(), edge.frame_index));
            }
        }
    }
    out
}

fn solved_flip_intervals(output: &SolveOutput) -> HashSet<(String, u32)> {
    solved_events(output, |kind| {
        matches!(
            kind,
            SolvedEventKind::Dodge { .. } | SolvedEventKind::DoubleJump | SolvedEventKind::Stall
        )
    })
}

fn solved_jump_intervals(output: &SolveOutput) -> HashSet<(String, u32)> {
    solved_events(output, |kind| {
        matches!(
            kind,
            SolvedEventKind::JumpPress | SolvedEventKind::JumpRelease
        )
    })
}

fn solved_events(
    output: &SolveOutput,
    predicate: impl Fn(&SolvedEventKind) -> bool,
) -> HashSet<(String, u32)> {
    let mut out = HashSet::new();
    for timeline in &output.timelines {
        for event in &timeline.events {
            if predicate(&event.kind) {
                out.insert((timeline.player_id.clone(), event.frame_index));
            }
        }
    }
    out
}

fn coalesced_flip_truth(series: &ReplaySeries, output: &SolveOutput) -> HashSet<(String, u32)> {
    let raw = flip_truth_raw(series);
    let mut out = HashSet::new();
    let by_player: HashMap<_, _> = output
        .timelines
        .iter()
        .map(|timeline| (timeline.player_id.as_str(), timeline))
        .collect();

    for player in &series.players {
        let Some(timeline) = by_player.get(player.player_id.as_str()) else {
            continue;
        };
        let mut prev = 0;
        for sample in &timeline.samples {
            if raw.iter().any(|(player_id, frame)| {
                player_id == &player.player_id && *frame > prev && *frame <= sample.frame_index
            }) {
                out.insert((player.player_id.clone(), sample.frame_index));
            }
            prev = sample.frame_index;
        }
    }
    out
}

fn replicated_bool_edges(
    series: &ReplaySeries,
    field: impl Fn(&crate::model::PlayerSeries) -> &[bool],
) -> HashSet<(String, u32)> {
    let mut out = HashSet::new();
    for player in &series.players {
        let values = field(player);
        for idx in 1..values.len() {
            if values[idx] != values[idx - 1] {
                out.insert((player.player_id.clone(), idx as u32));
            }
        }
    }
    out
}

fn solved_bool_edges(
    output: &SolveOutput,
    value: impl Fn(&InputSample) -> bool,
) -> HashSet<(String, u32)> {
    let mut out = HashSet::new();
    for timeline in &output.timelines {
        let mut prev = None;
        for sample in &timeline.samples {
            let current = value(sample);
            if prev.is_some_and(|prev| prev != current) {
                out.insert((timeline.player_id.clone(), sample.frame_index));
            }
            prev = Some(current);
        }
    }
    out
}

fn amount_derived_boost_edges(series: &ReplaySeries) -> HashSet<(String, u32)> {
    let mut out = HashSet::new();
    for player in &series.players {
        let raw = &player.replicated.boost_amount_raw;
        let mut prev_active = false;
        for idx in 1..raw.len() {
            let active = raw[idx] < raw[idx - 1];
            if active != prev_active {
                out.insert((player.player_id.clone(), idx as u32));
            }
            prev_active = active;
        }
    }
    out
}

fn throttle_sign(
    series: &ReplaySeries,
    output: &SolveOutput,
    calibration: &mut CalibrationAcc,
) -> ShareMetric {
    let mut acc = ShareAcc::default();
    for (player, timeline) in joined_players(series, output) {
        for sample in &timeline.samples {
            let idx = sample_start_frame(series, sample).unwrap_or(sample.frame_index) as usize;
            let Some(raw) = player.replicated.throttle_raw.get(idx).copied() else {
                continue;
            };
            let centered = i16::from(raw) - 128;
            if centered.abs() <= THROTTLE_DEADZONE_RAW {
                continue;
            }
            let correct = centered.signum() == signum_f32(sample.throttle.value);
            acc.numerator += usize::from(correct);
            acc.denominator += 1;
            calibration.add("throttle_sign", sample.throttle.confidence, correct);
        }
    }
    acc.finish()
}

fn steer_accuracy(
    series: &ReplaySeries,
    output: &SolveOutput,
    calibration: &mut CalibrationAcc,
) -> ShareMetric {
    let mut acc = ShareAcc::default();
    for (player, timeline) in joined_players(series, output) {
        for sample in &timeline.samples {
            let idx = sample_start_frame(series, sample).unwrap_or(sample.frame_index) as usize;
            let Some(raw) = player.replicated.steer_raw.get(idx).copied() else {
                continue;
            };
            let truth = raw_axis(raw);
            let correct = (sample.steer.value - truth).abs() <= STEER_TOLERANCE;
            acc.numerator += usize::from(correct);
            acc.denominator += 1;
            calibration.add("steer_abs_error_le_0_15", sample.steer.confidence, correct);
        }
    }
    acc.finish()
}

fn add_bool_calibration(
    series: &ReplaySeries,
    output: &SolveOutput,
    calibration: &mut CalibrationAcc,
    channel: &str,
    predicted: impl Fn(&InputSample) -> bool,
) {
    for (player, timeline) in joined_players(series, output) {
        for sample in &timeline.samples {
            let idx = sample_start_frame(series, sample).unwrap_or(sample.frame_index) as usize;
            let truth = match channel {
                "boost_active" => player.replicated.boost_active_raw.get(idx).copied(),
                "handbrake" => player.replicated.handbrake.get(idx).copied(),
                _ => None,
            };
            if let Some(truth) = truth {
                let confidence = match channel {
                    "boost_active" => sample.boost.confidence,
                    "handbrake" => sample.handbrake.confidence,
                    _ => 0.0,
                };
                calibration.add(channel, confidence, predicted(sample) == truth);
            }
        }
    }
}

fn joined_players<'a>(
    series: &'a ReplaySeries,
    output: &'a SolveOutput,
) -> Vec<(&'a crate::model::PlayerSeries, &'a InputTimeline)> {
    let timelines: HashMap<_, _> = output
        .timelines
        .iter()
        .map(|timeline| (timeline.player_id.as_str(), timeline))
        .collect();
    series
        .players
        .iter()
        .filter_map(|player| {
            timelines
                .get(player.player_id.as_str())
                .map(|timeline| (player, *timeline))
        })
        .collect()
}

fn sample_start_frame(series: &ReplaySeries, sample: &InputSample) -> Option<u32> {
    let times = frame_times(series);
    times
        .iter()
        .enumerate()
        .take(sample.frame_index as usize + 1)
        .min_by(|(_, a), (_, b)| {
            (*a - sample.time_range.0)
                .abs()
                .total_cmp(&(*b - sample.time_range.0).abs())
        })
        .map(|(idx, _)| idx as u32)
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

fn delta_for(series: &ReplaySeries, frame: usize) -> f32 {
    series
        .deltas
        .get(frame)
        .copied()
        .or_else(|| {
            frame
                .checked_sub(1)
                .and_then(|idx| series.deltas.get(idx).copied())
        })
        .unwrap_or(0.0)
}

fn f1_with_tolerance(
    truth: &HashSet<(String, u32)>,
    predicted: &HashSet<(String, u32)>,
    tolerance: i32,
) -> F1Metric {
    let mut matched_truth = HashSet::new();
    let mut predictions: Vec<_> = predicted.iter().collect();
    predictions.sort();
    for (player_id, pred_frame) in predictions {
        if let Some(candidate) = truth
            .iter()
            .filter(|(truth_player, truth_frame)| {
                truth_player == player_id
                    && !matched_truth.contains(&(truth_player.clone(), *truth_frame))
                    && (*truth_frame as i32 - *pred_frame as i32).abs() <= tolerance
            })
            .min_by_key(|(_, truth_frame)| (*truth_frame as i32 - *pred_frame as i32).abs())
        {
            matched_truth.insert((candidate.0.clone(), candidate.1));
        }
    }
    metric(truth.len(), predicted.len(), matched_truth.len())
}

fn metric(truth: usize, predicted: usize, matched: usize) -> F1Metric {
    let precision = share(matched, predicted);
    let recall = share(matched, truth);
    F1Metric {
        truth,
        predicted,
        matched,
        precision,
        recall,
        f1: if precision + recall == 0.0 {
            0.0
        } else {
            2.0 * precision * recall / (precision + recall)
        },
    }
}

fn coverage_from_output(output: &SolveOutput) -> CoverageMetric {
    CoverageMetric {
        air_segments: output.coverage.air_segments,
        air_segments_confident: output.coverage.air_segments_confident,
        coverage: output.coverage.coverage,
    }
}

fn fresh_scoring_intervals(
    segment: &Segment,
    freshness: &KinematicFreshness,
) -> Vec<(u32, LatticeInterval)> {
    let mut out = Vec::new();
    let mut anchor_frame = segment.frame_span.0.saturating_sub(1);
    let mut anchor_tick = 0;
    let mut anchor_time = 0.0;
    let mut flags = crate::timeline::AmbiguityFlags::empty();

    for interval in &segment.lattice.intervals {
        flags |= interval.flags;
        if !freshness.is_fresh(interval.frame_index) {
            continue;
        }
        if interval.frame_index != anchor_frame {
            out.push((
                anchor_frame,
                LatticeInterval {
                    frame_index: interval.frame_index,
                    tick_range: (anchor_tick, interval.tick_range.1),
                    time_range: (anchor_time, interval.time_range.1),
                    flags,
                },
            ));
        }
        anchor_frame = interval.frame_index;
        anchor_tick = interval.tick_range.1;
        anchor_time = interval.time_range.1;
        flags = crate::timeline::AmbiguityFlags::empty();
    }
    out
}

#[allow(dead_code)]
fn coalesced_flip_truth_from_segments(series: &ReplaySeries) -> HashSet<(String, u32)> {
    let segmentation = segment_replay(series);
    let raw = flip_truth_raw(series);
    let mut out = HashSet::new();
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
            for (start_frame, interval) in fresh_scoring_intervals(segment, &freshness) {
                if raw.iter().any(|(player_id, frame)| {
                    player_id == &player.player_id
                        && *frame > start_frame
                        && *frame <= interval.frame_index
                }) {
                    out.insert((player.player_id.clone(), interval.frame_index));
                }
            }
        }
    }
    out
}

fn raw_axis(raw: u8) -> f32 {
    (f32::from(raw) - 128.0) / 127.0
}

fn signum_f32(value: f32) -> i16 {
    if value > 0.0 {
        1
    } else if value < 0.0 {
        -1
    } else {
        0
    }
}

fn share(num: usize, den: usize) -> f32 {
    if den == 0 {
        0.0
    } else {
        num as f32 / den as f32
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::model::{BallSeries, ComponentStream, Kinematics, PlayerSeries, ReplicatedChannels};

    #[test]
    fn withheld_channel_is_never_read_during_solve() {
        let series = poison_replicated_series();
        let input = BlindSolverInput::strict(&series);
        let masked = input.masked_series();
        let player = &masked.players[0];

        assert_eq!(player.replicated.throttle_raw, vec![128; 3]);
        assert_eq!(player.replicated.steer_raw, vec![128; 3]);
        assert_eq!(player.replicated.handbrake, vec![false; 3]);
        assert_eq!(player.replicated.boost_active_raw, vec![false; 3]);
        assert_eq!(player.replicated.boost_amount_raw, vec![0; 3]);
        assert!(player.component.events.is_empty());
        assert!(player.component.jump_raw.iter().all(|value| *value == 0));

        let output = input.solve();
        assert!(output.timelines[0]
            .samples
            .iter()
            .all(
                |sample| sample.throttle.source != crate::timeline::Source::Replicated
                    && sample.steer.source != crate::timeline::Source::Replicated
                    && sample.boost.source != crate::timeline::Source::Replicated
                    && sample.handbrake.source != crate::timeline::Source::Replicated
            ));
    }

    #[test]
    fn f1_matching_is_greedy_and_one_to_one() {
        let truth = HashSet::from([("p0".to_string(), 10), ("p0".to_string(), 11)]);
        let predicted = HashSet::from([("p0".to_string(), 10), ("p0".to_string(), 10)]);
        let metric = f1_with_tolerance(&truth, &predicted, 0);
        assert_eq!(metric.matched, 1);
        assert_eq!(metric.truth, 2);
    }

    #[test]
    #[ignore = "set RLINPUT_DEV_SERIES_DIR to exported dev-set ReplaySeries JSON directory"]
    fn exported_dev_set_oracle_report() {
        let dir = std::env::var("RLINPUT_DEV_SERIES_DIR")
            .expect("RLINPUT_DEV_SERIES_DIR should point to exported ReplaySeries JSONs");
        let mut named = Vec::new();
        for entry in std::fs::read_dir(dir).expect("dev series dir should read") {
            let path = entry.expect("entry should read").path();
            if path.extension().and_then(|ext| ext.to_str()) != Some("json") {
                continue;
            }
            let file = std::fs::File::open(&path).expect("series json should open");
            let series: ReplaySeries = serde_json::from_reader(file).expect("series should parse");
            named.push((
                path.file_stem()
                    .and_then(|name| name.to_str())
                    .unwrap_or("unknown")
                    .to_string(),
                series,
            ));
        }
        named.sort_by(|a, b| a.0.cmp(&b.0));
        let report = run_oracle(&named);
        println!(
            "{}",
            serde_json::to_string_pretty(&report).expect("report should serialize")
        );
        assert_eq!(report.replay_count, 10);
    }

    fn poison_replicated_series() -> ReplaySeries {
        ReplaySeries {
            tick_rate: 120.0,
            build_bucket: "test".to_string(),
            players: vec![PlayerSeries {
                player_id: "p0".to_string(),
                frames: Kinematics {
                    pos: vec![[0.0, 0.0, 500.0], [1.0, 0.0, 499.0], [2.0, 0.0, 497.0]],
                    vel: vec![[0.0, 0.0, 0.0], [30.0, 0.0, -20.0], [30.0, 0.0, -40.0]],
                    quat_xyzw: vec![[0.0, 0.0, 0.0, 1.0]; 3],
                    ang_vel: vec![[0.0; 3]; 3],
                    on_ground: vec![false; 3],
                    sleeping: vec![false; 3],
                    demolished: vec![false; 3],
                },
                replicated: ReplicatedChannels {
                    throttle_raw: vec![255, 0, 255],
                    steer_raw: vec![0, 255, 0],
                    handbrake: vec![true; 3],
                    boost_amount_raw: vec![255, 200, 128],
                    boost_active_raw: vec![true; 3],
                },
                component: ComponentStream {
                    jump_raw: vec![9, 10, 11],
                    dodge_raw: vec![1, 2, 3],
                    double_jump_raw: vec![7, 8, 9],
                    boost_raw: vec![5, 6, 7],
                    events: vec![crate::model::ComponentEventIn {
                        t: 1.0 / 30.0,
                        frame_index: 1,
                        component: ComponentKind::DodgeTorque,
                        vector: Some([0.0, 2.24, 0.0]),
                        raw_value: Some(2),
                    }],
                },
            }],
            ball: BallSeries {
                pos: vec![[10_000.0, 10_000.0, 93.0]; 3],
                vel: vec![[0.0; 3]; 3],
            },
            deltas: vec![0.0, 1.0 / 30.0, 1.0 / 30.0],
            demo_events: Vec::new(),
            touch_events: Vec::new(),
            kickoff_markers: Vec::new(),
        }
    }
}
