use crate::{
    consts::{
        DODGE_COMPONENT_DEADZONE, DODGE_DEADZONE, DOUBLEJUMP_MAX_DELAY, FLIP_PITCHLOCK_END_TIME,
        FLIP_TORQUE_TIME, FLIP_TORQUE_X, FLIP_TORQUE_Y, FLIP_Z_DAMP_START, FLIP_Z_DAMP_TORQUE_END,
        JUMP_ACCEL, JUMP_MAX_TIME, JUMP_MIN_TIME, JUMP_PRE_MIN_ACCEL_SCALE,
    },
    model::{ComponentEventIn, ComponentKind, ComponentStream},
};
use serde::{Deserialize, Serialize};

/// Stateful seeded tracker for one car.
///
/// WP3 keeps this exact-state only: unseeded hypothesis branching in WP7 can wrap
/// cloned `CarTracker` values and collapse the winning branch after fit scoring.
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct CarTracker {
    pub contact: ContactState,
    pub jump: JumpState,
    pub second: SecondAction,
    pub boost: BoostTracker,
    tick_rate: f64,
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
pub enum ContactState {
    Grounded { since_tick: u64 },
    Airborne { liftoff_tick: u64 },
    Demolished { until_tick: Option<u64> },
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
pub enum JumpState {
    Idle,
    Holding {
        press_tick: u64,
    },
    Released {
        press_tick: u64,
        release_tick: u64,
        jump_end_tick: u64,
    },
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub enum SecondAction {
    Unavailable,
    Available { deadline_tick: u64 },
    UsedDodge(FlipPhase),
    UsedDoubleJump { tick: u64 },
    Expired,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct BoostTracker {
    pub active: bool,
    pub amount_estimate: f32,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct FlipPhase {
    pub start_tick: u64,
    tick_rate: f64,
    /// RocketSim `flipRelTorque.(x,y)`. `[0, 0]` means a stall.
    pub rel_torque: [f32; 2],
    pub cancel: CancelProfile,
    /// False for pure side flips (`flipRelTorque.y == 0`) and stalls.
    pub cancel_possible: bool,
}

/// `dodge_torque` replay-vector semantics, verified on `Replay_files/0925.replay`.
///
/// The payload is torque-scaled, not unit-length: across 378 raw vector events,
/// `abs(x)` capped at `2.60 == FLIP_TORQUE_X / 100`, `abs(y)` capped at
/// `2.24 == FLIP_TORQUE_Y / 100`, `z` was always zero, and
/// `sqrt((x/2.60)^2 + (y/2.24)^2)` stayed in `[0.9975, 1.0028]`
/// (median `1.0000`). Rotating the event vector from car-local to world axes
/// aligned best with the angular-velocity step into the event frame
/// (prev→current median cosine `0.944`, 176/222 positive nonzero samples),
/// matching network update timing. The tracker therefore divides by the
/// per-axis torque constants, then normalizes replay quantization noise away
/// before storing RocketSim `flipRelTorque`.
pub fn dodge_torque_vector_to_rel_torque(vector: [f32; 3]) -> [f32; 2] {
    let rel_torque = [
        vector[0] * 100.0 / FLIP_TORQUE_X,
        vector[1] * 100.0 / FLIP_TORQUE_Y,
    ];
    normalize_or_zero(rel_torque)
}

#[derive(Clone, Debug, Default, PartialEq, Serialize, Deserialize)]
pub struct CancelProfile {
    pub intervals: Vec<CancelInterval>,
}

#[derive(Clone, Copy, Debug, PartialEq, Serialize, Deserialize)]
pub struct CancelInterval {
    pub tick_range: (u64, u64),
    pub pitch: f32,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
pub struct CounterDelta {
    pub previous: u8,
    pub current: u8,
    /// Raw counter advance modulo 256 (`254 -> 2 == +4`).
    pub delta_mod_256: u8,
    /// Conservative edge lower bound. Even nonzero deltas are sub-frame
    /// toggle pairs and therefore expose at least two edges.
    pub min_toggle_edges: u8,
    pub net_parity_flip: bool,
    pub has_subframe_toggles: bool,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct ReconstructedEdge {
    pub frame_index: u32,
    pub t: f64,
    pub component: ComponentKind,
    pub source: EdgeEvidence,
    pub vector: Option<[f32; 3]>,
    pub counter_delta: Option<CounterDelta>,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
pub enum EdgeEvidence {
    VectorEvent,
    RawCounter,
}

#[derive(Clone, Copy, Debug, PartialEq, Serialize, Deserialize)]
pub enum SecondActionClass {
    DoubleJump,
    Dodge { dir: [f32; 2], rel_torque: [f32; 2] },
    Stall,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
pub enum TrackerError {
    NotAirborne,
    SecondActionUnavailable,
    SecondActionExpired,
    SecondActionAlreadyUsed,
    CannotFirstJumpFromCurrentContact,
    JumpNotHolding,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct TrackerBranch {
    pub tracker: CarTracker,
    pub score: f64,
    pub open_intervals: u8,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct BranchingTracker {
    branches: Vec<TrackerBranch>,
    beam_width: usize,
}

impl BranchingTracker {
    pub const DEFAULT_BEAM_WIDTH: usize = 4;
    pub const MAX_OPEN_INTERVALS: u8 = 2;

    pub fn new(tracker: CarTracker) -> Self {
        Self {
            branches: vec![TrackerBranch {
                tracker,
                score: 0.0,
                open_intervals: 0,
            }],
            beam_width: Self::DEFAULT_BEAM_WIDTH,
        }
    }

    pub fn branches(&self) -> &[TrackerBranch] {
        &self.branches
    }

    pub fn best_tracker(&self) -> &CarTracker {
        &self
            .branches
            .iter()
            .min_by(|a, b| a.score.total_cmp(&b.score))
            .expect("BranchingTracker always keeps at least one branch")
            .tracker
    }

    pub fn len(&self) -> usize {
        self.branches.len()
    }

    pub fn is_empty(&self) -> bool {
        self.branches.is_empty()
    }

    pub fn expand<I, F>(&mut self, scored_transitions: I, mut apply: F)
    where
        I: IntoIterator<Item = f64>,
        F: FnMut(&CarTracker, usize) -> Option<CarTracker>,
    {
        let scored_transitions: Vec<_> = scored_transitions.into_iter().collect();
        let ambiguous = scored_transitions.len() > 1;
        let mut next = Vec::new();
        for branch in &self.branches {
            for (transition_index, score_delta) in scored_transitions.iter().copied().enumerate() {
                if let Some(tracker) = apply(&branch.tracker, transition_index) {
                    next.push(TrackerBranch {
                        tracker,
                        score: branch.score + score_delta,
                        open_intervals: if ambiguous {
                            branch.open_intervals.saturating_add(1)
                        } else {
                            0
                        },
                    });
                }
            }
        }
        next.sort_by(|a, b| a.score.total_cmp(&b.score));
        next.truncate(self.beam_width);
        self.branches = next;
        if self
            .branches
            .iter()
            .any(|branch| branch.open_intervals > Self::MAX_OPEN_INTERVALS)
        {
            self.collapse_to_best();
        }
    }

    pub fn advance_unresolved(&mut self) {
        for branch in &mut self.branches {
            branch.open_intervals = branch.open_intervals.saturating_add(1);
        }
        if self
            .branches
            .iter()
            .any(|branch| branch.open_intervals > Self::MAX_OPEN_INTERVALS)
        {
            self.collapse_to_best();
        }
    }

    pub fn collapse_to_best(&mut self) {
        if let Some(best) = self
            .branches
            .iter()
            .min_by(|a, b| a.score.total_cmp(&b.score))
            .cloned()
        {
            self.branches = vec![TrackerBranch {
                open_intervals: 0,
                ..best
            }];
        }
    }

    pub fn into_best(mut self) -> CarTracker {
        self.collapse_to_best();
        self.branches
            .into_iter()
            .next()
            .expect("BranchingTracker always keeps at least one branch")
            .tracker
    }
}

impl CarTracker {
    pub fn new_grounded(since_tick: u64) -> Self {
        Self::new_grounded_with_tick_rate(since_tick, 120.0)
    }

    pub fn new_grounded_with_tick_rate(since_tick: u64, tick_rate: f64) -> Self {
        Self {
            contact: ContactState::Grounded { since_tick },
            jump: JumpState::Idle,
            second: SecondAction::Unavailable,
            boost: BoostTracker {
                active: false,
                amount_estimate: 0.0,
            },
            tick_rate,
        }
    }

    pub fn set_airborne(&mut self, liftoff_tick: u64) {
        self.contact = ContactState::Airborne { liftoff_tick };
    }

    pub fn set_grounded(&mut self, since_tick: u64) {
        self.contact = ContactState::Grounded { since_tick };
        self.jump = JumpState::Idle;
        self.second = SecondAction::Unavailable;
    }

    pub fn first_jump_press(&mut self, tick: u64) -> Result<(), TrackerError> {
        if !matches!(self.contact, ContactState::Grounded { .. }) {
            return Err(TrackerError::CannotFirstJumpFromCurrentContact);
        }
        self.contact = ContactState::Airborne { liftoff_tick: tick };
        self.jump = JumpState::Holding { press_tick: tick };
        let provisional_deadline = tick + self.ticks(JUMP_MAX_TIME + DOUBLEJUMP_MAX_DELAY);
        self.second = SecondAction::Available {
            deadline_tick: provisional_deadline,
        };
        Ok(())
    }

    pub fn jump_release(&mut self, release_tick: u64) -> Result<u64, TrackerError> {
        let JumpState::Holding { press_tick } = self.jump else {
            return Err(TrackerError::JumpNotHolding);
        };
        let jump_end_tick = self.jump_end_tick(press_tick, release_tick);
        self.jump = JumpState::Released {
            press_tick,
            release_tick,
            jump_end_tick,
        };
        if matches!(self.second, SecondAction::Available { .. }) {
            self.second = SecondAction::Available {
                deadline_tick: jump_end_tick + self.ticks(DOUBLEJUMP_MAX_DELAY),
            };
        }
        Ok(jump_end_tick)
    }

    pub fn advance_to(&mut self, tick: u64) {
        if let SecondAction::Available { deadline_tick } = self.second {
            if tick >= deadline_tick {
                self.second = SecondAction::Expired;
            }
        }
    }

    pub fn second_action_from_controls(
        &mut self,
        tick: u64,
        pitch: f32,
        yaw: f32,
        roll: f32,
    ) -> Result<SecondActionClass, TrackerError> {
        let class = classify_second_action_controls(pitch, yaw, roll);
        self.use_second_action(tick, class)?;
        Ok(class)
    }

    pub fn second_action_from_dodge_torque_vector(
        &mut self,
        tick: u64,
        vector: [f32; 3],
    ) -> Result<SecondActionClass, TrackerError> {
        let class = classify_dodge_torque_vector(vector);
        self.use_second_action(tick, class)?;
        Ok(class)
    }

    fn use_second_action(
        &mut self,
        tick: u64,
        class: SecondActionClass,
    ) -> Result<(), TrackerError> {
        if !matches!(self.contact, ContactState::Airborne { .. }) {
            return Err(TrackerError::NotAirborne);
        }
        match self.second {
            SecondAction::Available { deadline_tick } if tick < deadline_tick => {}
            SecondAction::Available { .. } | SecondAction::Expired => {
                return Err(TrackerError::SecondActionExpired);
            }
            SecondAction::Unavailable => return Err(TrackerError::SecondActionUnavailable),
            SecondAction::UsedDodge(_) | SecondAction::UsedDoubleJump { .. } => {
                return Err(TrackerError::SecondActionAlreadyUsed);
            }
        }

        self.second = match class {
            SecondActionClass::DoubleJump => SecondAction::UsedDoubleJump { tick },
            SecondActionClass::Dodge { rel_torque, .. } => {
                SecondAction::UsedDodge(FlipPhase::new(tick, rel_torque, self.tick_rate))
            }
            SecondActionClass::Stall => {
                SecondAction::UsedDodge(FlipPhase::new(tick, [0.0, 0.0], self.tick_rate))
            }
        };
        Ok(())
    }

    pub fn jump_end_tick(&self, press_tick: u64, release_tick: u64) -> u64 {
        let min_end = press_tick + self.ticks(JUMP_MIN_TIME);
        let max_end = press_tick + self.ticks(JUMP_MAX_TIME);
        release_tick.clamp(min_end, max_end)
    }

    pub fn jump_hold_accel_at(&self, tick: u64) -> Option<f32> {
        let (press_tick, end_tick) = match self.jump {
            JumpState::Holding { press_tick } => {
                (press_tick, press_tick + self.ticks(JUMP_MAX_TIME))
            }
            JumpState::Released {
                press_tick,
                jump_end_tick,
                ..
            } => (press_tick, jump_end_tick),
            JumpState::Idle => return None,
        };
        if tick >= end_tick {
            return None;
        }
        if tick < press_tick + self.ticks(JUMP_MIN_TIME) {
            Some(JUMP_ACCEL * JUMP_PRE_MIN_ACCEL_SCALE)
        } else {
            Some(JUMP_ACCEL)
        }
    }

    fn ticks(&self, seconds: f32) -> u64 {
        seconds_to_ticks(seconds, self.tick_rate)
    }
}

impl FlipPhase {
    pub fn new(start_tick: u64, rel_torque: [f32; 2], tick_rate: f64) -> Self {
        let cancel_possible = rel_torque[1] != 0.0;
        Self {
            start_tick,
            tick_rate,
            rel_torque,
            cancel: CancelProfile::default(),
            cancel_possible,
        }
    }

    pub fn torque_end_tick(&self) -> u64 {
        self.start_tick + seconds_to_ticks(FLIP_TORQUE_TIME, self.tick_rate)
    }

    pub fn pitchlock_end_tick(&self) -> u64 {
        self.start_tick + seconds_to_ticks(FLIP_PITCHLOCK_END_TIME, self.tick_rate)
    }

    pub fn z_damp_tick_range(&self) -> (u64, u64) {
        (
            self.start_tick + seconds_to_ticks(FLIP_Z_DAMP_START, self.tick_rate),
            self.start_tick + seconds_to_ticks(FLIP_Z_DAMP_TORQUE_END, self.tick_rate),
        )
    }

    pub fn is_stall(&self) -> bool {
        self.rel_torque == [0.0, 0.0]
    }
}

pub fn seconds_to_ticks(seconds: f32, tick_rate: f64) -> u64 {
    (f64::from(seconds) * tick_rate).round() as u64
}

pub fn raw_counter_delta(previous: u8, current: u8) -> CounterDelta {
    let delta_mod_256 = current.wrapping_sub(previous);
    CounterDelta {
        previous,
        current,
        delta_mod_256,
        min_toggle_edges: match delta_mod_256 {
            0 => 0,
            delta if delta.is_multiple_of(2) => 2,
            _ => 1,
        },
        net_parity_flip: !delta_mod_256.is_multiple_of(2),
        has_subframe_toggles: delta_mod_256 != 0 && delta_mod_256.is_multiple_of(2),
    }
}

pub fn reconstruct_seeded_edges(stream: &ComponentStream) -> Vec<ReconstructedEdge> {
    let mut edges: Vec<_> = stream.events.iter().filter_map(vector_edge).collect();

    if !has_vector_events(&stream.events, ComponentKind::DodgeTorque) {
        add_raw_counter_edges(&mut edges, &stream.dodge_raw, ComponentKind::DodgeTorque);
    }
    if !has_vector_events(&stream.events, ComponentKind::DoubleJumpImpulse) {
        add_raw_counter_edges(
            &mut edges,
            &stream.double_jump_raw,
            ComponentKind::DoubleJumpImpulse,
        );
    }
    add_raw_counter_edges(&mut edges, &stream.jump_raw, ComponentKind::Jump);
    add_raw_counter_edges(&mut edges, &stream.boost_raw, ComponentKind::Boost);
    edges.sort_by(|a, b| {
        a.frame_index
            .cmp(&b.frame_index)
            .then_with(|| a.t.total_cmp(&b.t))
    });
    edges
}

fn vector_edge(event: &ComponentEventIn) -> Option<ReconstructedEdge> {
    match event.component {
        ComponentKind::DodgeTorque | ComponentKind::DoubleJumpImpulse if event.vector.is_some() => {
            Some(ReconstructedEdge {
                frame_index: event.frame_index,
                t: event.t,
                component: event.component,
                source: EdgeEvidence::VectorEvent,
                vector: event.vector,
                counter_delta: None,
            })
        }
        _ => None,
    }
}

fn has_vector_events(events: &[ComponentEventIn], component: ComponentKind) -> bool {
    events
        .iter()
        .any(|event| event.component == component && event.vector.is_some())
}

fn add_raw_counter_edges(
    edges: &mut Vec<ReconstructedEdge>,
    raw_values: &[u8],
    component: ComponentKind,
) {
    for (idx, pair) in raw_values.windows(2).enumerate() {
        let delta = raw_counter_delta(pair[0], pair[1]);
        if delta.delta_mod_256 == 0 {
            continue;
        }
        edges.push(ReconstructedEdge {
            frame_index: idx as u32 + 1,
            t: 0.0,
            component,
            source: EdgeEvidence::RawCounter,
            vector: None,
            counter_delta: Some(delta),
        });
    }
}

pub fn classify_second_action_controls(pitch: f32, yaw: f32, roll: f32) -> SecondActionClass {
    if pitch.abs() + yaw.abs() + roll.abs() < DODGE_DEADZONE {
        return SecondActionClass::DoubleJump;
    }

    // Car.cpp:733-737: the pre-normalize deadzone zeroes the direction only when BOTH
    // raw components are inside 0.1 (a stall); a single small component is preserved
    // through normalization. Per-component zeroing of the NORMALIZED direction applies
    // to the impulse only (engine-side), never to flipRelTorque.
    let dir = [-pitch, yaw + roll];
    if dir[0].abs() < DODGE_COMPONENT_DEADZONE && dir[1].abs() < DODGE_COMPONENT_DEADZONE {
        return SecondActionClass::Stall;
    }
    normalize_dodge_dir(dir)
}

pub fn classify_dodge_torque_vector(vector: [f32; 3]) -> SecondActionClass {
    let rel_torque = dodge_torque_vector_to_rel_torque(vector);
    if rel_torque[0].abs() < DODGE_COMPONENT_DEADZONE
        && rel_torque[1].abs() < DODGE_COMPONENT_DEADZONE
    {
        return SecondActionClass::Stall;
    }
    let dodge_dir = [rel_torque[1], -rel_torque[0]];
    let norm = (dodge_dir[0] * dodge_dir[0] + dodge_dir[1] * dodge_dir[1]).sqrt();
    if norm == 0.0 {
        SecondActionClass::Stall
    } else {
        SecondActionClass::Dodge {
            dir: [dodge_dir[0] / norm, dodge_dir[1] / norm],
            rel_torque,
        }
    }
}

fn normalize_dodge_dir(dir: [f32; 2]) -> SecondActionClass {
    let Some(dir) = normalize_nonzero(dir) else {
        return SecondActionClass::Stall;
    };
    SecondActionClass::Dodge {
        dir,
        rel_torque: [-dir[1], dir[0]],
    }
}

fn normalize_or_zero(vector: [f32; 2]) -> [f32; 2] {
    normalize_nonzero(vector).unwrap_or([0.0, 0.0])
}

fn normalize_nonzero(vector: [f32; 2]) -> Option<[f32; 2]> {
    let norm = (vector[0] * vector[0] + vector[1] * vector[1]).sqrt();
    if norm == 0.0 {
        None
    } else {
        Some([vector[0] / norm, vector[1] / norm])
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn raw_counter_delta_uses_mod_256_wrap() {
        let delta = raw_counter_delta(254, 2);
        assert_eq!(delta.delta_mod_256, 4);
        assert_eq!(delta.min_toggle_edges, 2);
        assert!(!delta.net_parity_flip);
        assert!(delta.has_subframe_toggles);
    }

    #[test]
    fn odd_delta_is_net_parity_flip() {
        let delta = raw_counter_delta(7, 10);
        assert_eq!(delta.delta_mod_256, 3);
        assert_eq!(delta.min_toggle_edges, 1);
        assert!(delta.net_parity_flip);
        assert!(!delta.has_subframe_toggles);
    }

    #[test]
    fn even_nonzero_delta_marks_subframe_toggle_pair() {
        let delta = raw_counter_delta(10, 12);
        assert_eq!(delta.delta_mod_256, 2);
        assert_eq!(delta.min_toggle_edges, 2);
        assert!(!delta.net_parity_flip);
        assert!(delta.has_subframe_toggles);
    }

    #[test]
    fn vector_events_are_preferred_over_raw_counters() {
        let stream = ComponentStream {
            jump_raw: vec![0, 1],
            dodge_raw: vec![0, 2],
            double_jump_raw: vec![0, 2],
            boost_raw: vec![0, 0],
            events: vec![
                ComponentEventIn {
                    t: 1.0,
                    frame_index: 30,
                    component: ComponentKind::DodgeTorque,
                    vector: Some([2.6, 0.0, 0.0]),
                    raw_value: None,
                },
                ComponentEventIn {
                    t: 1.1,
                    frame_index: 33,
                    component: ComponentKind::DoubleJumpImpulse,
                    vector: Some([0.0, 0.0, 291.0]),
                    raw_value: None,
                },
            ],
        };
        let edges = reconstruct_seeded_edges(&stream);
        assert_eq!(
            edges
                .iter()
                .filter(|edge| edge.component == ComponentKind::DodgeTorque)
                .count(),
            1
        );
        assert_eq!(
            edges
                .iter()
                .filter(|edge| edge.component == ComponentKind::DoubleJumpImpulse)
                .count(),
            1
        );
        assert_eq!(
            edges
                .iter()
                .filter(|edge| edge.component == ComponentKind::Jump)
                .count(),
            1
        );
    }

    #[test]
    fn no_dodge_without_second_action_window() {
        let mut tracker = CarTracker::new_grounded(0);
        tracker.set_airborne(0);
        assert_eq!(
            tracker.second_action_from_controls(10, 0.0, 1.0, 0.0),
            Err(TrackerError::SecondActionUnavailable)
        );
    }

    #[test]
    fn no_second_action_after_deadline() {
        let mut tracker = CarTracker::new_grounded(0);
        tracker.first_jump_press(0).unwrap();
        let jump_end = tracker.jump_release(3).unwrap();
        tracker.advance_to(jump_end + seconds_to_ticks(DOUBLEJUMP_MAX_DELAY, 120.0));
        assert_eq!(
            tracker.second_action_from_controls(154, 0.0, 0.0, 0.0),
            Err(TrackerError::SecondActionExpired)
        );
    }

    #[test]
    fn stall_classification_survives_control_deadzone_ordering() {
        let class = classify_second_action_controls(0.05, 0.30, -0.25);
        assert_eq!(class, SecondActionClass::Stall);
    }

    #[test]
    fn below_dodge_deadzone_is_double_jump() {
        let class = classify_second_action_controls(0.1, 0.2, 0.1);
        assert_eq!(class, SecondActionClass::DoubleJump);
    }

    #[test]
    fn second_press_while_jumping_is_accepted() {
        let mut tracker = CarTracker::new_grounded(0);
        tracker.first_jump_press(0).unwrap();
        assert_eq!(
            tracker.second_action_from_controls(1, 0.0, 0.0, 0.0),
            Ok(SecondActionClass::DoubleJump)
        );
        assert_eq!(tracker.second, SecondAction::UsedDoubleJump { tick: 1 });
    }

    #[test]
    fn early_release_deadline_anchors_to_jump_end_not_release_tick() {
        let mut tracker = CarTracker::new_grounded(0);
        tracker.first_jump_press(0).unwrap();
        let jump_end = tracker.jump_release(1).unwrap();
        assert_eq!(jump_end, seconds_to_ticks(JUMP_MIN_TIME, 120.0));

        let mut accepted = tracker.clone();
        let last_legal_tick = jump_end + seconds_to_ticks(DOUBLEJUMP_MAX_DELAY, 120.0) - 1;
        assert_eq!(
            accepted.second_action_from_controls(last_legal_tick, 0.0, 0.0, 0.0),
            Ok(SecondActionClass::DoubleJump)
        );

        let mut rejected = tracker;
        let deadline_tick = jump_end + seconds_to_ticks(DOUBLEJUMP_MAX_DELAY, 120.0);
        assert_eq!(
            rejected.second_action_from_controls(deadline_tick, 0.0, 0.0, 0.0),
            Err(TrackerError::SecondActionExpired)
        );
    }

    #[test]
    fn pure_side_flip_records_no_cancel_possible() {
        let mut tracker = CarTracker::new_grounded(0);
        tracker.first_jump_press(0).unwrap();
        tracker.jump_release(3).unwrap();
        tracker
            .second_action_from_controls(4, 0.0, 1.0, 0.0)
            .unwrap();
        let SecondAction::UsedDodge(phase) = tracker.second else {
            panic!("expected dodge phase");
        };
        assert_eq!(phase.rel_torque, [-1.0, 0.0]);
        assert!(!phase.cancel_possible);
    }

    #[test]
    fn flip_phase_windows_come_from_constants() {
        let phase = FlipPhase::new(10, [0.0, 1.0], 120.0);
        assert_eq!(phase.torque_end_tick(), 88);
        assert_eq!(phase.pitchlock_end_tick(), 124);
        assert_eq!(phase.z_damp_tick_range(), (28, 88));
    }

    #[test]
    fn branching_tracker_caps_ambiguous_candidates_to_beam_width() {
        let tracker = CarTracker::new_grounded(0);
        let mut branches = BranchingTracker::new(tracker);
        branches.expand([4.0, 3.0, 2.0, 1.0, 0.0], |tracker, _idx| {
            Some(tracker.clone())
        });
        assert_eq!(branches.len(), BranchingTracker::DEFAULT_BEAM_WIDTH);
        assert_eq!(branches.branches()[0].score, 0.0);
    }

    #[test]
    fn branching_tracker_collapses_unresolved_ties_within_two_intervals() {
        let tracker = CarTracker::new_grounded(0);
        let mut branches = BranchingTracker::new(tracker);
        branches.expand([0.0, 0.1, 0.2, 0.3], |tracker, _idx| Some(tracker.clone()));
        assert_eq!(branches.len(), 4);
        branches.advance_unresolved();
        assert_eq!(branches.len(), 4);
        branches.advance_unresolved();
        assert_eq!(branches.len(), 1);
        assert_eq!(branches.branches()[0].open_intervals, 0);
    }

    #[test]
    fn dodge_torque_vector_decodes_axis_scaled_reltorque() {
        let rel = dodge_torque_vector_to_rel_torque([2.6, 0.0, 0.0]);
        assert!((rel[0] - 1.0).abs() < 1e-6);
        assert!(rel[1].abs() < 1e-6);

        let rel = dodge_torque_vector_to_rel_torque([0.0, 2.24, 0.0]);
        assert!(rel[0].abs() < 1e-6);
        assert!((rel[1] - 1.0).abs() < 1e-6);
    }

    #[test]
    #[ignore = "set RLINPUT_COMPONENT_JSON to scripts/export_component_stream.py output for Replay_files/0925.replay"]
    fn exported_0925_component_counts_match_vector_edges() {
        #[derive(Deserialize)]
        struct Export {
            players: Vec<ExportPlayer>,
        }
        #[derive(Deserialize)]
        struct ExportPlayer {
            component: ComponentStream,
        }

        let path = std::env::var("RLINPUT_COMPONENT_JSON")
            .expect("RLINPUT_COMPONENT_JSON should point to exported fixture json");
        let file = std::fs::File::open(path).expect("exported fixture should open");
        let export: Export = serde_json::from_reader(file).expect("exported fixture should parse");

        let mut dodge_vectors = 0usize;
        let mut double_jump_vectors = 0usize;
        let mut dodge_edges = 0usize;
        let mut double_jump_edges = 0usize;
        for player in export.players {
            dodge_vectors += player
                .component
                .events
                .iter()
                .filter(|event| event.component == ComponentKind::DodgeTorque)
                .count();
            double_jump_vectors += player
                .component
                .events
                .iter()
                .filter(|event| event.component == ComponentKind::DoubleJumpImpulse)
                .count();
            let edges = reconstruct_seeded_edges(&player.component);
            dodge_edges += edges
                .iter()
                .filter(|edge| edge.component == ComponentKind::DodgeTorque)
                .count();
            double_jump_edges += edges
                .iter()
                .filter(|edge| edge.component == ComponentKind::DoubleJumpImpulse)
                .count();
        }
        assert_eq!(dodge_vectors, 378);
        assert_eq!(double_jump_vectors, 119);
        assert_eq!(dodge_edges, dodge_vectors);
        assert_eq!(double_jump_edges, double_jump_vectors);
    }
}
