# SPEC: Extended Mechanics Detection

> Extend `src/rlcoach/analysis/mechanics.py` to detect additional game mechanics from replay frame data.

---

## Problem Statement

The current mechanics analyzer detects 8 mechanics (jump, double jump, flip, wavedash, flip cancel, half-flip, speedflip, aerial). Players want visibility into advanced mechanics like fast aerials, flip resets, dribbles, flicks, and ceiling plays. Adding these mechanics enables better coaching insights and skill progression tracking.

---

## Scope

### In Scope

**High Priority (Phase 1):**
- Fast Aerial detection
- Flip Reset detection
- Air Roll tracking (sustained aerial rotation)

**Medium Priority (Phase 2):**
- Dribble detection (ball carry on car roof)
- Generic Flick detection (ball departure from dribble during flip)
- Musty Flick detection (backflip flick with upward ball trajectory)
- Ceiling Shot detection (ceiling touch → aerial play)
- Power Slide detection (sideways velocity while grounded)

**Lower Priority (Phase 3):**
- Ground Pinch detection
- Double Touch detection (two aerial touches, same possession)
- Redirect detection (aerial touch redirecting ball toward goal)
- Stall detection (tornado spin hover)

### Out of Scope

- Breezi flick (requires input timing we don't have)
- 45-degree flick (requires precise angle measurement that may be unreliable)
- Bounce dribble (too nuanced for reliable physics-only detection)
- Any mechanic requiring controller input data

---

## Data Model

### New MechanicType Enum Values

```python
class MechanicType(Enum):
    # Existing
    JUMP = "jump"
    DOUBLE_JUMP = "double_jump"
    FLIP = "flip"
    DODGE = "dodge"
    WAVEDASH = "wavedash"
    FLIP_CANCEL = "flip_cancel"
    AERIAL = "aerial"
    HALF_FLIP = "half_flip"
    SPEEDFLIP = "speedflip"

    # Phase 1 - New
    FAST_AERIAL = "fast_aerial"
    FLIP_RESET = "flip_reset"
    AIR_ROLL = "air_roll"

    # Phase 2 - New
    DRIBBLE = "dribble"
    FLICK = "flick"
    MUSTY_FLICK = "musty_flick"
    CEILING_SHOT = "ceiling_shot"
    POWER_SLIDE = "power_slide"

    # Phase 3 - New
    GROUND_PINCH = "ground_pinch"
    DOUBLE_TOUCH = "double_touch"
    REDIRECT = "redirect"
    STALL = "stall"
```

### MechanicEvent Extensions

```python
@dataclass(frozen=True)
class MechanicEvent:
    timestamp: float
    player_id: str
    mechanic_type: MechanicType
    position: Vec3
    velocity: Vec3
    direction: str | None = None
    height: float = 0.0
    duration: float | None = None
    # New optional fields
    ball_position: Vec3 | None = None  # For ball-related mechanics
    ball_velocity_change: float | None = None  # For flicks/pinches
    boost_used: int | None = None  # For fast aerial tracking
```

### Per-Player Output Schema Additions

```python
{
    "fast_aerial_count": int,
    "flip_reset_count": int,
    "air_roll_total_time_s": float,
    "dribble_count": int,
    "dribble_total_time_s": float,
    "flick_count": int,
    "musty_flick_count": int,
    "ceiling_shot_count": int,
    "power_slide_count": int,
    "power_slide_total_time_s": float,
    "ground_pinch_count": int,
    "double_touch_count": int,
    "redirect_count": int,
    "stall_count": int
}
```

---

## Detection Algorithms

### Phase 1: High Priority

#### Fast Aerial

**Definition:** Jump + boost + second jump within 0.5s, reaching height > 300 UU within 1.0s of first jump.

**Detection:**
1. Detect first jump (existing logic)
2. Track boost consumption between frames: `boost_delta = prev_boost - current_boost`
3. If `boost_delta > 0` within 0.3s of jump AND (double_jump OR flip) within 0.5s of first jump
4. If height > 300 UU within 1.0s of first jump → emit FAST_AERIAL

**Thresholds:**
- `FAST_AERIAL_BOOST_WINDOW = 0.3` seconds
- `FAST_AERIAL_SECOND_JUMP_WINDOW = 0.5` seconds
- `FAST_AERIAL_HEIGHT_THRESHOLD = 300.0` UU
- `FAST_AERIAL_TIME_TO_HEIGHT = 1.0` seconds

#### Flip Reset

**Definition:** Ball contact on car's underside while airborne that restores flip availability, followed by a flip.

**Detection:**
1. Player is airborne AND has_flipped = True (flip consumed)
2. Compute car up vector from rotation: `up = rotation_to_up_vector(car.rotation)`
3. Compute ball-to-car vector: `ball_to_car = normalize(car.position - ball.position)`
4. Check underside contact: `dot(up, ball_to_car) > 0.7` (ball is below/behind car)
5. Check proximity: `distance(car.position, ball.position) < 120.0` UU (near ball radius + car hitbox)
6. Set `flip_available_from_reset = True` on contact
7. If player executes flip while `flip_available_from_reset = True`, emit FLIP_RESET at the touch timestamp
8. Reset `flip_available_from_reset = False` after flip or on landing

**Thresholds:**
- `FLIP_RESET_PROXIMITY = 120.0` UU (ball radius ~93 + margin)
- `FLIP_RESET_DOT_THRESHOLD = 0.7` (ball roughly under car)
- `FLIP_RESET_WINDOW = 2.0` seconds (max time between touch and reset flip)

**State Machine Change:** Add `flip_available_from_reset` flag that allows one additional flip mid-air after underside contact.

#### Air Roll

**Definition:** Sustained roll rotation (> 2.0 rad/s) while airborne for > 0.3s.

**Detection:**
1. Player is airborne
2. Compute roll rate with angle wrapping: `roll_rate = normalize_angle(current_roll - prev_roll) / dt`
   - Use `normalize_angle()` to handle wrapping at ±π
3. Exclude flip-induced rotation: if flip detected in same frame, skip air roll check for 0.2s
4. Track sustained roll: `|roll_rate| > AIR_ROLL_THRESHOLD` for consecutive frames
5. **Start condition:** First frame where `|roll_rate| > threshold` while airborne
6. **End condition:** `|roll_rate| < threshold` OR player lands OR flip starts
7. If duration > 0.3s, emit AIR_ROLL with duration

**Thresholds:**
- `AIR_ROLL_RATE_THRESHOLD = 2.0` rad/s
- `AIR_ROLL_MIN_DURATION = 0.3` seconds
- `AIR_ROLL_FLIP_EXCLUSION_WINDOW = 0.2` seconds

**Output:** Single event per continuous air roll segment, with `duration` field populated.

---

### Phase 2: Medium Priority

#### Dribble

**Definition:** Ball on car roof (within XY radius, ball Z above car Z by approximately ball radius) for > 0.5s. Ground dribbles only; wall/air dribbles excluded.

**Detection:**
1. Compute ball-to-car offset: `dx = ball.x - car.x`, `dy = ball.y - car.y`, `dz = ball.z - car.z`
2. Transform to car-local coordinates using car rotation
3. Check horizontal envelope: `sqrt(local_x² + local_y²) < 100` UU
4. Check vertical position: `90 < dz < 180` UU (ball center ~93 UU above car center when on roof)
5. Check car is grounded: `car.z < 50` UU (exclude wall/air dribbles)
6. Check relative velocity: `|ball_vel - car_vel| < 300` UU/s
7. If conditions hold for > 0.5s, emit DRIBBLE with duration at end

**Thresholds:**
- `DRIBBLE_XY_RADIUS = 100.0` UU (ball within this radius of car center)
- `DRIBBLE_Z_MIN = 90.0` UU (car roof ~17 + ball radius ~93 - margin)
- `DRIBBLE_Z_MAX = 180.0` UU (ball center, not too high)
- `DRIBBLE_CAR_HEIGHT_MAX = 50.0` UU (car must be grounded, not on wall)
- `DRIBBLE_RELATIVE_VELOCITY_MAX = 300.0` UU/s
- `DRIBBLE_MIN_DURATION = 0.5` seconds

**Note:** Wall dribbles and air dribbles are out of scope for v1.

#### Flick (Generic)

**Definition:** Ball departs car during flip, gaining > 500 UU/s velocity.

**Detection:**
1. Player was in dribble state (or ball within dribble envelope)
2. Player executes flip
3. Record ball velocity at flip start: `pre_flip_ball_speed = |ball.velocity|`
4. Within 0.3s of flip, check ball velocity: `post_flip_ball_speed = |ball.velocity|`
5. Compute delta: `ball_velocity_change = post_flip_ball_speed - pre_flip_ball_speed`
6. If `ball_velocity_change > 500` UU/s, emit FLICK with `ball_velocity_change` field

**Thresholds:**
- `FLICK_VELOCITY_GAIN = 500.0` UU/s (magnitude delta, not vector delta)
- `FLICK_DETECTION_WINDOW = 0.3` seconds after flip

**Velocity Computation:** Use magnitude delta (`|post| - |pre|`), not vector delta magnitude (`|post - pre|`). This measures net speed gain, not direction change.

#### Musty Flick

**Definition:** Backward flip while dribbling, ball gains significant upward (+Z) velocity > 800 UU/s.

**Detection:**
1. Player was in dribble state
2. Player executes backward flip (existing direction detection)
3. Ball Z velocity increases > 800 UU/s within 0.3s
4. Emit MUSTY_FLICK

**Thresholds:**
- `MUSTY_FLICK_Z_VELOCITY_GAIN = 800.0` UU/s

#### Ceiling Shot

**Definition:** Player touches ceiling (car Z > 1900 UU), then makes aerial ball contact.

**Detection:**
1. Track ceiling contact: `car.z > CEILING_HEIGHT_THRESHOLD` (1900 UU, consistent with `events/constants.py`)
2. Record `last_ceiling_touch_time` when ceiling contact detected
3. After ceiling contact, player falls (becomes airborne)
4. Ball touch occurs while airborne within window (use existing touch detection or proximity)
5. Emit CEILING_SHOT at the ball touch timestamp

**Thresholds:**
- `CEILING_HEIGHT_THRESHOLD = 1900.0` UU (aligned with existing `CEILING_HEIGHT_THRESHOLD` in events/constants.py)
- `CEILING_SHOT_WINDOW = 3.0` seconds (max time between ceiling touch and ball touch)

#### Power Slide

**Definition:** Significant sideways velocity relative to car facing direction while grounded.

**Detection:**
1. Player is on ground (`is_on_ground = True` or `z < 25`)
2. Compute car forward vector from yaw: `forward = (cos(yaw), sin(yaw), 0)`
3. Compute sideways component of velocity: `sideways = velocity - (velocity · forward) * forward`
4. If `|sideways| > 500 UU/s` for > 0.2s, emit POWER_SLIDE with duration

**Thresholds:**
- `POWER_SLIDE_VELOCITY_THRESHOLD = 500.0` UU/s (sideways component)
- `POWER_SLIDE_MIN_DURATION = 0.2` seconds

---

### Phase 3: Lower Priority

#### Ground Pinch

**Definition:** Ball pinched between car and ground, resulting in massive velocity gain (> 1500 UU/s delta) with high exit velocity (> 3000 UU/s).

**Detection:**
1. Ball touch detected (proximity-based)
2. Ball Z < 100 UU at touch time (ball is near ground)
3. Record pre-touch ball velocity: `pre_speed = |ball.velocity|` (frame before touch)
4. Record post-touch ball velocity: `post_speed = |ball.velocity|` (frame after touch)
5. Compute delta: `velocity_delta = post_speed - pre_speed`
6. If `post_speed > 3000` UU/s AND `velocity_delta > 1500` UU/s, emit GROUND_PINCH

**Thresholds:**
- `GROUND_PINCH_HEIGHT_MAX = 100.0` UU
- `GROUND_PINCH_EXIT_VELOCITY_MIN = 3000.0` UU/s (post-touch speed)
- `GROUND_PINCH_VELOCITY_DELTA_MIN = 1500.0` UU/s (speed gain from touch)

**Rationale:** Requiring both high exit velocity AND large velocity delta filters out strong ground shots and kickoff hits that happen to have high speed but don't involve a pinch mechanic.

#### Double Touch

**Definition:** Two aerial touches by same player without landing, with ball bouncing off backboard/wall between touches.

**Detection:**
1. First aerial touch detected (car Z > 300 UU at touch, aligned with `AERIAL_HEIGHT_THRESHOLD`)
2. Player remains airborne
3. Ball contacts backboard or wall (ball position near `FIELD.BACK_WALL_Y` or `FIELD.SIDE_WALL_X`)
4. Second aerial touch by same player within 3.0s of first touch
5. Emit DOUBLE_TOUCH on second touch

**Wall/Backboard Detection:**
- Backboard contact: `|ball.y| > FIELD.BACK_WALL_Y - 200` (within 200 UU of back wall)
- Side wall contact: `|ball.x| > FIELD.SIDE_WALL_X - 200` (within 200 UU of side wall)
- Must occur between first and second touch

**Thresholds:**
- `DOUBLE_TOUCH_WINDOW = 3.0` seconds
- `DOUBLE_TOUCH_HEIGHT_MIN = 300.0` UU (aligned with AERIAL_HEIGHT_THRESHOLD)
- `WALL_PROXIMITY = 200.0` UU

**Rationale:** Requiring wall/backboard interaction between touches distinguishes true double touches from simple multi-touch aerials or passing plays.

#### Redirect

**Definition:** Aerial touch that changes ball direction > 45° toward opponent goal, with sufficient ball speed.

**Detection:**
1. Aerial touch detected (car Z > 300 UU)
2. Check minimum ball speed: `|ball.velocity| > 500` UU/s (filter out slow touches)
3. Compute pre-touch direction: `pre_dir = normalize(ball.velocity)` (frame before touch)
4. Compute post-touch direction: `post_dir = normalize(ball.velocity)` (frame after touch)
5. Compute angle change: `angle = acos(dot(pre_dir, post_dir))`
6. Check post-touch is toward opponent goal: `is_toward_opponent_goal(team, ball.velocity)`
7. If `angle > 0.785` radians (45°) and toward goal, emit REDIRECT

**Thresholds:**
- `REDIRECT_ANGLE_THRESHOLD = 0.785` radians (45°)
- `REDIRECT_MIN_BALL_SPEED = 500.0` UU/s (filter slow/dribble touches)
- `REDIRECT_HEIGHT_MIN = 300.0` UU (aligned with AERIAL_HEIGHT_THRESHOLD)

**Rationale:** Minimum ball speed filter prevents noisy angle calculations on slow-moving balls where small velocity changes can produce large angle deltas.

#### Stall

**Definition:** Tornado spin pattern (high roll rate with opposite-signed yaw rate) causing near-zero vertical velocity mid-air. Detected purely from kinematics, not inputs.

**Detection:**
1. Player is airborne at height > 300 UU (aligned with AERIAL_HEIGHT_THRESHOLD)
2. Compute roll rate and yaw rate from rotation deltas
3. Check tornado pattern: `|roll_rate| > 3.0` rad/s AND `|yaw_rate| > 2.0` rad/s AND `sign(roll_rate) != sign(yaw_rate)`
4. Check hover condition: `|velocity.z| < 100` UU/s (near-zero vertical velocity)
5. Check low forward speed: `|velocity.xy| < 500` UU/s (not just flying fast)
6. If all conditions met for > 0.15s, emit STALL

**Thresholds:**
- `STALL_ROLL_RATE_MIN = 3.0` rad/s
- `STALL_YAW_RATE_MIN = 2.0` rad/s
- `STALL_VERTICAL_VELOCITY_MAX = 100.0` UU/s
- `STALL_HORIZONTAL_VELOCITY_MAX = 500.0` UU/s
- `STALL_HEIGHT_MIN = 300.0` UU
- `STALL_MIN_DURATION = 0.15` seconds

**Kinematics-Only:** This detection uses observable rotation rates and velocities only—no controller input data required. The opposite-signed roll/yaw rates are inferred from the physics state.

---

## Technical Approach

### Architecture

Extend the existing `mechanics.py` module. Add new detection functions that integrate with the existing frame iteration loop in `detect_mechanics_for_player()`.

**State Tracking Additions:**
```python
@dataclass
class PlayerMechanicsState:
    # ... existing fields ...

    # Fast aerial tracking
    first_jump_time: float | None = None
    boost_at_first_jump: int = 0
    boost_used_since_jump: int = 0

    # Dribble tracking
    dribble_start_time: float | None = None
    is_dribbling: bool = False

    # Flip reset tracking
    last_aerial_touch_time: float | None = None
    flip_available_from_reset: bool = False

    # Air roll tracking
    air_roll_start_time: float | None = None
    is_air_rolling: bool = False

    # Power slide tracking
    power_slide_start_time: float | None = None
    is_power_sliding: bool = False

    # Ceiling shot tracking
    last_ceiling_touch_time: float | None = None

    # Double touch tracking
    aerial_touch_count_since_ground: int = 0
    first_aerial_touch_time: float | None = None
```

### Integration Points

1. **Touch Events:** Import and use `detect_touches()` from `events/touches.py` for ball contact detection, or use proximity-based detection inline.

2. **Ball Data:** Each `Frame` contains `ball: BallFrame` with position and velocity.

3. **Goal Direction:** Use `is_toward_opponent_goal()` from `events/utils.py` for redirect detection.

### Dependencies

- No new external dependencies
- Reuses existing field constants, Vec3, Frame types
- May import from `events/touches.py` for touch detection

---

## Acceptance Criteria

### Phase 1

- [ ] Fast aerial detected when: jump + boost usage + second jump within 0.5s, height > 300 UU within 1.0s
- [ ] Flip reset detected when: airborne touch after flip used, followed by another flip
- [ ] Air roll detected when: roll rate > 2.0 rad/s sustained > 0.3s while airborne
- [ ] All new mechanics appear in per_player output with counts
- [ ] Existing mechanics tests still pass (no regressions)

### Phase 2

- [ ] Dribble detected when: ball in dribble envelope for > 0.5s
- [ ] Flick detected when: ball departs dribble during flip with velocity gain > 500 UU/s
- [ ] Musty flick detected when: backward flip from dribble with ball Z velocity gain > 800 UU/s
- [ ] Ceiling shot detected when: ceiling touch followed by aerial ball touch within 3.0s
- [ ] Power slide detected when: sideways velocity > 500 UU/s for > 0.2s while grounded

### Phase 3

- [ ] Ground pinch detected when: ball touch with ball Z < 100 UU, exit velocity > 3000 UU/s
- [ ] Double touch detected when: two aerial touches by same player within 3.0s without landing
- [ ] Redirect detected when: aerial touch changes ball direction > 45° toward goal
- [ ] Stall detected when: tornado spin pattern with near-zero vertical velocity mid-air

### All Phases

- [ ] Unit tests with synthetic frame data for each new mechanic (builder pattern)
- [ ] Integration test with real replay confirming no crashes
- [ ] Schema updated with new metric keys
- [ ] Report markdown includes new mechanics in player stats section

---

## Edge Cases

1. **Rapid mechanics overlap:** Player does fast aerial into flip reset — both should be detected as separate events
2. **Dribble interrupted by bump:** Dribble ends without flick if ball leaves envelope without flip
3. **Ceiling slide vs ceiling touch:** Only count as ceiling shot if player was on ceiling, not just sliding near it
4. **Multiple flip resets:** Each touch that restores flip and is followed by flip = separate flip reset
5. **Power slide into wavedash:** Can coexist; wavedash is flip-based, power slide is velocity-based
6. **Stall detection false positives:** Require minimum height to avoid detecting grounded spins
7. **Ball on side of car:** Not a dribble — require ball Z above car Z
8. **Very short dribbles:** Require 0.5s minimum to filter noise
9. **Flip reset without using it:** Don't count — must actually flip after the reset

---

## Non-Functional Requirements

- **Performance:** Detection should add < 5ms per 1000 frames (existing loop iteration pattern)
- **Test Coverage:** > 80% line coverage for new detection code
- **Backward Compatibility:** Existing per_player keys unchanged; new keys added alongside

---

## Testing Strategy

1. **Unit Tests:** Use `tests/fixtures/builders.py` to create synthetic frame sequences that trigger each mechanic
2. **Golden Tests:** Verify output format matches expected JSON structure
3. **Regression Tests:** Run existing `test_mechanics.py` tests to ensure no breakage
4. **Integration Tests:** Process a real replay file and verify no exceptions

---

## Open Questions (Resolved)

1. Should dribble emit one event at start or one event at end with duration?
   **Decision: One event at end with duration field.**

2. Should we track "air roll left" vs "air roll right" direction?
   **Decision: Not in v1; direction is nice-to-have for later.**

3. Should flip reset require the reset flip to be successful (not cancelled)?
   **Decision: No, count the reset regardless of what the player does with it.**
