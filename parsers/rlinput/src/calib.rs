//! Calibration oracle and V1 metric helpers.
//!
//! The oracle intentionally separates the solve input from scoring truth: the
//! solver receives only a [`BlindSolverInput`] whose replicated/component priors
//! have already been masked by [`WithheldChannels`]. Scoring code gets the
//! original [`ReplaySeries`] only after solving.

use std::collections::{BTreeMap, HashMap, HashSet};

use serde::{Deserialize, Serialize};

use crate::{
    component_truth::{component_edges, TruthFilter},
    lattice::LatticeInterval,
    model::{
        ComponentKind, EnginePreference, EstimatorConfig, KinematicFreshness, Mode, ReplaySeries,
        WithheldChannels,
    },
    segment::{segment_replay, Segment},
    solver::{default_estimator_config, masked_series_for_solving, solve_series},
    timeline::{InputSample, InputTimeline, SolveOutput, SolvedEventKind},
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
    pub flip_raw_unfiltered: F1Metric,
    pub flip_raw_pm1_interval: F1Metric,
    pub phantom_flip_raw: usize,
    pub flip_coalesced: F1Metric,
    pub flip_coalesced_unfiltered: F1Metric,
    pub flip_coalesced_pm1_interval: F1Metric,
    pub phantom_flip_coalesced: usize,
    pub flip_correct_interval_rate_raw: f32,
    pub flip_correct_interval_rate_raw_unfiltered: f32,
    pub flip_correct_interval_rate_coalesced: f32,
    pub flip_correct_interval_rate_coalesced_unfiltered: f32,
    pub blind: BlindChannelMetrics,
    pub powerslide_steer_split: PowerslideSteerSplit,
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
    pub flip_raw_unfiltered: F1Metric,
    pub flip_raw_pm1_interval: F1Metric,
    pub phantom_flip_raw: usize,
    pub flip_coalesced: F1Metric,
    pub flip_coalesced_unfiltered: F1Metric,
    pub flip_coalesced_pm1_interval: F1Metric,
    pub phantom_flip_coalesced: usize,
    pub blind: BlindChannelMetrics,
    pub powerslide_steer_split: PowerslideSteerSplit,
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

#[derive(Clone, Debug, Default, Serialize, Deserialize)]
pub struct PowerslideSteerSplit {
    pub powerslide: ShareMetric,
    pub non_powerslide: ShareMetric,
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
        flip_raw_unfiltered: acc.flip_raw_unfiltered.finish(),
        flip_raw_pm1_interval: acc.flip_raw_pm1_interval.finish(),
        phantom_flip_raw: acc.phantom_flip_raw,
        flip_coalesced: acc.flip_coalesced.finish(),
        flip_coalesced_unfiltered: acc.flip_coalesced_unfiltered.finish(),
        flip_coalesced_pm1_interval: acc.flip_coalesced_pm1_interval.finish(),
        phantom_flip_coalesced: acc.phantom_flip_coalesced,
        flip_correct_interval_rate_raw: acc.flip_raw.correct_interval_rate(),
        flip_correct_interval_rate_raw_unfiltered: acc.flip_raw_unfiltered.correct_interval_rate(),
        flip_correct_interval_rate_coalesced: acc.flip_coalesced.correct_interval_rate(),
        flip_correct_interval_rate_coalesced_unfiltered: acc
            .flip_coalesced_unfiltered
            .correct_interval_rate(),
        blind: acc.blind.finish(),
        powerslide_steer_split: acc.powerslide_steer_split.finish(),
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
    let raw_truth_unfiltered = flip_truth_raw_with_filter(series, TruthFilter::Unfiltered);
    let coalesced_truth = coalesced_flip_truth(series, output);
    let coalesced_truth_unfiltered =
        coalesced_flip_truth_with_filter(series, output, TruthFilter::Unfiltered);
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
        flip_raw_unfiltered: f1_with_tolerance(&raw_truth_unfiltered, &flip_pred, 0),
        flip_raw_pm1_interval: f1_with_tolerance(&raw_truth, &flip_pred, 1),
        phantom_flip_raw: raw_truth_unfiltered.len().saturating_sub(raw_truth.len()),
        flip_coalesced: f1_with_tolerance(&coalesced_truth, &flip_pred, 0),
        flip_coalesced_unfiltered: f1_with_tolerance(&coalesced_truth_unfiltered, &flip_pred, 0),
        flip_coalesced_pm1_interval: f1_with_tolerance(&coalesced_truth, &flip_pred, 1),
        phantom_flip_coalesced: coalesced_truth_unfiltered
            .len()
            .saturating_sub(coalesced_truth.len()),
        blind,
        powerslide_steer_split: powerslide_steer_split(series, output),
        amount_derived_boost_edges: f1_with_tolerance(&boost_truth, &amount_edges, 1),
        coverage: coverage_from_output(output),
    }
}

#[derive(Default)]
struct Accumulator {
    player_count: usize,
    flip_raw: CountF1,
    flip_raw_unfiltered: CountF1,
    flip_raw_pm1_interval: CountF1,
    phantom_flip_raw: usize,
    flip_coalesced: CountF1,
    flip_coalesced_unfiltered: CountF1,
    flip_coalesced_pm1_interval: CountF1,
    phantom_flip_coalesced: usize,
    blind: BlindAcc,
    powerslide_steer_split: PowerslideSteerAcc,
    amount_derived_boost_edges: CountF1,
    coverage: CoverageAcc,
    calibration: CalibrationAcc,
}

impl Accumulator {
    fn add_replay(&mut self, replay: &ReplayOracleReport) {
        self.player_count += replay.player_count;
        self.flip_raw.add(replay.flip_raw);
        self.flip_raw_unfiltered.add(replay.flip_raw_unfiltered);
        self.flip_raw_pm1_interval.add(replay.flip_raw_pm1_interval);
        self.phantom_flip_raw += replay.phantom_flip_raw;
        self.flip_coalesced.add(replay.flip_coalesced);
        self.flip_coalesced_unfiltered
            .add(replay.flip_coalesced_unfiltered);
        self.flip_coalesced_pm1_interval
            .add(replay.flip_coalesced_pm1_interval);
        self.phantom_flip_coalesced += replay.phantom_flip_coalesced;
        self.blind.add(&replay.blind);
        self.powerslide_steer_split
            .add(&replay.powerslide_steer_split);
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

#[derive(Default)]
struct PowerslideSteerAcc {
    powerslide: ShareAcc,
    non_powerslide: ShareAcc,
}

impl PowerslideSteerAcc {
    fn add(&mut self, metric: &PowerslideSteerSplit) {
        self.powerslide.add(metric.powerslide);
        self.non_powerslide.add(metric.non_powerslide);
    }

    fn finish(self) -> PowerslideSteerSplit {
        PowerslideSteerSplit {
            powerslide: self.powerslide.finish(),
            non_powerslide: self.non_powerslide.finish(),
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
    flip_truth_raw_with_filter(series, TruthFilter::Unfiltered)
}

fn flip_truth_raw_with_filter(
    series: &ReplaySeries,
    filter: TruthFilter,
) -> HashSet<(String, u32)> {
    component_truth_with_filter(
        series,
        &[ComponentKind::DodgeTorque, ComponentKind::DoubleJumpImpulse],
        filter,
    )
}

fn component_truth(series: &ReplaySeries, kinds: &[ComponentKind]) -> HashSet<(String, u32)> {
    component_truth_with_filter(series, kinds, TruthFilter::Unfiltered)
}

fn component_truth_with_filter(
    series: &ReplaySeries,
    kinds: &[ComponentKind],
    filter: TruthFilter,
) -> HashSet<(String, u32)> {
    let mut out = HashSet::new();
    for player in &series.players {
        for edge in component_edges(&player.component, filter) {
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
    coalesced_flip_truth_with_filter(series, output, TruthFilter::Unfiltered)
}

fn coalesced_flip_truth_with_filter(
    series: &ReplaySeries,
    output: &SolveOutput,
    filter: TruthFilter,
) -> HashSet<(String, u32)> {
    let raw = flip_truth_raw_with_filter(series, filter);
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
            if !player.frames.on_ground.get(idx).copied().unwrap_or(false) {
                continue;
            }
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

fn powerslide_steer_split(series: &ReplaySeries, output: &SolveOutput) -> PowerslideSteerSplit {
    let mut powerslide = ShareAcc::default();
    let mut non_powerslide = ShareAcc::default();
    for (player, timeline) in joined_players(series, output) {
        for sample in &timeline.samples {
            let idx = sample_start_frame(series, sample).unwrap_or(sample.frame_index) as usize;
            let Some(raw) = player.replicated.steer_raw.get(idx).copied() else {
                continue;
            };
            let correct = (sample.steer.value - raw_axis(raw)).abs() <= STEER_TOLERANCE;
            let acc = if player
                .replicated
                .handbrake
                .get(idx)
                .copied()
                .unwrap_or(false)
            {
                &mut powerslide
            } else {
                &mut non_powerslide
            };
            acc.numerator += usize::from(correct);
            acc.denominator += 1;
        }
    }
    PowerslideSteerSplit {
        powerslide: powerslide.finish(),
        non_powerslide: non_powerslide.finish(),
    }
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

    #[cfg(feature = "sim")]
    const SEEDED_251202_DEV_REPLAYS: [&str; 4] = [
        "3D6CDD7F418048C2AA2A11ACC588094D",
        "769971A8447DB11ABD813990572B53B1",
        "7A51ECF34B1E94EFE3B049B1DC0A8F7E",
        "F5BB1FF44EB9B29EE9EF9C9ACA51BA7C",
    ];

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
        let named = load_exported_series(&dir);
        let report = run_oracle(&named);
        println!(
            "{}",
            serde_json::to_string_pretty(&report).expect("report should serialize")
        );
        assert_eq!(report.replay_count, 10);
    }

    #[test]
    #[ignore = "set RLINPUT_DEV_SERIES_DIR to exported dev-set ReplaySeries JSON directory"]
    fn exported_dev_set_confidence_informativeness_report() {
        let dir = std::env::var("RLINPUT_DEV_SERIES_DIR")
            .expect("RLINPUT_DEV_SERIES_DIR should point to exported ReplaySeries JSONs");
        let named = load_exported_series(&dir);
        let mut samples = InformativenessSamples::default();
        for (name, series) in &named {
            let input = BlindSolverInput::strict(series);
            let output = input.solve();
            samples.add_replay(series, &output);
            println!(
                "confidence_informativeness_replay,replay={},air_segments={}",
                name, output.coverage.air_segments
            );
        }
        assert_eq!(named.len(), 10);
        samples.print();
    }

    #[cfg(feature = "sim")]
    #[test]
    #[ignore = "set RLINPUT_DEV_SERIES_DIR to exported dev-set ReplaySeries JSON directory"]
    fn criterion3_channel_probe_report() {
        let dir = std::env::var("RLINPUT_DEV_SERIES_DIR")
            .expect("RLINPUT_DEV_SERIES_DIR should point to exported ReplaySeries JSONs");
        let mut named: Vec<_> = load_exported_series(&dir)
            .into_iter()
            .filter(|(name, _)| SEEDED_251202_DEV_REPLAYS.contains(&name.as_str()))
            .collect();
        named.sort_by(|a, b| a.0.cmp(&b.0));
        assert_eq!(named.len(), SEEDED_251202_DEV_REPLAYS.len());

        println!("criterion3_probe_scope,replays={}", named.len());
        for (name, series) in named {
            let input = BlindSolverInput::strict(&series);
            println!(
                "criterion3_ruler_audit,replay={},mask_ok={},key_space=sample_start_raw_frame,boost_truth=raw_replicated_edges,boost_pred=sample_end_edges,strict_blind=true",
                name,
                strict_mask_ok(input.masked_series())
            );
            let output = input.solve();
            print_continuous_channel_probe(&name, &series, &output);
            print_boost_probe(&name, &series, &output);
        }
    }

    #[cfg(feature = "sim")]
    #[test]
    #[ignore = "set RLINPUT_GATE_MANIFEST to assets/s1_holdout_set.json or assets/s1_dev_set.json"]
    fn gate_evaluation_report() {
        let started = std::time::Instant::now();
        let manifest = gate_manifest_path();
        let repo = repo_root();
        let label =
            std::env::var("RLINPUT_GATE_LABEL").unwrap_or_else(|_| infer_gate_label(&manifest));
        let series_dir = gate_series_dir(&label);
        std::fs::create_dir_all(&series_dir).expect("gate series dir should be creatable");

        let entries = gate_manifest_entries(&manifest);
        assert!(
            !entries.is_empty(),
            "gate manifest should contain holdout or dev entries: {}",
            manifest.display()
        );

        let mut named = Vec::new();
        let mut failures = Vec::new();
        for entry in &entries {
            match export_and_load_gate_series(&repo, entry, &series_dir) {
                Ok(series) => named.push((gate_replay_name(entry), series)),
                Err(reason) => failures.push(serde_json::json!({
                    "replay": entry,
                    "reason": reason,
                })),
            }
        }
        assert!(
            !named.is_empty(),
            "all gate replay exports failed for {}",
            manifest.display()
        );

        let oracle = run_oracle(&named);
        let resim = run_gate_resim(&repo, &manifest, &series_dir);
        let report = gate_report_json(
            &label,
            &manifest,
            entries.len(),
            &failures,
            &oracle,
            resim,
            started.elapsed(),
        );
        println!(
            "{}",
            serde_json::to_string_pretty(&report).expect("gate report should serialize")
        );
    }

    fn load_exported_series(dir: &str) -> Vec<(String, ReplaySeries)> {
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
        named
    }

    #[derive(Default)]
    struct InformativenessSamples {
        by_family: BTreeMap<&'static str, Vec<(f32, bool)>>,
    }

    impl InformativenessSamples {
        fn add(&mut self, family: &'static str, confidence: f32, correct: bool) {
            self.by_family
                .entry(family)
                .or_default()
                .push((confidence, correct));
        }

        fn add_replay(&mut self, series: &ReplaySeries, output: &SolveOutput) {
            self.add_channels(series, output);
            self.add_segments(series, output);
        }

        fn add_channels(&mut self, series: &ReplaySeries, output: &SolveOutput) {
            for (player, timeline) in joined_players(series, output) {
                for sample in &timeline.samples {
                    let idx =
                        sample_start_frame(series, sample).unwrap_or(sample.frame_index) as usize;

                    if player.frames.on_ground.get(idx).copied().unwrap_or(false) {
                        if let Some(raw) = player.replicated.throttle_raw.get(idx).copied() {
                            let centered = i16::from(raw) - 128;
                            if centered.abs() > THROTTLE_DEADZONE_RAW {
                                self.add(
                                    "throttle_sign",
                                    sample.throttle.confidence,
                                    centered.signum() == signum_f32(sample.throttle.value),
                                );
                            }
                        }
                    }

                    if let Some(raw) = player.replicated.steer_raw.get(idx).copied() {
                        self.add(
                            "steer_abs_error_le_0_15",
                            sample.steer.confidence,
                            (sample.steer.value - raw_axis(raw)).abs() <= STEER_TOLERANCE,
                        );
                    }

                    if let Some(truth) = player.replicated.boost_active_raw.get(idx).copied() {
                        self.add(
                            "boost_active",
                            sample.boost.confidence,
                            sample.boost.value == truth,
                        );
                    }

                    if let Some(truth) = player.replicated.handbrake.get(idx).copied() {
                        self.add(
                            "handbrake",
                            sample.handbrake.confidence,
                            sample.handbrake.value == truth,
                        );
                    }
                }
            }
        }

        fn add_segments(&mut self, series: &ReplaySeries, output: &SolveOutput) {
            let segmentation = segment_replay(series);
            let truth = coalesced_flip_truth(series, output);
            let predicted = solved_flip_intervals(output);
            let timelines: HashMap<_, _> = output
                .timelines
                .iter()
                .map(|timeline| (timeline.player_id.as_str(), timeline))
                .collect();
            for segmented_player in &segmentation.players {
                let Some(timeline) = timelines.get(segmented_player.player_id.as_str()) else {
                    continue;
                };
                for segment in &segmented_player.segments {
                    if segment.kind != crate::segment::SegmentKind::Air {
                        continue;
                    }
                    let Some(summary) = timeline
                        .segments
                        .iter()
                        .find(|summary| summary.id == segment.summary.id)
                    else {
                        continue;
                    };
                    let truth_present = truth.iter().any(|(player_id, frame)| {
                        player_id == &segmented_player.player_id
                            && *frame >= segment.frame_span.0
                            && *frame < segment.frame_span.1
                    });
                    let predicted_present = predicted.iter().any(|(player_id, frame)| {
                        player_id == &segmented_player.player_id
                            && *frame >= segment.frame_span.0
                            && *frame < segment.frame_span.1
                    });
                    self.add(
                        "air_segment_flip_presence",
                        summary.confidence,
                        truth_present == predicted_present,
                    );
                }
            }
        }

        fn print(mut self) {
            for (family, samples) in &mut self.by_family {
                samples.sort_by(|a, b| a.0.total_cmp(&b.0));
                let bottom = quartile_agreement(samples.iter().take(samples.len() / 4));
                let top = quartile_agreement(samples.iter().rev().take(samples.len() / 4));
                let auc = bin_auc(samples);
                println!(
                    "confidence_informativeness,family={},count={},bottom_q_agreement={:.3},top_q_agreement={:.3},separation={:.3},bin_auc={:.3}",
                    family,
                    samples.len(),
                    bottom,
                    top,
                    top - bottom,
                    auc,
                );
            }
        }
    }

    fn quartile_agreement<'a>(samples: impl Iterator<Item = &'a (f32, bool)>) -> f32 {
        let mut count = 0usize;
        let mut hits = 0usize;
        for (_, correct) in samples {
            count += 1;
            hits += usize::from(*correct);
        }
        share(hits, count)
    }

    fn bin_auc(samples: &[(f32, bool)]) -> f32 {
        let mut bins = [BinAcc::default(); CONFIDENCE_BINS];
        for (confidence, correct) in samples {
            let idx = ((confidence.clamp(0.0, 0.999_999) * CONFIDENCE_BINS as f32) as usize)
                .min(CONFIDENCE_BINS - 1);
            bins[idx].add(*confidence, *correct);
        }
        let occupied: Vec<_> = bins
            .into_iter()
            .enumerate()
            .filter(|(_, bin)| bin.count > 0)
            .collect();
        let mut wins = 0.0f32;
        let mut total = 0.0f32;
        for (left_idx, left) in &occupied {
            let left_rate = share(left.hits, left.count);
            for (right_idx, right) in &occupied {
                if right_idx <= left_idx {
                    continue;
                }
                let weight = (left.count * right.count) as f32;
                total += weight;
                let right_rate = share(right.hits, right.count);
                wins += if right_rate > left_rate {
                    weight
                } else if (right_rate - left_rate).abs() < f32::EPSILON {
                    weight * 0.5
                } else {
                    0.0
                };
            }
        }
        if total == 0.0 {
            0.5
        } else {
            wins / total
        }
    }

    #[cfg(feature = "sim")]
    fn strict_mask_ok(series: &ReplaySeries) -> bool {
        series.players.iter().all(|player| {
            player.replicated.throttle_raw.iter().all(|raw| *raw == 128)
                && player.replicated.steer_raw.iter().all(|raw| *raw == 128)
                && player.replicated.handbrake.iter().all(|value| !*value)
                && player
                    .replicated
                    .boost_active_raw
                    .iter()
                    .all(|value| !*value)
                && player
                    .replicated
                    .boost_amount_raw
                    .iter()
                    .all(|raw| *raw == 0)
                && player.component.events.is_empty()
                && player.component.jump_raw.iter().all(|raw| *raw == 0)
                && player.component.dodge_raw.iter().all(|raw| *raw == 0)
                && player.component.double_jump_raw.iter().all(|raw| *raw == 0)
                && player.component.boost_raw.iter().all(|raw| *raw == 0)
        })
    }

    #[cfg(feature = "sim")]
    fn print_continuous_channel_probe(name: &str, series: &ReplaySeries, output: &SolveOutput) {
        let mut audit = RulerAudit::default();
        let mut throttle = [
            ("throttle", std::array::from_fn(|_| SignStats::default())),
            ("pitch", std::array::from_fn(|_| SignStats::default())),
            ("neg_pitch", std::array::from_fn(|_| SignStats::default())),
        ];
        let mut steer = [
            ("steer", std::array::from_fn(|_| SteerStats::default())),
            ("yaw", std::array::from_fn(|_| SteerStats::default())),
            ("neg_yaw", std::array::from_fn(|_| SteerStats::default())),
        ];

        for (player, timeline) in joined_players(series, output) {
            let freshness = KinematicFreshness::from_frames(&player.frames);
            for sample in &timeline.samples {
                let start =
                    sample_start_frame(series, sample).unwrap_or(sample.frame_index) as usize;
                let end = sample.frame_index as usize;
                let grounded = player.frames.on_ground.get(start).copied().unwrap_or(false);
                audit.add(player, &freshness, start, end);

                if let Some(raw) = player.replicated.throttle_raw.get(start).copied() {
                    for (label, stats) in &mut throttle {
                        let value = match *label {
                            "throttle" => sample.throttle.value,
                            "pitch" => sample.pitch.value,
                            "neg_pitch" => -sample.pitch.value,
                            _ => unreachable!(),
                        };
                        add_scoped_sign(stats, grounded, raw, value);
                    }
                }

                if let Some(raw) = player.replicated.steer_raw.get(start).copied() {
                    let truth = raw_axis(raw);
                    for (label, stats) in &mut steer {
                        let value = match *label {
                            "steer" => sample.steer.value,
                            "yaw" => sample.yaw.value,
                            "neg_yaw" => -sample.yaw.value,
                            _ => unreachable!(),
                        };
                        add_scoped_steer(stats, grounded, truth, value);
                    }
                }
            }
        }

        println!(
            "criterion3_sample_audit,replay={},samples={},start_fresh={}/{},end_fresh={}/{},start_equals_end={},throttle_start_end_same={},steer_start_end_same={},boost_start_end_same={}",
            name,
            audit.samples,
            audit.start_fresh,
            audit.samples,
            audit.end_fresh,
            audit.samples,
            audit.start_equals_end,
            audit.throttle_same,
            audit.steer_same,
            audit.boost_same
        );

        for (label, by_scope) in throttle {
            let all_den = by_scope[0].den;
            for (scope, stats) in ["all", "ground", "air"].into_iter().zip(by_scope) {
                println!(
                    "criterion3_throttle,replay={},metric={},scope={},coverage={}/{},score={:.4},den={},r={:.4},pred_hist={},truth_hist={},confusion={}",
                    name,
                    label,
                    scope,
                    stats.den,
                    all_den,
                    stats.share(),
                    stats.den,
                    pearson(&stats.pairs),
                    fmt3(stats.pred_hist),
                    fmt3(stats.truth_hist),
                    fmt_confusion(stats.confusion)
                );
            }
        }

        for (label, by_scope) in steer {
            for (scope, stats) in ["all", "ground", "air"].into_iter().zip(by_scope) {
                println!(
                    "criterion3_steer,replay={},metric={},scope={},coverage={}/{},le015={:.4},den={},r={:.4},pred_hist={},truth_hist={},err_hist={}",
                    name,
                    label,
                    scope,
                    stats.den,
                    stats.den,
                    stats.share(),
                    stats.den,
                    pearson(&stats.pairs),
                    fmt5(stats.pred_hist),
                    fmt5(stats.truth_hist),
                    fmt6(stats.err_hist)
                );
            }
        }
    }

    #[cfg(feature = "sim")]
    fn print_boost_probe(name: &str, series: &ReplaySeries, output: &SolveOutput) {
        let truth = replicated_bool_edges(series, |player| &player.replicated.boost_active_raw);
        let pred = solved_bool_edges(output, |sample| sample.boost.value);
        let exact = f1_with_tolerance(&truth, &pred, 0);
        let tol1 = f1_with_tolerance(&truth, &pred, 1);
        let tol2 = f1_with_tolerance(&truth, &pred, 2);
        let coalesced =
            coalesced_bool_truth(series, output, |player| &player.replicated.boost_active_raw);
        let coalesced_tol1 = f1_with_tolerance(&coalesced, &pred, 1);
        let mut active = BoolStats::default();
        for (player, timeline) in joined_players(series, output) {
            for sample in &timeline.samples {
                let start =
                    sample_start_frame(series, sample).unwrap_or(sample.frame_index) as usize;
                if let Some(truth) = player.replicated.boost_active_raw.get(start).copied() {
                    active.add(truth, sample.boost.value);
                }
            }
        }

        println!(
            "criterion3_boost,replay={},sample_coverage={}/{},exact_f1={:.4},tol1_f1={:.4},tol2_f1={:.4},coalesced_tol1_f1={:.4},truth={},pred={},matched_tol1={},false_neg_tol1={},false_pos_tol1={},active_r={:.4},active_pred_hist=false:{},true:{},active_truth_hist=false:{},true:{},nearest_offsets={}",
            name,
            active.pairs.len(),
            active.pairs.len(),
            exact.f1,
            tol1.f1,
            tol2.f1,
            coalesced_tol1.f1,
            tol1.truth,
            tol1.predicted,
            tol1.matched,
            tol1.truth.saturating_sub(tol1.matched),
            tol1.predicted.saturating_sub(tol1.matched),
            pearson(&active.pairs),
            active.pred_false,
            active.pred_true,
            active.truth_false,
            active.truth_true,
            boost_offsets(&truth, &pred)
        );
    }

    #[cfg(feature = "sim")]
    fn coalesced_bool_truth(
        series: &ReplaySeries,
        output: &SolveOutput,
        field: impl Fn(&PlayerSeries) -> &[bool],
    ) -> HashSet<(String, u32)> {
        let raw = replicated_bool_edges(series, field);
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

    #[cfg(feature = "sim")]
    #[derive(Default)]
    struct RulerAudit {
        samples: usize,
        start_fresh: usize,
        end_fresh: usize,
        start_equals_end: usize,
        throttle_same: usize,
        steer_same: usize,
        boost_same: usize,
    }

    #[cfg(feature = "sim")]
    impl RulerAudit {
        fn add(
            &mut self,
            player: &PlayerSeries,
            freshness: &KinematicFreshness,
            start: usize,
            end: usize,
        ) {
            self.samples += 1;
            self.start_fresh += usize::from(freshness.is_fresh(start as u32));
            self.end_fresh += usize::from(freshness.is_fresh(end as u32));
            self.start_equals_end += usize::from(start == end);
            self.throttle_same += usize::from(
                player.replicated.throttle_raw.get(start)
                    == player.replicated.throttle_raw.get(end),
            );
            self.steer_same += usize::from(
                player.replicated.steer_raw.get(start) == player.replicated.steer_raw.get(end),
            );
            self.boost_same += usize::from(
                player.replicated.boost_active_raw.get(start)
                    == player.replicated.boost_active_raw.get(end),
            );
        }
    }

    #[cfg(feature = "sim")]
    #[derive(Default)]
    struct SignStats {
        den: usize,
        hit: usize,
        truth_hist: [usize; 3],
        pred_hist: [usize; 3],
        confusion: [[usize; 3]; 3],
        pairs: Vec<(f32, f32)>,
    }

    #[cfg(feature = "sim")]
    impl SignStats {
        fn add(&mut self, raw: u8, pred: f32) {
            let centered = i16::from(raw) - 128;
            if centered.abs() <= THROTTLE_DEADZONE_RAW {
                return;
            }
            let truth_sign = centered.signum();
            let pred_sign = signum_f32(pred);
            let truth_idx = sign_idx(truth_sign);
            let pred_idx = sign_idx(pred_sign);
            self.den += 1;
            self.hit += usize::from(truth_sign == pred_sign);
            self.truth_hist[truth_idx] += 1;
            self.pred_hist[pred_idx] += 1;
            self.confusion[truth_idx][pred_idx] += 1;
            self.pairs.push((pred, raw_axis(raw)));
        }

        fn share(&self) -> f32 {
            share(self.hit, self.den)
        }
    }

    #[cfg(feature = "sim")]
    #[derive(Default)]
    struct SteerStats {
        den: usize,
        hit: usize,
        truth_hist: [usize; 5],
        pred_hist: [usize; 5],
        err_hist: [usize; 6],
        pairs: Vec<(f32, f32)>,
    }

    #[cfg(feature = "sim")]
    impl SteerStats {
        fn add(&mut self, truth: f32, pred: f32) {
            let err = (pred - truth).abs();
            self.den += 1;
            self.hit += usize::from(err <= STEER_TOLERANCE);
            self.truth_hist[value_bin5(truth)] += 1;
            self.pred_hist[value_bin5(pred)] += 1;
            self.err_hist[err_bin6(err)] += 1;
            self.pairs.push((pred, truth));
        }

        fn share(&self) -> f32 {
            share(self.hit, self.den)
        }
    }

    #[cfg(feature = "sim")]
    #[derive(Default)]
    struct BoolStats {
        pred_false: usize,
        pred_true: usize,
        truth_false: usize,
        truth_true: usize,
        pairs: Vec<(f32, f32)>,
    }

    #[cfg(feature = "sim")]
    impl BoolStats {
        fn add(&mut self, truth: bool, pred: bool) {
            self.truth_false += usize::from(!truth);
            self.truth_true += usize::from(truth);
            self.pred_false += usize::from(!pred);
            self.pred_true += usize::from(pred);
            self.pairs.push((f32::from(pred), f32::from(truth)));
        }
    }

    #[cfg(feature = "sim")]
    fn add_scoped_sign(stats: &mut [SignStats; 3], grounded: bool, raw: u8, pred: f32) {
        stats[0].add(raw, pred);
        stats[if grounded { 1 } else { 2 }].add(raw, pred);
    }

    #[cfg(feature = "sim")]
    fn add_scoped_steer(stats: &mut [SteerStats; 3], grounded: bool, truth: f32, pred: f32) {
        stats[0].add(truth, pred);
        stats[if grounded { 1 } else { 2 }].add(truth, pred);
    }

    #[cfg(feature = "sim")]
    fn sign_idx(sign: i16) -> usize {
        match sign.cmp(&0) {
            std::cmp::Ordering::Less => 0,
            std::cmp::Ordering::Equal => 1,
            std::cmp::Ordering::Greater => 2,
        }
    }

    #[cfg(feature = "sim")]
    fn value_bin5(value: f32) -> usize {
        if value < -0.5 {
            0
        } else if value < -STEER_TOLERANCE {
            1
        } else if value <= STEER_TOLERANCE {
            2
        } else if value <= 0.5 {
            3
        } else {
            4
        }
    }

    #[cfg(feature = "sim")]
    fn err_bin6(value: f32) -> usize {
        if value <= 0.05 {
            0
        } else if value <= STEER_TOLERANCE {
            1
        } else if value <= 0.3 {
            2
        } else if value <= 0.5 {
            3
        } else if value <= 1.0 {
            4
        } else {
            5
        }
    }

    #[cfg(feature = "sim")]
    fn pearson(pairs: &[(f32, f32)]) -> f64 {
        if pairs.len() < 2 {
            return 0.0;
        }
        let n = pairs.len() as f64;
        let (sum_x, sum_y) = pairs.iter().fold((0.0, 0.0), |(sx, sy), (x, y)| {
            (sx + f64::from(*x), sy + f64::from(*y))
        });
        let mean_x = sum_x / n;
        let mean_y = sum_y / n;
        let (num, den_x, den_y) = pairs.iter().fold((0.0, 0.0, 0.0), |acc, (x, y)| {
            let dx = f64::from(*x) - mean_x;
            let dy = f64::from(*y) - mean_y;
            (acc.0 + dx * dy, acc.1 + dx * dx, acc.2 + dy * dy)
        });
        if den_x == 0.0 || den_y == 0.0 {
            0.0
        } else {
            num / (den_x.sqrt() * den_y.sqrt())
        }
    }

    #[cfg(feature = "sim")]
    fn boost_offsets(truth: &HashSet<(String, u32)>, pred: &HashSet<(String, u32)>) -> String {
        let mut hist: BTreeMap<i32, usize> = BTreeMap::new();
        for (player_id, pred_frame) in pred {
            if let Some(delta) = truth
                .iter()
                .filter(|(truth_player, truth_frame)| {
                    truth_player == player_id && truth_frame.abs_diff(*pred_frame) <= 5
                })
                .map(|(_, truth_frame)| *truth_frame as i32 - *pred_frame as i32)
                .min_by_key(|delta| delta.abs())
            {
                *hist.entry(delta).or_default() += 1;
            }
        }
        hist.into_iter()
            .map(|(delta, count)| format!("{delta}:{count}"))
            .collect::<Vec<_>>()
            .join("|")
    }

    #[cfg(feature = "sim")]
    fn fmt3(values: [usize; 3]) -> String {
        format!("neg:{}|zero:{}|pos:{}", values[0], values[1], values[2])
    }

    #[cfg(feature = "sim")]
    fn fmt5(values: [usize; 5]) -> String {
        format!(
            "lt-0.5:{}|-0.5..-0.15:{}|-0.15..0.15:{}|0.15..0.5:{}|gt0.5:{}",
            values[0], values[1], values[2], values[3], values[4]
        )
    }

    #[cfg(feature = "sim")]
    fn fmt6(values: [usize; 6]) -> String {
        format!(
            "<=0.05:{}|<=0.15:{}|<=0.30:{}|<=0.50:{}|<=1.00:{}|>1.00:{}",
            values[0], values[1], values[2], values[3], values[4], values[5]
        )
    }

    #[cfg(feature = "sim")]
    fn fmt_confusion(values: [[usize; 3]; 3]) -> String {
        format!(
            "truth_neg[pred_neg:{},pred_zero:{},pred_pos:{}]|truth_zero[pred_neg:{},pred_zero:{},pred_pos:{}]|truth_pos[pred_neg:{},pred_zero:{},pred_pos:{}]",
            values[0][0],
            values[0][1],
            values[0][2],
            values[1][0],
            values[1][1],
            values[1][2],
            values[2][0],
            values[2][1],
            values[2][2]
        )
    }

    #[cfg(feature = "sim")]
    fn gate_manifest_path() -> std::path::PathBuf {
        let raw = std::env::var("RLINPUT_GATE_MANIFEST")
            .expect("RLINPUT_GATE_MANIFEST should point to the frozen gate manifest");
        resolve_path(&repo_root(), &raw)
    }

    #[cfg(feature = "sim")]
    fn repo_root() -> std::path::PathBuf {
        std::path::Path::new(env!("CARGO_MANIFEST_DIR"))
            .parent()
            .and_then(std::path::Path::parent)
            .expect("rlinput crate should live under parsers/rlinput")
            .to_path_buf()
    }

    #[cfg(feature = "sim")]
    fn resolve_path(repo: &std::path::Path, raw: &str) -> std::path::PathBuf {
        let path = std::path::PathBuf::from(raw);
        if path.is_absolute() {
            path
        } else {
            repo.join(path)
        }
    }

    #[cfg(feature = "sim")]
    fn infer_gate_label(manifest: &std::path::Path) -> String {
        manifest
            .file_stem()
            .and_then(|name| name.to_str())
            .unwrap_or("gate")
            .replace("s1_", "")
            .replace("_set", "")
    }

    #[cfg(feature = "sim")]
    fn gate_series_dir(label: &str) -> std::path::PathBuf {
        if let Ok(raw) = std::env::var("RLINPUT_GATE_SERIES_DIR") {
            return resolve_path(&repo_root(), &raw);
        }
        std::env::temp_dir().join(format!(
            "rlcoach-wp10-{}-series-{}",
            sanitize_label(label),
            std::process::id()
        ))
    }

    #[cfg(feature = "sim")]
    fn sanitize_label(label: &str) -> String {
        label
            .chars()
            .map(|ch| if ch.is_ascii_alphanumeric() { ch } else { '-' })
            .collect()
    }

    #[cfg(feature = "sim")]
    fn gate_manifest_entries(manifest: &std::path::Path) -> Vec<String> {
        let file = std::fs::File::open(manifest).expect("gate manifest should open");
        let data: serde_json::Value =
            serde_json::from_reader(file).expect("gate manifest should parse as JSON");
        let mut out = Vec::new();
        for key in ["holdout", "fixtures", "seeded_draw"] {
            let Some(items) = data.get(key).and_then(serde_json::Value::as_array) else {
                continue;
            };
            for item in items {
                if let Some(filename) = item.get("filename").and_then(serde_json::Value::as_str) {
                    out.push(filename.to_string());
                }
            }
        }
        out
    }

    #[cfg(feature = "sim")]
    fn gate_replay_name(entry: &str) -> String {
        std::path::Path::new(entry)
            .file_stem()
            .and_then(|name| name.to_str())
            .unwrap_or(entry)
            .to_string()
    }

    #[cfg(feature = "sim")]
    fn export_and_load_gate_series(
        repo: &std::path::Path,
        entry: &str,
        series_dir: &std::path::Path,
    ) -> Result<ReplaySeries, String> {
        let replay = repo.join(entry);
        if !replay.exists() {
            return Err(format!("missing replay {}", replay.display()));
        }
        let out = series_dir.join(format!("{}.json", gate_replay_name(entry)));
        let output = std::process::Command::new(gate_python(repo)?)
            .current_dir(repo)
            .arg(repo.join("scripts/export_series_json.py"))
            .arg(&replay)
            .output()
            .map_err(|err| format!("export command failed to start: {err}"))?;
        if !output.status.success() {
            return Err(command_failure("export_series_json.py", &output));
        }
        std::fs::write(&out, &output.stdout)
            .map_err(|err| format!("failed to write {}: {err}", out.display()))?;
        let file = std::fs::File::open(&out)
            .map_err(|err| format!("failed to open exported {}: {err}", out.display()))?;
        serde_json::from_reader(file)
            .map_err(|err| format!("failed to parse exported {}: {err}", out.display()))
    }

    #[cfg(feature = "sim")]
    fn gate_python(repo: &std::path::Path) -> Result<std::path::PathBuf, String> {
        if let Ok(raw) = std::env::var("RLCOACH_PYTHON") {
            let path = std::path::PathBuf::from(raw);
            if path.exists() {
                return Ok(path);
            }
        }
        for candidate in [
            repo.join(".venv/bin/python"),
            std::path::PathBuf::from("/Users/treygoff/Code/rlcoach/.venv/bin/python"),
        ] {
            if candidate.exists() {
                return Ok(candidate);
            }
        }
        Err("set RLCOACH_PYTHON to a venv python; no worktree/source .venv found".to_string())
    }

    #[cfg(feature = "sim")]
    fn run_gate_resim(
        repo: &std::path::Path,
        manifest: &std::path::Path,
        series_dir: &std::path::Path,
    ) -> serde_json::Value {
        let output_json = series_dir.join("v1_resim_python_approximation.json");
        let result = gate_python(repo).and_then(|python| {
            let output = std::process::Command::new(python)
                .current_dir(repo)
                .arg(repo.join("scripts/v1_resim.py"))
                .arg("--manifest")
                .arg(manifest)
                .arg("--series-dir")
                .arg(series_dir)
                .arg("--corpus-dir")
                .arg(repo)
                .arg("--output-json")
                .arg(&output_json)
                .output()
                .map_err(|err| format!("v1_resim.py failed to start: {err}"))?;
            if !output.status.success() {
                return Err(command_failure("v1_resim.py", &output));
            }
            let file = std::fs::File::open(&output_json)
                .map_err(|err| format!("failed to open {}: {err}", output_json.display()))?;
            serde_json::from_reader(file)
                .map_err(|err| format!("failed to parse {}: {err}", output_json.display()))
        });
        match result {
            Ok(value) => value,
            Err(reason) => serde_json::json!({
                "schema_version": 1,
                "status": "failed",
                "reason": reason,
            }),
        }
    }

    #[cfg(feature = "sim")]
    fn command_failure(name: &str, output: &std::process::Output) -> String {
        let stdout = String::from_utf8_lossy(&output.stdout);
        let stderr = String::from_utf8_lossy(&output.stderr);
        format!(
            "{name} exited with {}; stdout={} stderr={}",
            output.status, stdout, stderr
        )
    }

    #[cfg(feature = "sim")]
    fn gate_report_json(
        label: &str,
        manifest: &std::path::Path,
        requested_replays: usize,
        failures: &[serde_json::Value],
        oracle: &OracleReport,
        resim: serde_json::Value,
        elapsed: std::time::Duration,
    ) -> serde_json::Value {
        let c4_median = resim_value(&resim, &["aggregate", "median_ratio_to_zero"]);
        let c4_p95 = resim_value(&resim, &["aggregate", "p95_ratio_to_zero"]);
        let c4_max_build = c4_max_build_ratio(&resim);
        serde_json::json!({
            "schema_version": 1,
            "label": label,
            "manifest": manifest.display().to_string(),
            "runner": "rlinput::calib::tests::gate_evaluation_report",
            "mode": "unseeded_strict_blind",
            "processed_replays": oracle.replay_count,
            "requested_replays": requested_replays,
            "export_failures": failures,
            "runtime_seconds": elapsed.as_secs_f64(),
            "criteria": [
                criterion_ge("c1_flip_interval_f1", oracle.flip_raw.f1, 0.95, "unseeded raw component-edge interval F1"),
                criterion_ge("c2_30hz_correct_interval_rate", oracle.flip_correct_interval_rate_raw, 0.98, "30Hz fallback correct recorded interval; c4 reported separately"),
                criterion_ge("c3_boost_edge_f1", oracle.blind.boost_edge_f1.f1, 0.95, "strict-blind boost edge F1"),
                criterion_ge("c3_jump_edge_f1", oracle.blind.jump_edge_f1.f1, 0.95, "strict-blind jump edge F1"),
                criterion_ge("c3_throttle_sign", oracle.blind.throttle_sign.share, 0.90, "outside |raw-128| > 13 deadzone"),
                criterion_ge("c3_steer_abs_error_le_0_15", oracle.blind.steer_abs_error_le_0_15.share, 0.85, "all frames"),
                criterion_le("c4_resim_median_ratio", c4_median, 0.25, "PYTHON_APPROXIMATION scripts/v1_resim.py median ratio to zero-input baseline"),
                criterion_le("c4_resim_p95_ratio", c4_p95, 0.50, "PYTHON_APPROXIMATION scripts/v1_resim.py p95 ratio to zero-input baseline"),
                criterion_le("c4_resim_max_build_median_vs_corpus_median", c4_max_build, 2.0, "PYTHON_APPROXIMATION build median solved error / corpus median solved error"),
                criterion_ge("c5_air_segment_coverage_conf_ge_0_7", oracle.coverage.coverage, 0.80, "air segments with segment confidence >= 0.7"),
            ],
            "diagnostics": {
                "flip_raw_unfiltered": oracle.flip_raw_unfiltered,
                "flip_coalesced_unfiltered": oracle.flip_coalesced_unfiltered,
                "flip_raw_pm1_interval": oracle.flip_raw_pm1_interval,
                "flip_coalesced_pm1_interval": oracle.flip_coalesced_pm1_interval,
                "amount_derived_boost_edges_diagnostic_only": oracle.amount_derived_boost_edges,
                "powerslide_steer_split": oracle.powerslide_steer_split,
                "resim_label": "PYTHON_APPROXIMATION",
                "resim_known_ceiling": "one-frame positional approximation from solver output controls, not the full Rust reference resim"
            },
            "per_replay": oracle.per_replay.iter().map(gate_replay_breakdown).collect::<Vec<_>>(),
            "oracle_report": oracle,
            "resim_python_approximation": resim,
        })
    }

    #[cfg(feature = "sim")]
    fn criterion_ge(name: &str, measured: f32, threshold: f64, note: &str) -> serde_json::Value {
        criterion_json(name, Some(f64::from(measured)), ">=", threshold, note)
    }

    #[cfg(feature = "sim")]
    fn criterion_le(
        name: &str,
        measured: Option<f64>,
        threshold: f64,
        note: &str,
    ) -> serde_json::Value {
        criterion_json(name, measured, "<=", threshold, note)
    }

    #[cfg(feature = "sim")]
    fn criterion_json(
        name: &str,
        measured: Option<f64>,
        op: &str,
        threshold: f64,
        note: &str,
    ) -> serde_json::Value {
        let pass = measured.map(|value| match op {
            ">=" => value >= threshold,
            "<=" => value <= threshold,
            _ => false,
        });
        serde_json::json!({
            "criterion": name,
            "measured": measured,
            "threshold": threshold,
            "operator": op,
            "pass": pass,
            "note": note,
        })
    }

    #[cfg(feature = "sim")]
    fn resim_value(report: &serde_json::Value, path: &[&str]) -> Option<f64> {
        let mut current = report;
        for key in path {
            current = current.get(*key)?;
        }
        current.as_f64()
    }

    #[cfg(feature = "sim")]
    fn c4_max_build_ratio(report: &serde_json::Value) -> Option<f64> {
        let corpus = resim_value(report, &["aggregate", "e_solved_median"])?;
        if corpus == 0.0 {
            return None;
        }
        report
            .get("by_build_bucket")?
            .as_object()?
            .values()
            .filter_map(|bucket| {
                bucket
                    .get("e_solved_median")
                    .and_then(serde_json::Value::as_f64)
                    .map(|median| median / corpus)
            })
            .max_by(f64::total_cmp)
    }

    #[cfg(feature = "sim")]
    fn gate_replay_breakdown(replay: &ReplayOracleReport) -> serde_json::Value {
        serde_json::json!({
            "replay": replay.replay,
            "build_bucket": replay.build_bucket,
            "player_count": replay.player_count,
            "flip_raw": replay.flip_raw,
            "flip_raw_unfiltered_truth": replay.flip_raw_unfiltered.truth,
            "flip_raw_pm1_interval": replay.flip_raw_pm1_interval,
            "flip_correct_interval_rate_raw": replay.flip_raw.recall,
            "boost_edge_f1": replay.blind.boost_edge_f1,
            "jump_edge_f1": replay.blind.jump_edge_f1,
            "throttle_sign": replay.blind.throttle_sign,
            "steer_abs_error_le_0_15": replay.blind.steer_abs_error_le_0_15,
            "amount_derived_boost_edges_diagnostic_only": replay.amount_derived_boost_edges,
            "powerslide_steer_split": replay.powerslide_steer_split,
            "coverage": replay.coverage,
        })
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
