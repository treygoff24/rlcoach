use crate::timeline::AmbiguityFlags;
use serde::{Deserialize, Serialize};

#[derive(Clone, Copy, Debug, PartialEq, Serialize, Deserialize)]
pub struct LatticeConfig {
    pub tick_rate: f64,
    pub long_gap_seconds: f64,
    pub cadence_fraction_tolerance: f64,
    pub cadence_persistence_intervals: usize,
    pub nominal_interval_ticks: u64,
}

impl Default for LatticeConfig {
    fn default() -> Self {
        Self {
            tick_rate: 120.0,
            long_gap_seconds: 0.15,
            cadence_fraction_tolerance: 0.35,
            cadence_persistence_intervals: 3,
            nominal_interval_ticks: 4,
        }
    }
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct SegmentLattice {
    pub intervals: Vec<LatticeInterval>,
    pub diagnostics: LatticeDiagnostics,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct LatticeInterval {
    pub frame_index: u32,
    pub tick_range: (u64, u64),
    pub time_range: (f64, f64),
    pub flags: AmbiguityFlags,
}

#[derive(Clone, Debug, Default, PartialEq, Serialize, Deserialize)]
pub struct LatticeDiagnostics {
    pub nonstandard_cadence: bool,
    pub first_nonstandard_frame: Option<u32>,
}

pub fn build_segment_lattice(start_frame_index: u32, deltas: &[f32]) -> SegmentLattice {
    build_segment_lattice_with_config(start_frame_index, deltas, LatticeConfig::default())
}

pub fn build_segment_lattice_with_config(
    start_frame_index: u32,
    deltas: &[f32],
    config: LatticeConfig,
) -> SegmentLattice {
    let mut intervals = Vec::with_capacity(deltas.len());
    let mut diagnostics = LatticeDiagnostics::default();
    let mut acc = 0.0f64;
    let mut prev_tick = 0u64;
    let mut prev_time = 0.0f64;
    let mut pending_frame = start_frame_index;
    let mut pending_flags = AmbiguityFlags::empty();
    let mut nonstandard_run = 0usize;
    let mut run_first_frame = None;

    for (offset, delta) in deltas.iter().copied().enumerate() {
        let frame_index = start_frame_index + offset as u32;
        if delta == 0.0 {
            pending_frame = frame_index + 1;
            pending_flags |= AmbiguityFlags::DUPLICATE_FRAME;
            continue;
        }

        acc += f64::from(delta);
        let tick = round_half_even(acc * config.tick_rate);
        let mut flags = pending_flags;
        if f64::from(delta) > config.long_gap_seconds {
            flags |= AmbiguityFlags::LONG_GAP;
        }

        let interval_ticks = tick.saturating_sub(prev_tick);
        if tick > prev_tick {
            intervals.push(LatticeInterval {
                frame_index: pending_frame,
                tick_range: (prev_tick, tick),
                time_range: (prev_time, acc),
                flags,
            });
            prev_tick = tick;
            prev_time = acc;
            pending_flags = AmbiguityFlags::empty();
        } else {
            pending_flags |= AmbiguityFlags::DUPLICATE_FRAME;
        }
        pending_frame = frame_index + 1;

        let fractional_drift = (acc * config.tick_rate - tick as f64).abs();
        let nonstandard = fractional_drift > config.cadence_fraction_tolerance
            || interval_ticks != config.nominal_interval_ticks;
        if nonstandard {
            if nonstandard_run == 0 {
                run_first_frame = Some(frame_index);
            }
            nonstandard_run += 1;
            if nonstandard_run >= config.cadence_persistence_intervals {
                diagnostics.nonstandard_cadence = true;
                diagnostics.first_nonstandard_frame = run_first_frame;
            }
        } else {
            nonstandard_run = 0;
            run_first_frame = None;
        }
    }

    SegmentLattice {
        intervals,
        diagnostics,
    }
}

pub fn round_half_even(value: f64) -> u64 {
    let floor = value.floor();
    let frac = value - floor;
    if (frac - 0.5).abs() < 1e-12 {
        let floor_u64 = floor as u64;
        if floor_u64.is_multiple_of(2) {
            floor_u64
        } else {
            floor_u64 + 1
        }
    } else if frac < 0.5 {
        floor as u64
    } else {
        floor as u64 + 1
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn nominal_thirty_hz_interval_is_four_ticks() {
        let lattice = build_segment_lattice(0, &[1.0 / 30.0]);
        assert_eq!(lattice.intervals[0].tick_range, (0, 4));
        assert!(!lattice.diagnostics.nonstandard_cadence);
    }

    #[test]
    fn delta_zero_merges_and_keeps_later_observation() {
        let lattice = build_segment_lattice(10, &[0.0, 1.0 / 30.0]);
        assert_eq!(lattice.intervals.len(), 1);
        assert_eq!(lattice.intervals[0].frame_index, 11);
        assert_eq!(lattice.intervals[0].tick_range, (0, 4));
        assert!(lattice.intervals[0]
            .flags
            .contains(AmbiguityFlags::DUPLICATE_FRAME));
    }

    #[test]
    fn sub_tick_delta_merges_and_keeps_later_observation() {
        let lattice = build_segment_lattice(10, &[0.001, 1.0 / 30.0]);
        assert_eq!(lattice.intervals[0].frame_index, 11);
        assert!(lattice.intervals[0]
            .flags
            .contains(AmbiguityFlags::DUPLICATE_FRAME));
    }

    #[test]
    fn long_gap_is_tolerated_and_flagged() {
        let lattice = build_segment_lattice(0, &[0.19]);
        assert_eq!(lattice.intervals.len(), 1);
        assert_eq!(lattice.intervals[0].tick_range, (0, 23));
        assert!(lattice.intervals[0]
            .flags
            .contains(AmbiguityFlags::LONG_GAP));
    }

    #[test]
    fn f64_accumulation_stays_within_half_tick_over_match_segment() {
        let deltas = vec![1.0f32 / 30.0; 9_000];
        let lattice = build_segment_lattice(0, &deltas);
        let final_tick = lattice
            .intervals
            .last()
            .expect("synthetic segment should emit intervals")
            .tick_range
            .1;
        let drift = (final_tick as f64 - 9_000.0 * 4.0).abs();
        assert!(drift < 0.5, "tick drift was {drift}");
    }

    #[test]
    fn cadence_guard_fires_on_persistent_24hz() {
        let deltas = vec![1.0f32 / 24.0; 8];
        let lattice = build_segment_lattice(0, &deltas);
        assert!(lattice.diagnostics.nonstandard_cadence);
        assert_eq!(lattice.diagnostics.first_nonstandard_frame, Some(0));
    }

    #[test]
    fn half_even_rounds_ties_to_even_tick() {
        assert_eq!(round_half_even(2.5), 2);
        assert_eq!(round_half_even(3.5), 4);
    }
}
