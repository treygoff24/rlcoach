use crate::{
    consts,
    convert::RotationMatrix,
    timeline::{AmbiguityFlags, Channel, Source},
    tracker::FlipPhase,
};

const DENOM_EPS: f32 = 2.0;
const ROOT_EPS: f32 = 1e-4;
const RESIDUAL_EPS: f32 = 1e-4;
const GRID_STEPS: usize = 8;
const BISECT_ITERS: usize = 20;
const SAT_EPS: f32 = 1e-4;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum AerialAxis {
    Pitch,
    Yaw,
    Roll,
}

#[derive(Clone, Debug, PartialEq)]
pub struct AerialAxisSolve {
    pub value: f32,
    pub roots: Vec<f32>,
    pub source: Source,
    pub confidence: f32,
    pub flags: AmbiguityFlags,
    pub degenerate: bool,
    pub saturated: bool,
}

impl AerialAxisSolve {
    pub fn channel(&self) -> Channel<f32> {
        Channel {
            value: self.value,
            source: self.source,
            confidence: self.confidence,
            flags: self.flags,
        }
    }
}

#[derive(Clone, Copy, Debug, PartialEq)]
pub struct AxisObservation {
    pub rot: RotationMatrix,
    pub ang_vel: [f32; 3],
}

pub fn solve_axis_from_observations(
    axis: AerialAxis,
    start: AxisObservation,
    end: AxisObservation,
    ticks: u32,
    tick_range: (u64, u64),
    flip: Option<&FlipPhase>,
) -> AerialAxisSolve {
    if let Some(flags) = unobservable_flags(axis, tick_range, flip) {
        return inferred(flags);
    }
    solve_axis_interval(
        axis,
        local_axis_ang_vel(start.rot, start.ang_vel, axis),
        local_axis_ang_vel(end.rot, end.ang_vel, axis),
        ticks,
    )
}

pub fn solve_axis_interval(
    axis: AerialAxis,
    start: f32,
    target: f32,
    ticks: u32,
) -> AerialAxisSolve {
    if ticks == 0 {
        return AerialAxisSolve {
            value: 0.0,
            roots: vec![0.0],
            source: Source::Inferred,
            confidence: 0.0,
            flags: AmbiguityFlags::LOW_MARGIN,
            degenerate: true,
            saturated: false,
        };
    }

    if start.abs() >= consts::CAR_MAX_ANG_SPEED - SAT_EPS
        || target.abs() >= consts::CAR_MAX_ANG_SPEED - SAT_EPS
    {
        return AerialAxisSolve {
            value: 0.0,
            roots: Vec::new(),
            source: Source::Inferred,
            confidence: 0.0,
            flags: AmbiguityFlags::ANGVEL_SATURATED,
            degenerate: false,
            saturated: true,
        };
    }

    let mut roots = Vec::new();
    let mut flags = AmbiguityFlags::empty();
    let mut degenerate = false;

    for branch in [Branch::Negative, Branch::Positive] {
        if branch_degenerate(axis, branch, start) {
            degenerate = true;
            flags |= AmbiguityFlags::LOW_MARGIN;
            continue;
        }
        if let Some(root) = closed_form_root(axis, branch, start, target, ticks) {
            push_root(&mut roots, root);
        }
        for root in bracketed_roots(axis, branch, start, target, ticks) {
            push_root(&mut roots, root);
        }
    }

    roots.sort_by(f32::total_cmp);
    let saturated = roots
        .iter()
        .any(|&root| rollout_axis(axis, root, start, ticks).saturated);
    if saturated {
        return AerialAxisSolve {
            value: 0.0,
            roots,
            source: Source::Inferred,
            confidence: 0.0,
            flags: flags | AmbiguityFlags::ANGVEL_SATURATED,
            degenerate,
            saturated: true,
        };
    }

    if let Some(value) = choose_smallest_abs(&roots) {
        if roots.len() > 1 {
            flags |= AmbiguityFlags::LOW_MARGIN;
        }
        AerialAxisSolve {
            value,
            roots,
            source: Source::Solved,
            confidence: if flags.is_empty() { 1.0 } else { 0.6 },
            flags,
            degenerate,
            saturated: false,
        }
    } else {
        let value = nearest_boundary(axis, start, target, ticks);
        AerialAxisSolve {
            value,
            roots,
            source: Source::Inferred,
            confidence: 0.25,
            flags: flags | AmbiguityFlags::LOW_MARGIN,
            degenerate,
            saturated: false,
        }
    }
}

pub fn local_axis_ang_vel(rot: RotationMatrix, ang_vel: [f32; 3], axis: AerialAxis) -> f32 {
    dot(axis_dir(rot, axis), ang_vel)
}

pub fn axis_dir(rot: RotationMatrix, axis: AerialAxis) -> [f32; 3] {
    match axis {
        AerialAxis::Pitch => [-rot[0][1], -rot[1][1], -rot[2][1]],
        AerialAxis::Yaw => [rot[0][2], rot[1][2], rot[2][2]],
        AerialAxis::Roll => [-rot[0][0], -rot[1][0], -rot[2][0]],
    }
}

pub fn unobservable_flags(
    axis: AerialAxis,
    tick_range: (u64, u64),
    flip: Option<&FlipPhase>,
) -> Option<AmbiguityFlags> {
    let flip = flip?;
    let torque_range = (flip.start_tick, flip.torque_end_tick());
    let pitchlock_range = (flip.torque_end_tick(), flip.pitchlock_end_tick());

    if intersects(tick_range, torque_range) {
        if flip.is_stall() {
            if axis == AerialAxis::Pitch {
                return Some(AmbiguityFlags::PITCHLOCK_ACTIVE);
            }
        } else if !flip.cancel_possible
            || axis == AerialAxis::Pitch
            || !cancel_active_for(flip, tick_range)
        {
            return Some(AmbiguityFlags::FLIP_TORQUE_ACTIVE);
        }
    }

    if axis == AerialAxis::Pitch && intersects(tick_range, pitchlock_range) {
        return Some(AmbiguityFlags::PITCHLOCK_ACTIVE);
    }

    None
}

#[derive(Clone, Copy)]
enum Branch {
    Negative,
    Positive,
}

impl Branch {
    fn bounds(self) -> (f32, f32) {
        match self {
            Branch::Negative => (-1.0, 0.0),
            Branch::Positive => (0.0, 1.0),
        }
    }

    fn contains(self, value: f32) -> bool {
        let (lo, hi) = self.bounds();
        value >= lo - ROOT_EPS && value <= hi + ROOT_EPS
    }
}

struct AxisRollout {
    end: f32,
    saturated: bool,
}

fn inferred(flags: AmbiguityFlags) -> AerialAxisSolve {
    AerialAxisSolve {
        value: 0.0,
        roots: Vec::new(),
        source: Source::Inferred,
        confidence: 0.0,
        flags,
        degenerate: false,
        saturated: false,
    }
}

fn branch_degenerate(axis: AerialAxis, branch: Branch, omega: f32) -> bool {
    if axis == AerialAxis::Roll {
        return false;
    }
    let t = consts::CAR_AIR_CONTROL_T[axis_index(axis)];
    let d = consts::CAR_AIR_CONTROL_D[axis_index(axis)];
    let denom = match branch {
        Branch::Negative => t - d * omega,
        Branch::Positive => t + d * omega,
    };
    denom.abs() < DENOM_EPS
}

fn closed_form_root(
    axis: AerialAxis,
    branch: Branch,
    start: f32,
    target: f32,
    ticks: u32,
) -> Option<f32> {
    if ticks != 1 {
        return None;
    }
    let alpha = (target - start) * 120.0;
    let t = consts::CAR_AIR_CONTROL_T[axis_index(axis)];
    let d = consts::CAR_AIR_CONTROL_D[axis_index(axis)];
    let denom = match (axis, branch) {
        (AerialAxis::Roll, _) => t,
        (_, Branch::Negative) => t - d * start,
        (_, Branch::Positive) => t + d * start,
    };
    if denom.abs() < f32::EPSILON {
        return None;
    }
    let root = ((alpha + d * start) / denom).clamp(-1.0, 1.0);
    let residual = residual(axis, root, start, target, ticks).abs();
    (branch.contains(root) && residual <= RESIDUAL_EPS).then_some(root)
}

fn bracketed_roots(
    axis: AerialAxis,
    branch: Branch,
    start: f32,
    target: f32,
    ticks: u32,
) -> Vec<f32> {
    let (lo, hi) = branch.bounds();
    let mut roots = Vec::new();
    let mut prev_u = lo;
    let mut prev_r = residual(axis, prev_u, start, target, ticks);

    if prev_r.abs() <= RESIDUAL_EPS {
        push_root(&mut roots, prev_u);
    }

    for i in 1..=GRID_STEPS {
        let u = lo + (hi - lo) * i as f32 / GRID_STEPS as f32;
        let r = residual(axis, u, start, target, ticks);
        if r.abs() <= RESIDUAL_EPS {
            push_root(&mut roots, u);
        } else if prev_r.signum() != r.signum() {
            push_root(
                &mut roots,
                bisect_root(axis, start, target, ticks, prev_u, u),
            );
        }
        prev_u = u;
        prev_r = r;
    }

    roots
}

fn bisect_root(
    axis: AerialAxis,
    start: f32,
    target: f32,
    ticks: u32,
    mut lo: f32,
    mut hi: f32,
) -> f32 {
    let mut lo_r = residual(axis, lo, start, target, ticks);
    for _ in 0..BISECT_ITERS {
        let mid = (lo + hi) * 0.5;
        let mid_r = residual(axis, mid, start, target, ticks);
        if mid_r.abs() <= RESIDUAL_EPS {
            return mid;
        }
        if lo_r.signum() == mid_r.signum() {
            lo = mid;
            lo_r = mid_r;
        } else {
            hi = mid;
        }
    }
    (lo + hi) * 0.5
}

fn nearest_boundary(axis: AerialAxis, start: f32, target: f32, ticks: u32) -> f32 {
    [-1.0, 0.0, 1.0]
        .into_iter()
        .map(|u| (u, residual(axis, u, start, target, ticks).abs()))
        .min_by(|a, b| a.1.total_cmp(&b.1))
        .map_or(0.0, |(u, _)| u)
}

fn choose_smallest_abs(roots: &[f32]) -> Option<f32> {
    roots
        .iter()
        .copied()
        .min_by(|a, b| a.abs().total_cmp(&b.abs()).then_with(|| a.total_cmp(b)))
}

fn push_root(roots: &mut Vec<f32>, root: f32) {
    let root = root.clamp(-1.0, 1.0);
    if !roots.iter().any(|seen| (*seen - root).abs() < ROOT_EPS) {
        roots.push(root);
    }
}

fn residual(axis: AerialAxis, u: f32, start: f32, target: f32, ticks: u32) -> f32 {
    rollout_axis(axis, u, start, ticks).end - target
}

fn rollout_axis(axis: AerialAxis, u: f32, start: f32, ticks: u32) -> AxisRollout {
    let mut omega = start;
    let mut saturated = false;
    for _ in 0..ticks {
        let next = omega + axis_accel(axis, u, omega) / 120.0;
        if next.abs() > consts::CAR_MAX_ANG_SPEED {
            saturated = true;
            omega = next.clamp(-consts::CAR_MAX_ANG_SPEED, consts::CAR_MAX_ANG_SPEED);
        } else {
            omega = next;
        }
    }
    AxisRollout {
        end: omega,
        saturated,
    }
}

fn axis_accel(axis: AerialAxis, u: f32, omega: f32) -> f32 {
    let t = consts::CAR_AIR_CONTROL_T[axis_index(axis)];
    let d = consts::CAR_AIR_CONTROL_D[axis_index(axis)];
    if axis == AerialAxis::Roll {
        return u * t - d * omega;
    }
    if u >= 0.0 {
        u * (t + d * omega) - d * omega
    } else {
        u * (t - d * omega) - d * omega
    }
}

fn axis_index(axis: AerialAxis) -> usize {
    match axis {
        AerialAxis::Pitch => 0,
        AerialAxis::Yaw => 1,
        AerialAxis::Roll => 2,
    }
}

fn cancel_active_for(flip: &FlipPhase, tick_range: (u64, u64)) -> bool {
    flip.cancel
        .intervals
        .iter()
        .any(|interval| intersects(tick_range, interval.tick_range))
}

fn intersects(a: (u64, u64), b: (u64, u64)) -> bool {
    a.0 < b.1 && b.0 < a.1
}

fn dot(a: [f32; 3], b: [f32; 3]) -> f32 {
    a[0] * b[0] + a[1] * b[1] + a[2] * b[2]
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::{
        convert::identity_rot_mat,
        engine::{portable::PortableEngine, AirEngine, CarPhysState, Controls, TickPlan},
        tracker::{CancelInterval, CancelProfile, FlipPhase},
    };

    fn base_state(axis: AerialAxis, omega: f32) -> CarPhysState {
        let rot = identity_rot_mat();
        let dir = axis_dir(rot, axis);
        CarPhysState {
            pos: [0.0; 3],
            vel: [0.0; 3],
            rot,
            ang_vel: [dir[0] * omega, dir[1] * omega, dir[2] * omega],
            boost: consts::BOOST_MAX,
            is_boosting: false,
            boosting_time: 0.0,
            has_jumped: true,
            has_double_jumped: false,
            has_flipped: false,
            is_jumping: false,
            is_flipping: false,
            jump_time: 0.0,
            flip_time: 0.0,
            air_time_since_jump: 0.2,
            flip_rel_torque: [0.0; 3],
        }
    }

    fn controls(axis: AerialAxis, value: f32) -> Controls {
        match axis {
            AerialAxis::Pitch => Controls {
                pitch: value,
                ..Controls::default()
            },
            AerialAxis::Yaw => Controls {
                yaw: value,
                ..Controls::default()
            },
            AerialAxis::Roll => Controls {
                roll: value,
                ..Controls::default()
            },
        }
    }

    #[test]
    fn inverse_aerial_round_trip_dense_grid_against_portable_engine() {
        let axes = [AerialAxis::Pitch, AerialAxis::Yaw, AerialAxis::Roll];
        let omegas = [
            -5.5, -5.25, -4.75, -4.33, -3.0, -1.0, 0.0, 1.0, 3.0, 4.33, 4.75, 5.25, 5.5,
        ];
        let inputs = [-1.0, -0.8, -0.5, -0.2, 0.0, 0.2, 0.5, 0.8, 1.0];
        let ticks = [1, 2, 4, 8];
        let mut errors = Vec::new();
        let mut flagged = 0;
        let mut ambiguous = 0;

        for axis in axes {
            for omega in omegas {
                for input in inputs {
                    for tick_count in ticks {
                        let state = base_state(axis, omega);
                        let out = PortableEngine::new().rollout(
                            &state,
                            &TickPlan::constant(controls(axis, input)),
                            tick_count,
                        );
                        let end = local_axis_ang_vel(out.rot, out.ang_vel, axis);
                        let solved = solve_axis_interval(axis, omega, end, tick_count);
                        if solved.saturated || solved.degenerate || solved.roots.is_empty() {
                            flagged += 1;
                            continue;
                        }
                        if solved.flags.contains(AmbiguityFlags::LOW_MARGIN) {
                            ambiguous += 1;
                            continue;
                        }
                        errors.push((solved.value - input).abs());
                    }
                }
            }
        }

        errors.sort_by(f32::total_cmp);
        let p99_index = ((errors.len() as f32 - 1.0) * 0.99).round() as usize;
        let p99 = errors[p99_index];
        println!(
            "inverse aerial round-trip cases={} flagged={} ambiguous={} p99={p99:.6}",
            errors.len(),
            flagged,
            ambiguous
        );
        assert!(p99 < 0.02, "p99 error {p99}");
    }

    #[test]
    fn branch_bracketing_recovers_multiroot_case_and_selects_smallest_abs() {
        let target = rollout_axis(AerialAxis::Pitch, -0.09405, -5.4, 2).end;
        let solved = solve_axis_interval(AerialAxis::Pitch, -5.4, target, 2);

        assert!(
            solved.roots.len() >= 2,
            "expected multiple roots, got {:?}",
            solved.roots
        );
        assert!(solved.flags.contains(AmbiguityFlags::LOW_MARGIN));
        assert!((solved.value + 0.09405).abs() < 0.01, "{solved:?}");
        assert!(solved
            .roots
            .iter()
            .any(|root| (*root + 0.09405).abs() < 0.01));
        assert!(solved.roots.iter().any(|root| (*root - 0.895).abs() < 0.03));
    }

    #[test]
    fn saturated_and_degenerate_intervals_are_flagged() {
        let saturated = solve_axis_interval(AerialAxis::Pitch, 5.5, 5.4, 1);
        assert!(saturated.saturated);
        assert!(saturated.flags.contains(AmbiguityFlags::ANGVEL_SATURATED));

        let degenerate = solve_axis_interval(AerialAxis::Pitch, -(130.0 / 30.0), -4.2, 1);
        assert!(degenerate.degenerate);
        assert!(degenerate.flags.contains(AmbiguityFlags::LOW_MARGIN));
    }

    #[test]
    fn flip_observability_windows_emit_inferred_zero_confidence() {
        let pure_side = FlipPhase::new(100, [1.0, 0.0], 120.0);
        let solved = solve_axis_from_observations(
            AerialAxis::Yaw,
            AxisObservation {
                rot: identity_rot_mat(),
                ang_vel: [0.0; 3],
            },
            AxisObservation {
                rot: identity_rot_mat(),
                ang_vel: [0.0; 3],
            },
            4,
            (100, 104),
            Some(&pure_side),
        );
        assert_eq!(solved.source, Source::Inferred);
        assert_eq!(solved.confidence, 0.0);
        assert!(solved.flags.contains(AmbiguityFlags::FLIP_TORQUE_ACTIVE));

        let stall = FlipPhase::new(200, [0.0, 0.0], 120.0);
        assert_eq!(
            unobservable_flags(AerialAxis::Pitch, (250, 254), Some(&stall)),
            Some(AmbiguityFlags::PITCHLOCK_ACTIVE)
        );
        assert_eq!(
            unobservable_flags(AerialAxis::Yaw, (250, 254), Some(&stall)),
            None
        );

        let mut cancelling = FlipPhase::new(300, [0.0, 1.0], 120.0);
        cancelling.cancel = CancelProfile {
            intervals: vec![CancelInterval {
                tick_range: (300, 304),
                pitch: 0.5,
            }],
        };
        assert_eq!(
            unobservable_flags(AerialAxis::Yaw, (300, 304), Some(&cancelling)),
            None
        );
        assert_eq!(
            unobservable_flags(AerialAxis::Pitch, (378, 382), Some(&cancelling)),
            Some(AmbiguityFlags::PITCHLOCK_ACTIVE)
        );
    }
}
