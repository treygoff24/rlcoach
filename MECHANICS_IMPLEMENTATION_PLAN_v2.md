# Mechanics Detection Implementation Plan v2

Based on: `MECHANICS_DETECTION.md` comprehensive spec with player feedback and technical review.

---

## Overview

This plan implements the refined mechanics detection system with:
- Foundation fixes for accurate physics detection at 30 Hz sampling
- Core mechanic improvements based on player feedback
- Mechanic refinements (dribble, flip reset split)
- Two new advanced mechanics (Skim, Psycho)

**Critical Context:**
- Replays sample at **30 Hz**, not 120 Hz physics rate
- Thresholds must account for 1-2 frames of gravity decay
- No pitch/yaw/roll inputs available - must infer from physics

---

## Phase 1: Foundation — Physics Threshold Calibration

**Goal:** Fix thresholds that are too tight for 30 Hz sampling.

### Changes

| Constant | Current | New | Rationale |
|----------|---------|-----|-----------|
| `JUMP_Z_VELOCITY_THRESHOLD` | 292.0 | 250.0 | Account for gravity decay between samples |
| `FLIP_ANGULAR_THRESHOLD` | 5.0 | 3.5 | 91% of max is too tight; misses cancels |
| `SPEEDFLIP_CANCEL_WINDOW` | 0.20 | 0.10 | Per player feedback: real speedflips cancel in ~100ms |
| `CEILING_HEIGHT_THRESHOLD` | 1900.0 | 2040.0 | Closer to actual ceiling (2044 UU) |

### Files Modified
- `src/rlcoach/analysis/mechanics.py` (constants only)

### Verification
- All existing tests pass
- No false negatives in golden replays

---

## Phase 2: Foundation — Car-Local Transforms Everywhere

**Goal:** Refactor ALL position/velocity checks to work in car-local space.

### Current Problem
```python
z_vel_increase = vel.z - state.prev_z_velocity  # Only works upright on flat ground
```
This fails for walls, ramps, tilted cars, aerial situations.

### Solution

1. **Add `_rotation_to_forward_vector()` helper** (complement to existing `_rotation_to_up_vector`):
```python
def _rotation_to_forward_vector(rotation: Rotation | Vec3) -> Vec3:
    pitch, yaw, roll = _get_rotation_values(rotation)
    # Forward vector (X-axis of rotated frame)
    ...
```

2. **Store previous velocity as Vec3** in PlayerMechanicsState:
```python
prev_velocity: Vec3 | None = None
```

3. **Refactor jump detection** to use car-local impulse:
```python
car_up = _rotation_to_up_vector(rot)
delta_v = Vec3(vel.x - prev_vel.x, vel.y - prev_vel.y, vel.z - prev_vel.z)
impulse_in_car_up = _dot(delta_v, car_up)
if impulse_in_car_up > JUMP_Z_VELOCITY_THRESHOLD:
    # Jump detected
```

4. **Apply car-local transforms to:**
   - Jump detection
   - Double jump detection
   - Dribble envelope (ball position relative to car)
   - Power slide (velocity perpendicular to car forward)

### Files Modified
- `src/rlcoach/analysis/mechanics.py`

### Verification
- All existing tests pass
- Jump counts remain similar (may increase slightly due to catching wall jumps)

---

## Phase 3: Foundation — Flip Discrimination via Angular Impulse

**Goal:** Distinguish flip from double-jump using angular impulse axis, not raw magnitude.

### Current Problem
```python
if total_rot_rate > FLIP_ANGULAR_THRESHOLD:  # 5.0 rad/s
    # This is a flip
```
This misses early cancels, messy diagonals, and can false-positive on air roll.

### Solution

Detect step-change in angular velocity + axis dominance:
```python
# Compute angular velocity delta
omega_delta = current_omega - prev_omega

# Flip signature: sharp step in angular velocity
omega_step = _magnitude_omega(omega_delta)

# Check axis alignment for flip type
# Pitch-heavy = front/back flip, Yaw-heavy = side flip
if omega_step > 2.0:  # Sudden angular change (lower than 5.0!)
    if abs(pitch_delta) > abs(yaw_delta) and abs(pitch_delta) > abs(roll_delta):
        # Front/back flip
    elif abs(roll_delta) > abs(pitch_delta):
        # Side flip
    else:
        # Diagonal flip
```

### Changes
1. Track previous angular velocities (pitch_rate, yaw_rate, roll_rate) per frame
2. Compute angular velocity delta to detect step-change
3. Use axis dominance for flip type, not total magnitude

### Files Modified
- `src/rlcoach/analysis/mechanics.py`

### Verification
- Flip detection remains accurate
- Fewer false positives from sustained air roll

---

## Phase 4: Core Fix — Wavedash (Remove Sideways, Tighter Window)

**Goal:** Detect wavedashes in any direction; tighten landing window.

### Current Problem
Current detection requires sideways velocity. Real wavedashes work forward, backward, diagonal.

### Solution
Per spec (lines 702-705):
1. Require airborne→grounded transition within **0.05-0.125s** (6-15 ticks at 120 Hz, ~2-4 frames at 30 Hz)
2. Require car pitch/roll indicates "dash" setup (flip angled toward ground)
3. Require speed gain in car's forward direction after landing
4. Remove sideways velocity requirement entirely

```python
# Wavedash detection on landing
if just_landed and state.flip_start_time is not None:
    landing_window = timestamp - state.flip_start_time
    if 0.05 <= landing_window <= 0.125:  # Tight window!
        # Check car pitch/roll at flip time - must indicate "dash" setup
        # Dash setup = car pitched down toward ground during flip
        # Use pitch at flip start: negative pitch = nose down = front wavedash setup
        # Or roll for side wavedash
        flip_pitch = state.pitch_at_flip_start or 0
        flip_roll = state.roll_at_flip_start or 0
        is_dash_setup = abs(flip_pitch) > 0.2 or abs(flip_roll) > 0.2  # ~11 degrees

        if is_dash_setup:
            # Check speed gain in car's forward direction
            car_forward = _rotation_to_forward_vector(rot)
            forward_speed_now = _dot(vel, car_forward)
            forward_speed_before = _dot(state.prev_velocity, car_forward) if state.prev_velocity else 0
            if forward_speed_now > forward_speed_before + 100:  # Speed boost
                # WAVEDASH
```

**New state fields:**
- `pitch_at_flip_start: float = 0.0`
- `roll_at_flip_start: float = 0.0`

### Changes
1. Change `WAVEDASH_LANDING_WINDOW` from 0.4 to 0.125 (max)
2. Add `WAVEDASH_LANDING_WINDOW_MIN = 0.05` (min)
3. Remove sideways velocity check
4. Add forward speed gain check

### Files Modified
- `src/rlcoach/analysis/mechanics.py`

### Verification
- Wavedash test passes
- Forward/backward wavedashes now detected

**Dependencies:** Phase 2 (car-local forward vector)

---

## Phase 5: Core Fix — Ceiling Shot (Persistence + Flip-Based)

**Goal:** Require sustained ceiling contact and flip-based detection.

### Current Problem
Only height threshold is updated. Need persistence for ceiling contact.

### Solution
Per spec (lines 998-1003):
1. Raise threshold to ~2040 UU (done in Phase 1)
2. Add persistence: car must stay near ceiling for multiple frames
3. Track `has_ceiling_flip` when car contacts ceiling with all wheels
4. Ceiling shot = using that flip before wheels touch ANY surface (ground, wall, ceiling)
5. Check car orientation: car_up · world_down > 0.7 (car is upside down / on ceiling)

```python
# Ceiling contact tracking with orientation check
world_down = Vec3(0, 0, -1)
car_up = _rotation_to_up_vector(rot)
car_upside_down = _dot(car_up, world_down) > 0.7  # Car is oriented for ceiling contact

if pos.z > CEILING_HEIGHT_THRESHOLD and abs(vel.z) < 50 and car_upside_down:
    state.ceiling_contact_frames += 1
    if state.ceiling_contact_frames >= 2:  # ~66ms persistence
        state.has_ceiling_flip = True
        state.last_ceiling_touch_time = timestamp
        state.had_surface_contact_since_ceiling = False  # Track surface contact
        state.left_ceiling_yet = False  # Reset for new ceiling contact
else:
    state.ceiling_contact_frames = 0

# Track when player LEAVES ceiling (transition from ceiling to falling)
if state.has_ceiling_flip and not state.left_ceiling_yet:
    still_on_ceiling = pos.z > CEILING_HEIGHT_THRESHOLD and car_upside_down
    if not still_on_ceiling:
        state.left_ceiling_yet = True  # Player has fallen away from ceiling

# Track ANY surface contact AFTER leaving ceiling (invalidates ceiling flip)
if state.has_ceiling_flip and state.left_ceiling_yet:
    on_ground = player.is_on_ground
    # Wall contact: near walls with low velocity perpendicular to wall
    near_wall = abs(pos.x) > FIELD.SIDE_WALL_X - 50 or abs(pos.y) > FIELD.BACK_WALL_Y - 50
    # Back on ceiling counts as surface contact too
    back_on_ceiling = pos.z > CEILING_HEIGHT_THRESHOLD and car_upside_down
    if on_ground or near_wall or back_on_ceiling:
        state.had_surface_contact_since_ceiling = True

# Ceiling shot = flip used after ceiling contact, BEFORE any surface contact
if (state.has_ceiling_flip and state.has_flipped and ball_touched
    and not state.had_surface_contact_since_ceiling):
    # CEILING_SHOT
    state.has_ceiling_flip = False  # Reset after use
```

### Changes
1. Add `ceiling_contact_frames: int = 0` to PlayerMechanicsState
2. Add `has_ceiling_flip: bool = False` to PlayerMechanicsState
3. Add `had_surface_contact_since_ceiling: bool = False` to PlayerMechanicsState
4. Add `left_ceiling_yet: bool = False` to PlayerMechanicsState
5. Require 2+ frames of ceiling contact for ceiling flip grant
6. Require car orientation check (upside down for ceiling contact)
7. Track "left ceiling" transition before counting surface contacts
8. Ceiling shot ONLY emits if flip is used before any surface contact (post-ceiling)

### Files Modified
- `src/rlcoach/analysis/mechanics.py`

### Verification
- Ceiling shot test passes
- Fewer false positives from grazing ceiling

---

## Phase 6: Core Fix — Musty Flick (Remove Dribble Requirement)

**Goal:** Detect musty from anywhere - ceiling, flip resets, walls, 50/50s.

### Current Problem
Musty requires `was_dribbling` flag. Real mustys happen anywhere.

### Solution
Per spec (line 1056): Musty = backflip + ball contact + ball acceleration (any, not just Z).

```python
# Musty detection - anywhere, not just dribble
# Per spec: "no speed gate required" - any acceleration counts
if state.has_flipped and state.flip_direction == "backward":
    if frame.ball is not None:
        ball_dist = _distance(pos, frame.ball.position)
        if ball_dist < BALL_CONTACT_PROXIMITY:
            # Check ANY velocity increase (spec: no speed gate, just acceleration)
            current_speed = _magnitude(frame.ball.velocity)
            if current_speed > state.prev_ball_speed:  # Any acceleration
                # MUSTY_FLICK
```

### Changes
1. Remove `was_dribbling` requirement from musty detection
2. Check for ball velocity increase (any direction, not just Z)
3. Keep backward flip direction check
4. Keep ball proximity check

### Files Modified
- `src/rlcoach/analysis/mechanics.py`

### Verification
- Musty detection works from any context
- No false positives on non-contact backflips

**Dependencies:** Phase 3 (flip direction detection)

---

## Phase 7: Core Fix — Fast Aerial (Same-Frame Boost)

**Goal:** Require boost on same frame as jumps, with ±1 frame tolerance.

### Current Problem
```python
if state.boost_used_in_window:  # Too loose - boost anywhere in 0.3s counts
```

### Solution
Per spec (lines 989-996):
1. Check boost delta on jump frames (±1 frame for 30 Hz tolerance)
2. Guard against pad pickups (large positive jumps in boost amount)
3. Use boost button if parser exposes it (check capabilities)

```python
# Track boost per frame
boost_delta = state.prev_boost_amount - player.boost_amount

# Pad pickup detection (boost increased, not consumed)
is_pad_pickup = boost_delta < 0

# Same-frame boost check with ±1 frame tolerance
# Store boost deltas for last 3 frames
state.recent_boost_deltas.append((timestamp, boost_delta))
state.recent_boost_deltas = [(t, d) for t, d in state.recent_boost_deltas if timestamp - t < 0.1]

def had_boost_near_time(target_time: float) -> bool:
    for t, delta in state.recent_boost_deltas:
        if abs(t - target_time) <= 0.034 and delta > 0:  # ±1 frame at 30 Hz
            return True
    return False

# Fast aerial check
if state.first_jump_time and state.second_jump_time:
    boost_on_first = had_boost_near_time(state.first_jump_time)
    boost_on_second = had_boost_near_time(state.second_jump_time)
    if boost_on_first and boost_on_second:
        # FAST_AERIAL
```

### Changes
1. Add `recent_boost_deltas: list[tuple[float, float]]` to PlayerMechanicsState
2. Track boost delta per frame with timestamp
3. Check for boost consumption within ±1 frame of jump times
4. Guard against pad pickups

### Files Modified
- `src/rlcoach/analysis/mechanics.py`

### Verification
- Fast aerial count may decrease (stricter)
- No false positives from boost used between jumps

---

## Phase 8: Core Fix — Flip Cancel (Persistence + Intent)

**Goal:** Require cancel to persist and be relative to flip's pitch intent.

### Current Problem
Single-frame pitch reversal triggers cancel. Missing flip intent check.

### Solution
Per spec (line 1053, lines 666-670):
1. Infer flip's pitch intent at flip start (front flip = positive, back flip = negative)
2. Require pitch angular velocity to become opposite sign
3. Require persistence for 3-5 frames (~0.1-0.15s at 30 Hz)
4. **Retain 0.25s max cancel window from spec** (FLIP_CANCEL_WINDOW = 0.25)

```python
# At flip start, record intended pitch direction
state.flip_pitch_intent = 1 if pitch_rate > 0 else -1 if pitch_rate < 0 else 0

# Cancel detection with persistence (within 0.25s max window)
FLIP_CANCEL_WINDOW = 0.25  # Retained from spec
if state.has_flipped and state.flip_start_time:
    flip_elapsed = timestamp - state.flip_start_time
    if flip_elapsed <= FLIP_CANCEL_WINDOW:  # Must be within 0.25s
        # Check pitch reversal relative to intent
        pitch_reversed = (state.flip_pitch_intent > 0 and pitch_rate < -1.0) or \
                         (state.flip_pitch_intent < 0 and pitch_rate > 1.0)

        if pitch_reversed:
            if state.flip_cancel_start_time is None:
                state.flip_cancel_start_time = timestamp
            elif timestamp - state.flip_cancel_start_time >= 0.1:  # 3 frames persistence
                if not state.flip_cancel_confirmed:
                    state.flip_cancel_confirmed = True
                    # Emit FLIP_CANCEL
        else:
            # Cancel criteria no longer met - reset
            state.flip_cancel_start_time = None
```

### Changes
1. Add `flip_pitch_intent: int = 0` to PlayerMechanicsState
2. Add `flip_cancel_start_time: float | None` to PlayerMechanicsState
3. Add `flip_cancel_confirmed: bool = False` to PlayerMechanicsState
4. Record pitch intent at flip start
5. Require reversal relative to intent
6. Require ~3 frame persistence

### Files Modified
- `src/rlcoach/analysis/mechanics.py`

### Verification
- Flip cancel detection is stricter
- Fewer false positives from single-frame noise

---

## Phase 9: Core Fix — Double Touch (Velocity Sign-Flip)

**Goal:** Use velocity sign-flip to detect actual wall bounce.

### Current Problem
```python
near_back_wall = abs(ball_pos.y) > FIELD.BACK_WALL_Y - WALL_PROXIMITY
# Position-based, doesn't verify actual bounce
```

### Solution
Per spec (lines 780-787):
```python
# Near back wall: require v_y sign flip
near_back_wall = abs(ball_pos.y) > FIELD.BACK_WALL_Y - WALL_PROXIMITY
if near_back_wall and state.prev_ball_velocity:
    # Check for velocity reversal
    prev_vy = state.prev_ball_velocity.y
    curr_vy = frame.ball.velocity.y
    # Toward wall → away from wall
    if ball_pos.y > 0:  # Positive end wall
        bounced = prev_vy > 0 and curr_vy < 0
    else:  # Negative end wall
        bounced = prev_vy < 0 and curr_vy > 0

    if bounced:
        state.wall_bounce_detected = True
```

Same logic for side walls with X velocity.

### Changes
1. Replace position-only wall check with velocity sign-flip detection
2. Track previous ball velocity (already in state)
3. Require velocity component reversal for bounce

### Files Modified
- `src/rlcoach/analysis/mechanics.py`

### Verification
- Double touch detection is more accurate
- Fewer false positives from air dribbles near walls

---

## Phase 10: Core Fix — Speedflip (Bucket Scoring)

**Goal:** Treat cancel timing as ~3 frame bucket, not razor threshold.

### Current Problem
Plan only updates window constant. Spec requires bucket-style scoring.

### Solution
Per spec (lines 969-979):
```python
# Speedflip scoring - bucket approach (100ms = ~3 frames at 30 Hz)
def score_speedflip(cancel_latency: float, has_boost: bool, forward_accel: float) -> float:
    # Cancel latency buckets - spec requires 100ms window treated as ~3 frame bucket
    if cancel_latency <= 0.033:  # 1 frame - great
        latency_score = 3
    elif cancel_latency <= 0.066:  # 2 frames - good
        latency_score = 2
    elif cancel_latency <= 0.100:  # 3 frames (100ms) - acceptable
        latency_score = 1
    else:
        latency_score = 0  # Beyond 100ms = not a speedflip

    boost_score = 1 if has_boost else 0
    accel_score = 1 if forward_accel > 500 else 0  # Forward acceleration discriminator

    return latency_score + boost_score + accel_score

# Speedflip if score >= 3 (must have at least some latency credit + other signals)
if is_diagonal_flip and state.flip_cancel_confirmed:
    cancel_latency = state.flip_cancel_start_time - state.flip_start_time
    if cancel_latency <= 0.100:  # Within 100ms window
        forward_accel = _dot(vel, car_forward) - _dot(state.vel_at_flip_start, car_forward)
        has_boost = state.boost_used_since_flip > 0

        if score_speedflip(cancel_latency, has_boost, forward_accel) >= 3:
            # SPEEDFLIP
```

### Changes
1. Add scoring function for speedflip
2. Add `vel_at_flip_start: Vec3 | None` to PlayerMechanicsState
3. Add `boost_used_since_flip: int = 0` to track boost during flip
4. Use bucket scoring instead of razor threshold

### Files Modified
- `src/rlcoach/analysis/mechanics.py`

### Verification
- Speedflip detection is more robust
- Forward acceleration discriminator reduces false positives

**Dependencies:** Phase 2 (car-local forward vector), Phase 8 (cancel detection)

---

## Phase 11: Mechanic Refinement — Dribble (Car-Local + Oval Footprint)

**Goal:** Transform dribble envelope to car-local coords with oval footprint.

### Current Problem
Uses world-space XY distance. Doesn't work on ramps, slopes.

### Solution
Per spec (line 1057):
```python
# Transform ball to car-local coordinates
car_up = _rotation_to_up_vector(rot)
car_forward = _rotation_to_forward_vector(rot)
car_right = _cross(car_forward, car_up)

ball_offset = Vec3(ball_pos.x - pos.x, ball_pos.y - pos.y, ball_pos.z - pos.z)
local_x = _dot(ball_offset, car_right)    # Side-to-side
local_y = _dot(ball_offset, car_forward)  # Front-to-back
local_z = _dot(ball_offset, car_up)       # Above car

# Oval footprint: tighter side-to-side than front-to-back
in_footprint = (local_x / 80)**2 + (local_y / 120)**2 <= 1  # Oval equation
in_height = DRIBBLE_Z_MIN < local_z < DRIBBLE_Z_MAX
```

### Changes
1. Add `_cross()` helper for cross product
2. Transform ball position to car-local coordinates
3. Use oval footprint (80 UU side, 120 UU front/back)
4. Use local_z for height check

### Files Modified
- `src/rlcoach/analysis/mechanics.py`

### Verification
- Dribble detection works on any surface angle
- Oval footprint is more realistic

**Dependencies:** Phase 2 (car-local transforms)

---

## Phase 12: Mechanic Refinement — Flip Reset (TOUCH + USE Split)

**Goal:** Emit separate events for reset acquisition and usage.

### Current Problem
Only emits FLIP_RESET when the reset flip is executed.

### Solution
Per spec (line 1059):
```python
# New mechanic types
class MechanicType(Enum):
    FLIP_RESET_TOUCH = "flip_reset_touch"  # Acquired reset
    FLIP_RESET_USE = "flip_reset_use"      # Used reset flip

# On underside contact
if underside_contact_detected:
    # Emit FLIP_RESET_TOUCH immediately
    events.append(MechanicEvent(..., mechanic_type=MechanicType.FLIP_RESET_TOUCH))
    state.flip_available_from_reset = True

# On flip after reset
if state.flip_available_from_reset and state.has_flipped:
    # Emit FLIP_RESET_USE
    events.append(MechanicEvent(..., mechanic_type=MechanicType.FLIP_RESET_USE))
```

### Changes
1. Add `FLIP_RESET_TOUCH` and `FLIP_RESET_USE` to MechanicType (keep `FLIP_RESET` for backwards compat)
2. Emit TOUCH on acquisition
3. Emit USE on flip execution
4. Update schema and golden files

### Files Modified
- `src/rlcoach/analysis/mechanics.py`
- `schemas/rlcoach-report.json`

### Verification
- Both events emit correctly
- Count of touches >= count of uses

---

## Phase 13: New Mechanic — Skim

**Goal:** Detect underside ball contact that accelerates ball toward opponent goal.

### Definition
Skim = underside contact + ball velocity increase + ball heading toward opponent goal.

### Detection Logic
Per spec (lines 820-836):
```python
if state.is_airborne and frame.ball is not None:
    car_up = _rotation_to_up_vector(rot)
    car_to_ball = Vec3(ball_pos.x - pos.x, ball_pos.y - pos.y, ball_pos.z - pos.z)
    # Ball is in direction of car's DOWN (underside contact)
    # Use car_to_ball, check if dot with car_up is negative
    underside_contact = _dot(car_up, _normalize_vec(car_to_ball)) < -0.7

    if underside_contact and ball_dist < BALL_CONTACT_PROXIMITY:
        # Check ball velocity increase (any amount per spec)
        current_speed = _magnitude(frame.ball.velocity)
        if current_speed > state.prev_ball_speed:
            # Check toward opponent goal AFTER touch
            if is_toward_opponent_goal(player_team, frame.ball.velocity):
                # SKIM detected (orthogonal to flip reset - can emit both)
```

### Changes
1. Add `SKIM` to MechanicType enum
2. Add skim detection in airborne ball contact section
3. Skim is orthogonal to flip reset (can emit both on same touch)

### New Constants
```python
SKIM_DOT_THRESHOLD = -0.7  # Ball below car
```

### Files Modified
- `src/rlcoach/analysis/mechanics.py`

### Verification
- Skim detection works
- Schema updated with skim_count

---

## Phase 14: New Mechanic — Psycho

**Goal:** Detect the ultimate combo: backboard slam → invert → skim.

### Definition
Psycho = intentional backboard slam + flip to invert + skim redirect toward opponent goal.

### State Machine
Per spec (lines 838-851, 1023-1036):

```
State 1: WATCHING
  - Ball heading toward player's OWN goal
  - Player touches ball near own backboard
  - Ball velocity toward own goal INCREASES (intentional slam)
  - Ball bounces off backboard (velocity sign flip)
  → Transition to INVERTING, record slam time

State 2: INVERTING
  - Player is rotating/flipping
  - Car becomes inverted: dot(car_up, world_up) < -0.5
  → Transition to SKIM_READY

State 3: SKIM_READY
  - Player is inverted
  - If skim occurs within 3.0s of backboard slam → PSYCHO
  - Reset on landing
```

### Implementation
```python
# Use goal direction vectors (spec lines 1025-1031)
own_goal_direction = get_own_goal_direction(player_team)
ball_toward_own_goal = _dot(frame.ball.velocity, own_goal_direction) > 500

# State 1: Backboard slam detection with velocity sign-flip
if ball_toward_own_goal and near_own_backboard:
    ball_touched = _distance(pos, ball_pos) < BALL_CONTACT_PROXIMITY
    if ball_touched:
        # Check ball velocity toward own goal INCREASED
        prev_toward_goal = _dot(state.prev_ball_velocity, own_goal_direction) if state.prev_ball_velocity else 0
        curr_toward_goal = _dot(frame.ball.velocity, own_goal_direction)
        if curr_toward_goal > prev_toward_goal + 200:  # Intentional slam
            # Wait for wall bounce (velocity sign flip)
            state.psycho_waiting_for_bounce = True
            state.psycho_slam_time = timestamp

# Detect wall bounce
if state.psycho_waiting_for_bounce and near_own_backboard:
    if ball_velocity_reversed:  # Sign flip detection
        state.psycho_state = "INVERTING"
        state.psycho_waiting_for_bounce = False

# State 2: Check for inversion
if state.psycho_state == "INVERTING":
    car_up = _rotation_to_up_vector(rot)
    world_up = Vec3(0, 0, 1)
    if _dot(car_up, world_up) < -0.5:  # Inverted
        state.psycho_state = "SKIM_READY"

# State 3: Skim detection
if state.psycho_state == "SKIM_READY":
    if skim_detected and timestamp - state.psycho_slam_time < PSYCHO_WINDOW:
        # PSYCHO detected!

# Reset on landing or timeout
if on_ground or (state.psycho_slam_time and timestamp - state.psycho_slam_time > PSYCHO_WINDOW):
    state.psycho_state = None
    state.psycho_slam_time = None
```

### Changes
1. Add `PSYCHO` to MechanicType enum
2. Add state machine fields to PlayerMechanicsState:
   - `psycho_state: str | None = None`
   - `psycho_slam_time: float | None = None`
   - `psycho_waiting_for_bounce: bool = False`
3. Implement state machine with goal-direction vectors
4. Require wall bounce sign-flip for backboard slam

### New Constants
```python
PSYCHO_WINDOW = 3.0  # seconds - max time from backboard slam to skim
PSYCHO_INVERT_THRESHOLD = -0.5  # car_up · world_up < this = inverted
```

### Files Modified
- `src/rlcoach/analysis/mechanics.py`

### Verification
- Psycho detection works (may be rare in test data)
- No false positives from normal clears (requires intentional slam + bounce + invert)

**Dependencies:** Phase 13 (Skim detection)

---

## Phase 15: Schema & Golden Updates

**Goal:** Update schema and regenerate golden files.

### Changes
1. Add new fields to player mechanics schema:
   - `skim_count`
   - `psycho_count`
   - `flip_reset_touch_count`
   - `flip_reset_use_count`
2. Regenerate golden files with new detection logic

### Files Modified
- `schemas/rlcoach-report.json`
- `tests/goldens/synthetic_small.json`
- `tests/goldens/synthetic_small.md`

### Verification
- Schema validation passes
- All tests pass

---

## Phase 16: Final Verification

**Goal:** Full quality gate pass and Codex final review.

### Steps
1. Run full test suite: `PYTHONPATH=src pytest -q`
2. Run linter: `ruff check src/`
3. Run formatter: `black --check src/`
4. Call Codex for final cross-check
5. Commit all changes

---

## Acceptance Criteria

### Foundation (Phases 1-3)
- [ ] All threshold calibrations applied (Phase 1)
- [ ] Car-local transforms applied everywhere (Phase 2)
- [ ] Flip discrimination uses angular impulse axis (Phase 3)

### Core Fixes (Phases 4-10)
- [ ] Wavedash: 0.05-0.125s window, any direction, speed gain (Phase 4)
- [ ] Ceiling shot: persistence + flip-based (Phase 5)
- [ ] Musty: works anywhere, any ball acceleration (Phase 6)
- [ ] Fast aerial: same-frame boost ±1 frame, pad pickup guard (Phase 7)
- [ ] Flip cancel: persistence + relative to intent (Phase 8)
- [ ] Double touch: velocity sign-flip bounce (Phase 9)
- [ ] Speedflip: bucket scoring (Phase 10)

### Mechanic Refinements (Phases 11-12)
- [ ] Dribble: car-local, oval footprint (Phase 11)
- [ ] Flip reset: TOUCH + USE split (Phase 12)

### New Mechanics (Phases 13-14)
- [ ] Skim: underside contact + acceleration + toward goal (Phase 13)
- [ ] Psycho: slam + bounce + invert + skim state machine (Phase 14)

### Final (Phases 15-16)
- [ ] Schema updated (Phase 15)
- [ ] All tests pass (Phase 16)
- [ ] Codex final review passed

---

## Phase Dependencies

```
Phase 1 (thresholds) ─┬─► Phase 2 (car-local)
                      │
                      └─► Phase 3 (flip discrimination)
                              │
                              ▼
┌─────────────────────────────┴───────────────────────────────┐
│  Phases 4-12 depend on foundation (2 & 3)                   │
│  Can be parallelized within groups:                         │
│    Group A: 4, 5, 6, 9, 11 (independent)                    │
│    Group B: 7 (fast aerial - boost tracking)                │
│    Group C: 8, 10 (flip cancel → speedflip)                 │
│    Group D: 12 (flip reset split)                           │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
                      Phase 13 (Skim)
                              │
                              ▼
                      Phase 14 (Psycho)
                              │
                              ▼
                      Phase 15 (Schema)
                              │
                              ▼
                      Phase 16 (Final)
```

---

## Future Improvements (Deferred)

Per spec (lines 1065-1068):
- [ ] Confidence scoring for edge cases
- [ ] Air Roll TAP vs HELD distinction
- [ ] Speed-dependent thresholds for flip reset

These are marked as deferred and not part of this implementation plan.

---

## Risk Notes

1. **Threshold changes may affect test assertions** - golden files will need regeneration
2. **Psycho may be very rare** - hard to test without specific replay data
3. **Car-local transforms are complex** - need careful testing
4. **30 Hz sampling limits precision** - accept ±33ms timing tolerance

---

*Plan created based on MECHANICS_DETECTION.md spec with player feedback and technical review. Revised based on Codex review feedback.*
