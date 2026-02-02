# Coaching Data Enhancements Implementation Plan

**Created:** 2025-11-26
**Purpose:** Add missing data and metrics required for comprehensive Rocket League coaching
**Priority:** P0 → P1 → P2 → P3

---

## IMPLEMENTATION STATUS (Updated 2026-02-02)

### COMPLETED

**Phase 1.1: True Car Rotation** - DONE
- Added `car_rot` HashMap in Rust parser for quaternion (x,y,z,w) tracking
- Extracts rotation from `rb.rotation` in RigidBody handler
- Added `quat_to_euler()` helper function in `lib.rs`
- Frame output now includes `pitch`, `yaw`, `roll` + raw quaternion
- Added `Quaternion` and `Rotation` dataclasses in `src/rlcoach/parser/types.py`
- Added `_parse_rotation()` helper in `src/rlcoach/normalize.py` to handle both new (pitch/yaw/roll+quat) and legacy (x/y/z) formats
- Updated imports in normalize.py
- Note: boxcars 0.10.7 doesn't expose Jump/Dodge/Throttle/Steer/Handbrake attributes directly - these must be inferred

**Phase 1.2: Mechanics Detection (via physics inference)** - DONE
- Created `src/rlcoach/analysis/mechanics.py`
- Detects: JUMP, DOUBLE_JUMP, FLIP, WAVEDASH, AERIAL from physics state changes
- Uses z-velocity spikes, rotation rates, and height tracking
- `analyze_mechanics()` returns per-player and aggregate stats

**Phase 2.1: Touch Context Classification** - DONE
- Added `TouchContext` enum in `src/rlcoach/events.py` (GROUND, AERIAL, WALL, CEILING, HALF_VOLLEY, UNKNOWN)
- Added `_classify_touch_context()` helper function
- Updated `TouchEvent` dataclass with: `touch_context`, `car_height`, `is_first_touch`
- Updated `detect_touches()` to populate new fields
- Updated `src/rlcoach/report.py` to serialize new touch fields
- Updated golden test files with new touch fields
- Fixed `_normalize()` in test_goldens.py to handle Enum serialization

**Phase 2.2: Recovery Tracking** - DONE
- Created `src/rlcoach/analysis/recovery.py`
- `RecoveryQuality` enum: EXCELLENT, GOOD, AVERAGE, POOR, FAILED
- `RecoveryEvent` dataclass with: timestamp, landing_position, quality, time_airborne, time_to_control, peak_height, momentum_retained, was_wavedash
- `analyze_recoveries()` returns per-player stats and events list

**Phase 3.1: Expected Goals (xG) Model** - DONE
- Created `src/rlcoach/analysis/xg.py`
- `ShotType` enum: GROUND, AERIAL, WALL, CEILING, REDIRECT, POWER_SHOT, LOB
- `calculate_xg()` considers: distance, angle, ball speed, defender coverage, shot type
- `analyze_shots_xg()` returns per-player and team xG totals

**Phase 4.1: Defensive Positioning Context** - DONE
- Created `src/rlcoach/analysis/defense.py`
- `DefensiveRole` enum: LAST_DEFENDER, SECOND_DEFENDER, SHADOW, PRESSURING, RECOVERING, OUT_OF_POSITION
- Tracks: last defender situations, shadow defense angles, danger zone time
- `analyze_defense()` returns per-team and per-player defensive stats

**Phase 4.2: Ball Prediction Awareness** - DONE
- Created `src/rlcoach/analysis/ball_prediction.py`
- `ReadQuality` enum: EXCELLENT, GOOD, AVERAGE, POOR, WHIFF
- Simplified ball physics prediction (gravity, bounces)
- `analyze_ball_prediction()` returns per-player read quality stats

### TEST STATUS
- Tests exist in `tests/test_analysis_new_modules.py` and updated goldens.
- 2026-02-01: `source .venv/bin/activate && PYTHONPATH=src pytest -q` → **415 passed in 13.75s**

### NOT YET DONE / REMAINING WORK

1. **Phase 3.2: Input States (Throttle, Boost, Steer)** - SKIPPED
   - Boxcars 0.10.7 doesn't expose these attributes directly
   - Would require updating boxcars or different approach

### COMPLETED SINCE ORIGINAL PLAN (2026-02-02)

- Integration wired via `src/rlcoach/analysis/__init__.py` (aggregator) and `src/rlcoach/report.py`.
- Schema updated in `schemas/replay_report.schema.json` to include mechanics, recovery, xg, defense, ball prediction.
- Tests added in `tests/test_analysis_new_modules.py`, plus golden updates for header-only and synthetic fixtures.

### FILES MODIFIED/CREATED

**Modified:**
- `parsers/rlreplay_rust/src/lib.rs` - Rotation extraction
- `src/rlcoach/parser/types.py` - Quaternion, Rotation types
- `src/rlcoach/normalize.py` - `_parse_rotation()` helper
- `src/rlcoach/events.py` - TouchContext enum and touch classification
- `src/rlcoach/report.py` - Touch serialization
- `src/rlcoach/analysis/__init__.py` - Aggregator wiring + caching for new analyzers
- `schemas/replay_report.schema.json` - New analysis fields
- `tests/test_goldens.py` - Enum handling in `_normalize()`
- `tests/goldens/synthetic_small.json` - New touch fields
- `tests/goldens/synthetic_small.md` - New touch fields
- `tests/goldens/header_only.json` - New analysis fields
- `tests/goldens/header_only.md` - New analysis fields

**Created:**
- `src/rlcoach/analysis/mechanics.py` - Jump/flip/aerial detection
- `src/rlcoach/analysis/recovery.py` - Recovery tracking
- `src/rlcoach/analysis/xg.py` - Expected goals model
- `src/rlcoach/analysis/defense.py` - Defensive positioning
- `src/rlcoach/analysis/ball_prediction.py` - Ball read analysis
- `tests/test_analysis_new_modules.py` - Unit coverage for new analyzers

---

**Note:** Detailed design sections below reflect the original 2025-11-26 proposal. Current implementation uses `src/rlcoach/analysis/ball_prediction.py` and `schemas/replay_report.schema.json`; legacy `ball_read`/`report.json` names are superseded.

## Executive Summary

After reviewing the current output (`out/0925.json`), this plan identifies and prioritizes missing data points that would significantly improve coaching effectiveness. The enhancements are organized into implementation phases based on coaching value and technical complexity.

---

## Phase 1: P0 - Foundation (True Car State)

### 1.1 True Car Rotation/Orientation

**Current State:** Car rotation is approximated from velocity direction in `lib.rs:701-714`

**Problem:** This approximation fails when:
- Car is stationary
- Car is moving in a different direction than facing (powersliding, recovering)
- Car is airborne with complex orientation

**What Boxcars Provides:** The `RigidBody` attribute contains a `rotation` field with quaternion data that we're currently ignoring.

**Implementation:**

#### A. Rust Parser Changes (`parsers/rlreplay_rust/src/lib.rs`)

```rust
// Add car rotation tracking alongside existing car_pos, car_vel
let mut car_rot: HashMap<i32, (f32, f32, f32, f32)> = HashMap::new(); // quaternion (x,y,z,w)
```

In the `RigidBody` attribute handler (~line 522), extract rotation:

```rust
Attribute::RigidBody(rb) => {
    // ... existing position/velocity code ...

    // Extract quaternion rotation
    if let Some(rot) = rb.rotation {
        // Boxcars provides rotation as Quaternion { x, y, z, w }
        car_rot.insert(aid, (rot.x, rot.y, rot.z, rot.w));
    }
}
```

Update the frame output (~line 688) to include rotation as quaternion AND euler:

```rust
// Convert quaternion to euler for convenience
fn quat_to_euler(q: (f32, f32, f32, f32)) -> (f64, f64, f64) {
    let (x, y, z, w) = q;
    // Roll (x-axis rotation)
    let sinr_cosp = 2.0 * (w * x + y * z);
    let cosr_cosp = 1.0 - 2.0 * (x * x + y * y);
    let roll = sinr_cosp.atan2(cosr_cosp);

    // Pitch (y-axis rotation)
    let sinp = 2.0 * (w * y - z * x);
    let pitch = if sinp.abs() >= 1.0 {
        std::f32::consts::FRAC_PI_2.copysign(sinp)
    } else {
        sinp.asin()
    };

    // Yaw (z-axis rotation)
    let siny_cosp = 2.0 * (w * z + x * y);
    let cosy_cosp = 1.0 - 2.0 * (y * y + z * z);
    let yaw = siny_cosp.atan2(cosy_cosp);

    (roll as f64, pitch as f64, yaw as f64)
}

// In frame output:
let prot = PyDict::new(py);
if let Some(q) = car_rot.get(&aid) {
    let (roll, pitch, yaw) = quat_to_euler(*q);
    prot.set_item("pitch", pitch)?;
    prot.set_item("yaw", yaw)?;
    prot.set_item("roll", roll)?;
    // Also include raw quaternion for precision work
    let quat = PyDict::new(py);
    quat.set_item("x", q.0)?;
    quat.set_item("y", q.1)?;
    quat.set_item("z", q.2)?;
    quat.set_item("w", q.3)?;
    prot.set_item("quaternion", quat)?;
}
p.set_item("rotation", prot)?;
```

#### B. Python Type Updates (`src/rlcoach/parser/types.py`)

Add rotation fields to `PlayerFrame`:

```python
@dataclass
class PlayerFrame:
    player_id: str
    team: int
    position: Vec3
    velocity: Vec3
    rotation: Rotation  # Add this
    boost_amount: int
    is_supersonic: bool
    is_on_ground: bool
    is_demolished: bool

@dataclass
class Rotation:
    pitch: float  # radians
    yaw: float    # radians
    roll: float   # radians
    quaternion: Optional[Quaternion] = None

@dataclass
class Quaternion:
    x: float
    y: float
    z: float
    w: float
```

#### C. Normalize Layer (`src/rlcoach/normalize.py`)

Update frame normalization to preserve rotation data.

**Testing:**
- Compare facing direction vs velocity direction during powerslides
- Verify aerial rotations are captured accurately
- Test recovery scenarios where car faces opposite to movement

---

### 1.2 Jump/Flip/Dodge Detection

**Current State:** Not tracked at all

**What Boxcars Provides:**
- `Attribute::Jump { is_active }` - Jump button state
- `Attribute::Dodge { is_active }` - Dodge/flip active state
- `Attribute::DoubleJumpActive { is_active }` - Double jump state
- `Attribute::JumpActive { is_active }` - Alternative jump tracking

**Implementation:**

#### A. Rust Parser Changes

```rust
// New tracking structures
let mut car_jump_active: HashMap<i32, bool> = HashMap::new();
let mut car_dodge_active: HashMap<i32, bool> = HashMap::new();
let mut car_double_jump_active: HashMap<i32, bool> = HashMap::new();

// Track state transitions for event detection
struct JumpState {
    jump_active: bool,
    dodge_active: bool,
    double_jump_active: bool,
    jump_start_frame: Option<usize>,
    dodge_start_frame: Option<usize>,
    last_ground_frame: Option<usize>,
}
let mut car_jump_state: HashMap<i32, JumpState> = HashMap::new();
```

In the attribute handler, add cases:

```rust
Attribute::Jump(jump) | Attribute::JumpActive(jump) => {
    let target = component_owner.get(&aid).cloned().unwrap_or(aid);
    let was_active = car_jump_active.get(&target).cloned().unwrap_or(false);
    car_jump_active.insert(target, jump.is_active);

    // Detect jump start
    if jump.is_active && !was_active {
        // Record jump event
    }
}

Attribute::Dodge(dodge) => {
    let target = component_owner.get(&aid).cloned().unwrap_or(aid);
    let was_active = car_dodge_active.get(&target).cloned().unwrap_or(false);
    car_dodge_active.insert(target, dodge.is_active);

    if dodge.is_active && !was_active {
        // Record dodge/flip start - capture velocity direction for flip type
    }
}

Attribute::DoubleJumpActive(dj) => {
    let target = component_owner.get(&aid).cloned().unwrap_or(aid);
    car_double_jump_active.insert(target, dj.is_active);
}
```

#### B. Frame Output

Add to player dict:

```rust
p.set_item("is_jumping", *car_jump_active.get(&aid).unwrap_or(&false))?;
p.set_item("is_dodging", *car_dodge_active.get(&aid).unwrap_or(&false))?;
p.set_item("is_double_jumping", *car_double_jump_active.get(&aid).unwrap_or(&false))?;
```

#### C. New Events Module (`src/rlcoach/events_mechanics.py`)

```python
@dataclass
class JumpEvent:
    t: float
    frame: int
    player_id: str
    jump_type: str  # "SINGLE", "DOUBLE", "DODGE"
    position: Vec3
    velocity: Vec3
    is_grounded_before: bool

@dataclass
class FlipEvent:
    t: float
    frame: int
    player_id: str
    flip_type: str  # "FRONT", "BACK", "LEFT", "RIGHT", "DIAGONAL_FL", "DIAGONAL_FR", etc.
    flip_direction: Vec3  # normalized direction vector
    car_orientation_at_flip: Rotation
    speed_at_flip: float
    height_at_flip: float
    is_flip_cancel: bool  # detected if flip duration < normal

def classify_flip_type(velocity: Vec3, rotation: Rotation) -> str:
    """Classify flip type based on car-relative dodge direction."""
    # Transform velocity to car-local coordinates using rotation
    # Determine flip direction from local velocity components
    pass

def detect_flip_cancel(flip_start_frame: int, flip_end_frame: int, fps: float) -> bool:
    """Detect if flip was cancelled early (half-flip, stall)."""
    duration = (flip_end_frame - flip_start_frame) / fps
    return duration < 0.65  # Normal flip ~0.65s
```

#### D. Analysis Module (`src/rlcoach/analysis/mechanics.py`)

New analyzer for mechanics:

```python
def analyze_mechanics(timeline: NormalizedTimeline, events: list) -> dict:
    """Analyze mechanical skill indicators."""

    jump_events = [e for e in events if isinstance(e, JumpEvent)]
    flip_events = [e for e in events if isinstance(e, FlipEvent)]

    return {
        "total_jumps": len(jump_events),
        "single_jumps": len([j for j in jump_events if j.jump_type == "SINGLE"]),
        "double_jumps": len([j for j in jump_events if j.jump_type == "DOUBLE"]),
        "total_flips": len(flip_events),
        "flip_types": Counter(f.flip_type for f in flip_events),
        "flip_cancels": len([f for f in flip_events if f.is_flip_cancel]),
        "avg_flip_height": mean(f.height_at_flip for f in flip_events) if flip_events else 0,
        "aerial_flips": len([f for f in flip_events if f.height_at_flip > 300]),  # uu threshold
        "ground_flips": len([f for f in flip_events if f.height_at_flip <= 300]),
    }
```

**Testing:**
- Verify jump detection on kickoffs
- Test flip type classification accuracy
- Verify flip cancel detection for half-flips
- Test aerial flip vs ground flip distinction

---

## Phase 2: P1 - Touch Context & Recovery

### 2.1 Touch Context (Aerial/Ground/Wall)

**Current State:** Touches have location and ball speed, but no context

**Implementation:**

#### A. Enhance Touch Event Detection (`src/rlcoach/events.py`)

```python
@dataclass
class TouchEvent:
    t: float
    frame: int
    player_id: str
    location: Vec3
    ball_speed_kph: float
    outcome: str
    # NEW fields:
    touch_type: str  # "GROUND", "AERIAL", "WALL", "CEILING"
    car_height: float  # z coordinate of car at touch
    car_orientation: Rotation
    car_speed_kph: float
    is_first_touch_aerial: bool  # true if jumped for this touch
    touch_part: str  # "HOOD", "BUMPER", "CORNER", "ROOF", "WHEELS" (estimated)

def classify_touch_type(car_pos: Vec3, car_on_ground: bool) -> str:
    """Classify touch based on car position and state."""
    # Wall touch: car x near ±4096 or y near ±5120
    if abs(car_pos.x) > 3800 or abs(car_pos.y) > 4800:
        return "WALL"
    # Ceiling touch
    if car_pos.z > 1800:
        return "CEILING"
    # Aerial: car significantly off ground
    if car_pos.z > 300 and not car_on_ground:
        return "AERIAL"
    return "GROUND"

def estimate_touch_part(ball_pos: Vec3, car_pos: Vec3, car_rotation: Rotation) -> str:
    """Estimate which part of car contacted ball."""
    # Transform ball position to car-local coordinates
    # Based on relative position, estimate contact point
    pass
```

#### B. Touch Quality Metrics

```python
def compute_touch_quality(touch: TouchEvent, ball_trajectory_before: list, ball_trajectory_after: list) -> dict:
    """Compute quality metrics for a touch."""
    return {
        "power": touch.ball_speed_kph,
        "accuracy": compute_accuracy_to_target(ball_trajectory_after),  # How close to goal/teammate
        "timing": compute_timing_quality(touch),  # Based on challenge proximity
        "technique": classify_technique(touch),  # "POWER_SHOT", "REDIRECT", "DRIBBLE_TOUCH", etc.
    }
```

---

### 2.2 Recovery Tracking

**Current State:** Not tracked

**Implementation:**

#### A. Recovery Event Detection (`src/rlcoach/events_mechanics.py`)

```python
@dataclass
class RecoveryEvent:
    t_start: float  # When recovery started (left ground/got bumped)
    t_end: float    # When recovered (stable on ground)
    frame_start: int
    frame_end: int
    player_id: str
    recovery_type: str  # "LANDING", "BUMP_RECOVERY", "DEMO_RESPAWN", "WALL_RECOVERY"
    duration_s: float
    landing_quality: str  # "CLEAN", "BOUNCED", "AWKWARD"
    technique_used: str  # "WAVEDASH", "FLIP_RESET", "AIR_ROLL", "NONE"
    boost_used: float
    speed_retained_pct: float  # Speed at end vs speed at start

def detect_recovery_start(prev_frame: PlayerFrame, curr_frame: PlayerFrame) -> Optional[str]:
    """Detect if player started a recovery situation."""
    # Left ground (was grounded, now airborne)
    if prev_frame.is_on_ground and not curr_frame.is_on_ground:
        return "LANDING"
    # Got bumped (sudden velocity change without touch)
    if velocity_change_magnitude(prev_frame, curr_frame) > BUMP_THRESHOLD:
        return "BUMP_RECOVERY"
    return None

def detect_recovery_end(frames: list[PlayerFrame], start_idx: int) -> tuple[int, str]:
    """Find when recovery completed and assess quality."""
    for i in range(start_idx, min(start_idx + 300, len(frames))):  # ~10s max
        frame = frames[i]
        if frame.is_on_ground and is_stable(frames, i):
            # Assess landing quality
            quality = assess_landing_quality(frames, start_idx, i)
            return i, quality
    return start_idx + 300, "TIMEOUT"

def detect_wavedash(frames: list[PlayerFrame], landing_frame: int) -> bool:
    """Detect if player performed a wavedash on landing."""
    # Wavedash: dodge into ground immediately after landing
    # Look for dodge activation within 2-3 frames of ground contact
    pass

def detect_flip_reset(frames: list[PlayerFrame], jump_events: list) -> list:
    """Detect flip resets (all 4 wheels touched ball/surface)."""
    # Look for double jump becoming available again mid-air
    pass
```

#### B. Recovery Analysis Module (`src/rlcoach/analysis/recovery.py`)

```python
def analyze_recovery(timeline: NormalizedTimeline, recovery_events: list) -> dict:
    """Analyze recovery performance."""
    return {
        "total_recoveries": len(recovery_events),
        "avg_recovery_time_s": mean(r.duration_s for r in recovery_events),
        "fast_recoveries": len([r for r in recovery_events if r.duration_s < 1.0]),
        "slow_recoveries": len([r for r in recovery_events if r.duration_s > 2.0]),
        "wavedashes": len([r for r in recovery_events if r.technique_used == "WAVEDASH"]),
        "flip_resets": len([r for r in recovery_events if r.technique_used == "FLIP_RESET"]),
        "clean_landings_pct": percentage([r for r in recovery_events if r.landing_quality == "CLEAN"]),
        "avg_speed_retained_pct": mean(r.speed_retained_pct for r in recovery_events),
        "boost_efficiency": analyze_boost_in_recoveries(recovery_events),
    }
```

---

## Phase 3: P2 - Shot Quality & Inputs

### 3.1 Shot Quality / Expected Goals (xG)

**Current State:** Only shot speed captured

**Implementation:**

#### A. xG Model (`src/rlcoach/analysis/xg.py`)

```python
@dataclass
class ShotContext:
    ball_position: Vec3
    ball_velocity: Vec3
    ball_speed_kph: float
    shot_angle_deg: float  # Angle to goal center
    distance_to_goal_m: float
    defender_positions: list[Vec3]
    defender_distances: list[float]
    nearest_defender_distance: float
    goalie_position: Optional[Vec3]
    goalie_in_net: bool
    shooter_boost: int
    is_open_net: bool
    shot_height: float  # Ball z at shot

def compute_shot_angle(ball_pos: Vec3, target_goal_y: float) -> float:
    """Compute angle from ball to goal center."""
    goal_center = Vec3(0, target_goal_y, GOAL_HEIGHT / 2)
    # Calculate angle using dot product
    pass

def compute_xg(context: ShotContext) -> float:
    """Compute expected goal probability (0.0 - 1.0)."""
    # Base xG from distance and angle
    base_xg = distance_angle_xg(context.distance_to_goal_m, context.shot_angle_deg)

    # Modify by defender pressure
    defender_modifier = compute_defender_pressure(context.defender_distances)

    # Modify by shot speed (faster = harder to save)
    speed_modifier = min(1.0 + (context.ball_speed_kph - 80) / 200, 1.5)

    # Open net bonus
    if context.is_open_net:
        return min(0.95, base_xg * 2.0)

    return min(0.95, base_xg * defender_modifier * speed_modifier)

def is_open_net(goalie_pos: Optional[Vec3], goal_y: float) -> bool:
    """Determine if goal is effectively undefended."""
    if goalie_pos is None:
        return True
    # Check if goalie is in net area
    in_net_x = abs(goalie_pos.x) < GOAL_WIDTH / 2 + 200
    in_net_y = (goal_y > 0 and goalie_pos.y > goal_y - 500) or \
               (goal_y < 0 and goalie_pos.y < goal_y + 500)
    return not (in_net_x and in_net_y)
```

#### B. Enhanced Shot Event

```python
@dataclass
class ShotEvent:
    t: float
    frame: int
    player_id: str
    ball_speed_kph: float
    # NEW fields:
    xg: float  # Expected goal probability
    shot_angle_deg: float
    distance_to_goal_m: float
    is_open_net: bool
    defender_count_in_path: int
    shot_type: str  # "POWER", "PLACEMENT", "REDIRECT", "AERIAL", "GROUND"
```

#### C. Shot Analysis Enhancement

```python
def analyze_shots(shots: list[ShotEvent], goals: list[GoalEvent]) -> dict:
    """Enhanced shot analysis with xG."""
    return {
        "total_shots": len(shots),
        "total_xg": sum(s.xg for s in shots),
        "goals": len(goals),
        "goals_minus_xg": len(goals) - sum(s.xg for s in shots),  # Finishing above/below expected
        "avg_xg_per_shot": mean(s.xg for s in shots),
        "high_quality_shots": len([s for s in shots if s.xg > 0.3]),
        "low_quality_shots": len([s for s in shots if s.xg < 0.1]),
        "open_net_conversion": open_net_stats(shots, goals),
        "shot_type_breakdown": Counter(s.shot_type for s in shots),
    }
```

---

### 3.2 Input States (Throttle, Boost, Steer)

**Current State:** Not tracked

**What Boxcars Provides:**
- `Attribute::Throttle(throttle)` - Throttle input (-1.0 to 1.0)
- `Attribute::Steer(steer)` - Steering input (-1.0 to 1.0)
- `Attribute::Handbrake { is_active }` - Powerslide state

**Implementation:**

#### A. Rust Parser Changes

```rust
let mut car_throttle: HashMap<i32, f32> = HashMap::new();
let mut car_steer: HashMap<i32, f32> = HashMap::new();
let mut car_handbrake: HashMap<i32, bool> = HashMap::new();

// In attribute handler:
Attribute::Throttle(throttle) => {
    let target = component_owner.get(&aid).cloned().unwrap_or(aid);
    car_throttle.insert(target, throttle.value);
}

Attribute::Steer(steer) => {
    let target = component_owner.get(&aid).cloned().unwrap_or(aid);
    car_steer.insert(target, steer.value);
}

Attribute::Handbrake(hb) => {
    let target = component_owner.get(&aid).cloned().unwrap_or(aid);
    car_handbrake.insert(target, hb.is_active);
}
```

#### B. Frame Output

```rust
p.set_item("throttle", *car_throttle.get(&aid).unwrap_or(&0.0))?;
p.set_item("steer", *car_steer.get(&aid).unwrap_or(&0.0))?;
p.set_item("is_powersliding", *car_handbrake.get(&aid).unwrap_or(&false))?;
```

#### C. Input Analysis (`src/rlcoach/analysis/inputs.py`)

```python
def analyze_inputs(timeline: NormalizedTimeline) -> dict:
    """Analyze input patterns for each player."""
    results = {}

    for player_id in timeline.player_ids:
        frames = timeline.player_frames(player_id)

        # Boost usage pattern
        boost_frames = [f for f in frames if f.boost_amount < f_prev.boost_amount]
        boost_tap_count = count_boost_taps(frames)  # Short bursts
        boost_hold_count = count_boost_holds(frames)  # Sustained usage

        # Throttle analysis
        throttle_values = [f.throttle for f in frames]
        full_throttle_pct = len([t for t in throttle_values if t > 0.95]) / len(throttle_values)
        reverse_pct = len([t for t in throttle_values if t < -0.5]) / len(throttle_values)

        # Steering smoothness (lower = smoother)
        steer_values = [f.steer for f in frames]
        steer_jitter = compute_jitter(steer_values)

        results[player_id] = {
            "boost_taps": boost_tap_count,
            "boost_holds": boost_hold_count,
            "boost_tap_ratio": boost_tap_count / (boost_tap_count + boost_hold_count) if boost_hold_count else 1.0,
            "full_throttle_pct": full_throttle_pct,
            "reverse_time_pct": reverse_pct,
            "steering_smoothness": 1.0 - min(1.0, steer_jitter),
            "powerslide_count": count_state_transitions(frames, 'is_powersliding', False, True),
            "avg_powerslide_duration_s": compute_avg_state_duration(frames, 'is_powersliding'),
        }

    return results
```

---

## Phase 4: P3 - Defensive Context & Ball Prediction

### 4.1 Defensive Positioning Context

**Current State:** Basic positioning stats exist, but no situational awareness

**Implementation:**

#### A. Game State Tracking (`src/rlcoach/game_state.py`)

```python
@dataclass
class GameState:
    t: float
    frame: int
    score_blue: int
    score_orange: int
    score_differential: int  # From perspective of ball possessor's team
    time_remaining_s: float
    is_overtime: bool
    is_kickoff: bool
    possession_team: Optional[str]  # "BLUE", "ORANGE", None

def build_game_state_timeline(timeline: NormalizedTimeline, events: list) -> list[GameState]:
    """Build frame-by-frame game state."""
    pass
```

#### B. Defensive Situation Detection (`src/rlcoach/analysis/defense.py`)

```python
@dataclass
class DefensiveSituation:
    t: float
    frame: int
    player_id: str
    situation_type: str  # "LAST_BACK", "SHADOW", "CHALLENGE", "ROTATING_BACK", "IN_NET"
    threat_level: float  # 0.0 - 1.0
    ball_distance: float
    is_correct_position: bool  # Based on situation type

def detect_last_back(frame: NormalizedFrame, player_id: str) -> bool:
    """Detect if player is last back for their team."""
    team = frame.player_team(player_id)
    teammates = frame.teammates(player_id)

    own_goal_y = -5120 if team == "BLUE" else 5120
    player_y = frame.player_position(player_id).y

    # Player is last back if closest to own goal
    for teammate in teammates:
        teammate_y = frame.player_position(teammate).y
        if (team == "BLUE" and teammate_y < player_y) or \
           (team == "ORANGE" and teammate_y > player_y):
            return False
    return True

def detect_shadow_defense(frames: list, player_id: str, start_frame: int) -> Optional[ShadowDefense]:
    """Detect shadow defense: staying between ball and goal while retreating."""
    # Look for pattern: player behind ball, moving toward own goal, ball approaching
    pass

def analyze_defensive_positioning(timeline: NormalizedTimeline, events: list) -> dict:
    """Analyze defensive positioning quality."""
    return {
        "last_back_time_s": total_time_as_last_back,
        "last_back_overcommits": count_overcommits_while_last_back,
        "shadow_defense_count": len(shadow_defenses),
        "avg_shadow_duration_s": mean(s.duration for s in shadow_defenses),
        "goal_line_saves": len([s for s in saves if s.location.y near goal]),
        "clearances": len(clearances),
        "clearance_distance_avg": mean(c.distance for c in clearances),
        "defensive_positioning_score": compute_defense_score(),
    }
```

---

### 4.2 Ball Prediction Awareness

**Current State:** Not tracked

**Implementation:**

#### A. Ball Trajectory Prediction (`src/rlcoach/physics/ball_prediction.py`)

```python
def predict_ball_trajectory(ball_pos: Vec3, ball_vel: Vec3, ball_angvel: Vec3,
                            duration_s: float, dt: float = 0.016) -> list[Vec3]:
    """Predict ball trajectory using simplified physics."""
    trajectory = []
    pos = ball_pos
    vel = ball_vel

    for _ in range(int(duration_s / dt)):
        # Apply gravity
        vel = Vec3(vel.x, vel.y, vel.z - 650 * dt)  # Gravity in uu/s^2

        # Update position
        pos = Vec3(pos.x + vel.x * dt, pos.y + vel.y * dt, pos.z + vel.z * dt)

        # Handle bounces (simplified)
        if pos.z < 93:  # Ball radius
            pos = Vec3(pos.x, pos.y, 93)
            vel = Vec3(vel.x * 0.6, vel.y * 0.6, -vel.z * 0.6)  # Bounce with energy loss

        # Handle wall bounces
        # ... similar logic for walls

        trajectory.append(pos)

    return trajectory
```

#### B. Player Ball Read Analysis (`src/rlcoach/analysis/ball_read.py`)

```python
def analyze_ball_read_quality(timeline: NormalizedTimeline) -> dict:
    """Analyze how well players read the ball's trajectory."""

    for player_id in timeline.player_ids:
        ball_read_scores = []

        for frame_idx in range(0, len(timeline.frames) - 60, 30):  # Sample every second
            frame = timeline.frames[frame_idx]

            # Predict where ball will be in 2 seconds
            predicted_pos = predict_ball_trajectory(
                frame.ball.position,
                frame.ball.velocity,
                frame.ball.angular_velocity,
                duration_s=2.0
            )[-1]

            # Check if player is moving toward predicted position
            player_pos = frame.player_position(player_id)
            player_vel = frame.player_velocity(player_id)

            # Score based on velocity alignment with optimal path to ball
            direction_to_predicted = normalize(predicted_pos - player_pos)
            player_direction = normalize(player_vel)
            alignment = dot(direction_to_predicted, player_direction)

            ball_read_scores.append(alignment)

        return {
            "avg_ball_read_score": mean(ball_read_scores),
            "good_reads_pct": len([s for s in ball_read_scores if s > 0.7]) / len(ball_read_scores),
            "poor_reads_pct": len([s for s in ball_read_scores if s < 0.3]) / len(ball_read_scores),
        }
```

---

## Schema Updates

Add new fields to `schemas/report.json`:

```json
{
  "per_player": {
    "mechanics": {
      "total_jumps": "integer",
      "double_jumps": "integer",
      "total_flips": "integer",
      "flip_types": "object",
      "flip_cancels": "integer",
      "wavedashes": "integer",
      "flip_resets": "integer"
    },
    "recovery": {
      "total_recoveries": "integer",
      "avg_recovery_time_s": "number",
      "clean_landings_pct": "number",
      "avg_speed_retained_pct": "number"
    },
    "shot_quality": {
      "total_xg": "number",
      "goals_minus_xg": "number",
      "avg_xg_per_shot": "number",
      "shot_type_breakdown": "object"
    },
    "inputs": {
      "boost_tap_ratio": "number",
      "full_throttle_pct": "number",
      "steering_smoothness": "number"
    },
    "defense": {
      "last_back_time_s": "number",
      "last_back_overcommits": "integer",
      "shadow_defense_count": "integer",
      "defensive_positioning_score": "number"
    },
    "ball_read": {
      "avg_ball_read_score": "number",
      "good_reads_pct": "number"
    }
  }
}
```

---

## Testing Strategy

### Unit Tests

For each new module:
- `tests/analysis/test_mechanics.py` - Jump/flip detection
- `tests/analysis/test_recovery.py` - Recovery detection and scoring
- `tests/analysis/test_xg.py` - xG calculation accuracy
- `tests/analysis/test_inputs.py` - Input analysis
- `tests/analysis/test_defense.py` - Defensive situation detection
- `tests/analysis/test_ball_read.py` - Ball prediction and read scoring

### Integration Tests

- `tests/test_full_pipeline_enhanced.py` - End-to-end with new fields
- Golden file updates for `tests/goldens/`

### Parity Tests

- Compare xG calculations against known shot outcomes
- Validate recovery detection against manual review
- Cross-reference flip detection with replay viewers

---

## Implementation Order

1. **Week 1: P0 Foundation**
   - 1.1 True car rotation (Rust + Python)
   - 1.2 Jump/flip/dodge detection (Rust + Python)
   - Unit tests for both

2. **Week 2: P1 Touch & Recovery**
   - 2.1 Touch context classification
   - 2.2 Recovery tracking
   - Integration tests

3. **Week 3: P2 Shot Quality & Inputs**
   - 3.1 xG model
   - 3.2 Input states
   - Parity testing

4. **Week 4: P3 Defense & Ball Read**
   - 4.1 Defensive context
   - 4.2 Ball prediction awareness
   - Full integration testing
   - Schema updates
   - Golden file updates

---

## Dependencies

- boxcars Rust crate (already in use) - provides all necessary attributes
- No new external dependencies required

---

## Notes for Implementation

1. **Start with Rust parser changes** - These are the foundation for everything else
2. **Test rotation extraction first** - Without accurate rotation, flip classification won't work
3. **Use existing frame iteration patterns** - Follow the style in `normalize.py` and `events.py`
4. **Preserve backward compatibility** - New fields should be additive, not breaking
5. **Add quality warnings** - If any new detection fails, add to quality.warnings array

---

## Success Criteria

After implementation, the coaching output should be able to answer:

- "Are you using your flip efficiently? Do you flip cancel when appropriate?"
- "How fast are your recoveries? Do you use advanced techniques like wavedashing?"
- "Are you taking high-quality shots or forcing low-percentage attempts?"
- "Is your boost usage efficient? Are you tapping or holding?"
- "Do you read the ball well? Are you moving to where the ball will be?"
- "When you're last back, do you overcommit?"
- "What's your defensive positioning score?"

These are the questions I need data to answer for effective coaching.
