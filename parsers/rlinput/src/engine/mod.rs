use crate::convert::RotationMatrix;
use serde::{Deserialize, Serialize};

pub mod portable;

pub const AIR_TICK_RATE_HZ: f32 = 120.0;
pub const AIR_DT: f32 = 1.0 / AIR_TICK_RATE_HZ;

pub trait AirEngine {
    /// Advance `state` by `ticks` at 120Hz applying per-tick controls and pending events.
    fn rollout(&mut self, state: &CarPhysState, plan: &TickPlan, ticks: u32) -> CarPhysState;
}

#[derive(Clone, Copy, Debug, PartialEq, Serialize, Deserialize)]
pub struct CarPhysState {
    pub pos: [f32; 3],
    pub vel: [f32; 3],
    pub rot: RotationMatrix,
    pub ang_vel: [f32; 3],
    pub boost: f32,
    pub has_jumped: bool,
    pub has_double_jumped: bool,
    pub has_flipped: bool,
    pub is_jumping: bool,
    pub is_flipping: bool,
    pub jump_time: f32,
    pub flip_time: f32,
    pub air_time_since_jump: f32,
    pub flip_rel_torque: [f32; 3],
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct TickPlan {
    pub controls: Vec<Controls>,
    pub events: Vec<TickEvent>,
}

impl TickPlan {
    pub fn constant(controls: Controls) -> Self {
        Self {
            controls: vec![controls],
            events: Vec::new(),
        }
    }

    pub fn controls_at(&self, tick: u32) -> Controls {
        self.controls
            .get(tick as usize)
            .copied()
            .or_else(|| self.controls.last().copied())
            .unwrap_or_default()
            .clamped()
    }
}

#[derive(Clone, Copy, Debug, Default, PartialEq, Serialize, Deserialize)]
pub struct Controls {
    pub throttle: f32,
    pub steer: f32,
    pub pitch: f32,
    pub yaw: f32,
    pub roll: f32,
    pub jump: bool,
    pub boost: bool,
    pub handbrake: bool,
}

impl Controls {
    pub fn clamped(self) -> Self {
        Self {
            throttle: self.throttle.clamp(-1.0, 1.0),
            steer: self.steer.clamp(-1.0, 1.0),
            pitch: self.pitch.clamp(-1.0, 1.0),
            yaw: self.yaw.clamp(-1.0, 1.0),
            roll: self.roll.clamp(-1.0, 1.0),
            jump: self.jump,
            boost: self.boost,
            handbrake: self.handbrake,
        }
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Serialize, Deserialize)]
pub struct TickEvent {
    pub tick_offset: u32,
    pub kind: TickEventKind,
}

#[derive(Clone, Copy, Debug, PartialEq, Serialize, Deserialize)]
pub enum TickEventKind {
    JumpPress,
    JumpRelease,
    DoubleJump,
    Dodge { dir: [f32; 2] },
}
