# Mechanics Detection Reference

This document describes how each mechanic is detected in `src/rlcoach/analysis/mechanics.py`. Review this as an experienced player to validate detection logic.

---

## Detection Overview Table

| Mechanic | Trigger | Key Thresholds | Notes/Concerns |
|----------|---------|----------------|----------------|
| **Jump** | Z velocity spike > 292 UU/s while airborne | `JUMP_COOLDOWN = 0.1s` | Detected before flip if flip follows |
| **Double Jump** | Second Z velocity spike > 292 UU/s, no rotation | Must not have flipped yet | Pure vertical second jump only |
| **Flip** | Z velocity spike + rotation rate > 5 rad/s | Consumes double jump | Direction inferred from velocity + rotation |
| **Flip Cancel** | Pitch rate reversal > 3 rad/s within 0.25s of flip | `FLIP_CANCEL_WINDOW = 0.25s` | Looks for sudden pitch direction change |
| **Half-Flip** | Backward flip + cancel + yaw change > 143° | Within 0.6s of flip start | Requires flip cancel to be detected first |
| **Speedflip** | Diagonal flip + cancel within 0.2s | `SPEEDFLIP_CANCEL_WINDOW = 0.20s` | Tighter window than regular flip cancel |
| **Wavedash** | Flip within 0.4s of landing + sideways velocity | `WAVEDASH_LANDING_WINDOW = 0.4s` | Detected on landing after flip |
| **Aerial** | Height > 200 UU + jumped + airborne > 0.5s | Dedupe within 1.0s | Basic aerial classification |
| **Fast Aerial** | Jump + boost in 0.3s + 2nd jump in 0.5s + height > 300 UU in 1.0s | See detailed section | All conditions must be met |
| **Flip Reset** | Underside ball contact after flip used, then flip again | `DOT > 0.7`, dist < 120 UU | Only emits when reset flip is executed |
| **Air Roll** | Roll rate > 2 rad/s sustained > 0.3s while airborne | Excludes 0.2s after flip | Ends on landing or flip |
| **Dribble** | Ball in envelope on car roof for > 0.5s | See detailed section | Ground dribbles only (car z < 50) |
| **Flick** | Ball velocity gain > 500 UU/s during flip from dribble | `FLICK_DETECTION_WINDOW = 0.3s` | Must have been dribbling |
| **Musty Flick** | Backward flip from dribble + ball Z velocity gain > 800 UU/s | No speed gate required | Checked before regular flick |
| **Ceiling Shot** | Ceiling touch (z > 1900) then ball touch within 3.0s | Must leave ceiling first | Cleared on landing |
| **Power Slide** | Sideways velocity > 500 UU/s while grounded for > 0.2s | Car must be on ground | Duration tracked |
| **Ground Pinch** | Ball near ground + velocity gain > 1500 UU/s + exit speed > 3000 UU/s | Ball z < 100 UU | Requires both delta AND exit speed |
| **Double Touch** | Two aerial touches (> 300 UU) with wall bounce between, within 3.0s | `TOUCH_DEBOUNCE = 0.1s` | Wall = ball within 200 UU of wall |
| **Redirect** | Aerial touch that changes ball direction > 45° toward opponent goal | Ball speed > 500 UU/s | Uses velocity vectors, not position |
| **Stall** | High roll + yaw rate, opposite signs, near-zero velocity, height > 300 | Duration > 0.15s | Tornado spin / air stall |

---

## Detailed Detection Logic

### Jump / Double Jump / Flip

```
IF airborne AND z_velocity_increase > 292 UU/s AND time_since_ground > 0.1s:
    IF rotation_rate > 5 rad/s:
        → FLIP (also counts preceding JUMP if first jump)
    ELSE:
        IF first jump not used:
            → JUMP
        ELIF double jump not used AND no flip:
            → DOUBLE_JUMP
```

**Player Review Questions:**
- Is 292 UU/s the right threshold for jump detection?
- Should rotation rate threshold (5 rad/s) be different?

---

### Fast Aerial

**Detection:**
```
1. First jump detected → record timestamp, boost amount
2. Track boost usage; mark boost_used_in_window if boost used within 0.3s
3. Second jump/flip detected within 0.5s of first jump
4. Height > 300 UU reached within 1.0s of first jump
5. All conditions met → emit FAST_AERIAL
```

**Thresholds:**
| Constant | Value | Purpose |
|----------|-------|---------|
| `FAST_AERIAL_BOOST_WINDOW` | 0.3s | Boost must be used within this time of first jump |
| `FAST_AERIAL_SECOND_JUMP_WINDOW` | 0.5s | Second jump must occur within this time |
| `FAST_AERIAL_HEIGHT_THRESHOLD` | 300 UU | Must reach this height |
| `FAST_AERIAL_TIME_TO_HEIGHT` | 1.0s | Must reach height within this time |

**Player Review Questions:**
- Is 0.3s boost window too tight? Too loose?
- Is 300 UU height threshold appropriate?
- Should we track boost AMOUNT used, not just "any boost"?

---

### Flip Reset

**Detection:**
```
1. Player is airborne AND has used their flip (has_flipped = True)
2. Ball is within 120 UU of car
3. Car's up vector · ball-to-car vector > 0.7 (ball is under car)
4. → Set flip_available_from_reset = True, record touch time
5. If player flips while flip_available_from_reset = True:
   → Emit FLIP_RESET (timestamped at the touch, not the flip)
6. Reset expires after 2.0s if not used
```

**Thresholds:**
| Constant | Value | Purpose |
|----------|-------|---------|
| `FLIP_RESET_PROXIMITY` | 120 UU | Ball must be within this distance |
| `FLIP_RESET_DOT_THRESHOLD` | 0.7 | Dot product for "ball under car" |
| `FLIP_RESET_WINDOW` | 2.0s | Reset expires if not used |

**Player Review Questions:**
- Is 120 UU proximity correct? (Ball radius ~93 + car hitbox margin)
- Is 0.7 dot threshold too strict? Too loose?
- Should we detect the touch even if they don't use it?

---

### Dribble

**Detection:**
```
1. Car is grounded (z < 50 UU)
2. Ball is above car: 90 < ball_z - car_z < 180 UU
3. Ball is centered: XY distance < 100 UU
4. Ball-car relative velocity < 300 UU/s
5. All conditions sustained for > 0.5s
   → Emit DRIBBLE on end (when ball leaves envelope)
```

**Thresholds:**
| Constant | Value | Purpose |
|----------|-------|---------|
| `DRIBBLE_XY_RADIUS` | 100 UU | Max horizontal offset |
| `DRIBBLE_Z_MIN` | 90 UU | Min ball height above car |
| `DRIBBLE_Z_MAX` | 180 UU | Max ball height above car |
| `DRIBBLE_CAR_HEIGHT_MAX` | 50 UU | Car must be grounded |
| `DRIBBLE_RELATIVE_VELOCITY_MAX` | 300 UU/s | Max ball-car speed diff |
| `DRIBBLE_MIN_DURATION` | 0.5s | Minimum dribble time |

**Player Review Questions:**
- Is 100 UU XY radius too generous? (Ball can be on side of car?)
- Are Z thresholds correct for ball on roof?
- Is 300 UU/s relative velocity reasonable?
- **Known limitation:** Uses world-space coordinates, not car-local

---

### Flick / Musty Flick

**Detection:**
```
1. Player was dribbling (is_dribbling flag was True)
2. Player flips
3. Within 0.3s of flip, check ball velocity change:

   IF flip_direction == "backward" AND ball_z_velocity_gain > 800 UU/s:
       → MUSTY_FLICK (no speed gate!)
   ELIF ball_speed_gain > 500 UU/s:
       → FLICK
```

**Thresholds:**
| Constant | Value | Purpose |
|----------|-------|---------|
| `FLICK_VELOCITY_GAIN` | 500 UU/s | Min ball speed gain for regular flick |
| `FLICK_DETECTION_WINDOW` | 0.3s | Window after flip to check |
| `MUSTY_FLICK_Z_VELOCITY_GAIN` | 800 UU/s | Min ball Z velocity gain for musty |

**Player Review Questions:**
- Is 500 UU/s speed gain threshold correct for flicks?
- Is 800 UU/s Z velocity gain correct for musty?
- Should musty detection also check ball trajectory angle?

---

### Ceiling Shot

**Detection:**
```
1. Player touches ceiling (z > 1900 UU) → record last_ceiling_touch_time
2. Player falls away from ceiling (not on ceiling anymore)
3. Player touches ball within 3.0s while airborne
   → Emit CEILING_SHOT
4. Cleared on landing
```

**Thresholds:**
| Constant | Value | Purpose |
|----------|-------|---------|
| `CEILING_HEIGHT_THRESHOLD` | 1900 UU | Height to count as "ceiling" |
| `CEILING_SHOT_WINDOW` | 3.0s | Max time from ceiling to ball touch |

**Player Review Questions:**
- Is 1900 UU the correct ceiling height?
- Is 3.0s window too long? Too short?
- Should this require a specific type of play (shot on goal)?

---

### Power Slide

**Detection:**
```
1. Player is on ground
2. Sideways velocity > 500 UU/s (velocity perpendicular to facing direction)
3. Sustained for > 0.2s
   → Emit POWER_SLIDE on end
```

**Thresholds:**
| Constant | Value | Purpose |
|----------|-------|---------|
| `POWER_SLIDE_VELOCITY_THRESHOLD` | 500 UU/s | Min sideways velocity |
| `POWER_SLIDE_MIN_DURATION` | 0.2s | Min duration |

**Player Review Questions:**
- Is 500 UU/s the right threshold for meaningful power slides?
- Is 0.2s duration too short? (Would catch incidental slides?)

---

### Ground Pinch

**Detection:**
```
1. Ball is near ground (z < 100 UU)
2. Player touches ball (distance < 200 UU)
3. Ball exit velocity > 3000 UU/s
4. Ball velocity GAIN > 1500 UU/s (delta from prev frame)
   → Emit GROUND_PINCH
```

**Thresholds:**
| Constant | Value | Purpose |
|----------|-------|---------|
| `GROUND_PINCH_HEIGHT_MAX` | 100 UU | Ball must be near ground |
| `GROUND_PINCH_EXIT_VELOCITY_MIN` | 3000 UU/s | Min post-touch speed |
| `GROUND_PINCH_VELOCITY_DELTA_MIN` | 1500 UU/s | Min velocity gain |

**Player Review Questions:**
- Is 3000 UU/s exit velocity correct for a "pinch"?
- Is 1500 UU/s delta reasonable?
- Should this distinguish intentional pinches from lucky bounces?

---

### Double Touch

**Detection:**
```
1. Player is airborne at height > 300 UU
2. Player touches ball (with 0.1s debounce between touches)
3. Ball goes near wall (within 200 UU of back wall or side wall)
4. Player touches ball again within 3.0s
   → Emit DOUBLE_TOUCH
```

**Thresholds:**
| Constant | Value | Purpose |
|----------|-------|---------|
| `DOUBLE_TOUCH_WINDOW` | 3.0s | Max time between touches |
| `DOUBLE_TOUCH_HEIGHT_MIN` | 300 UU | Min height for aerial touches |
| `WALL_PROXIMITY` | 200 UU | Distance from wall to count as "wall bounce" |
| `TOUCH_DEBOUNCE_TIME` | 0.1s | Min time between distinct touches |

**Player Review Questions:**
- Is 300 UU height correct? Should it be lower/higher?
- **Known limitation:** Only checks ball POSITION near wall, not actual bounce
- Is 3.0s window too long?

---

### Redirect

**Detection:**
```
1. Player is airborne at height > 300 UU
2. Player touches ball (distance < 200 UU)
3. Ball speed > 500 UU/s
4. Ball direction changes > 45° (using velocity vectors)
5. New direction is toward opponent goal
   → Emit REDIRECT
```

**Thresholds:**
| Constant | Value | Purpose |
|----------|-------|---------|
| `REDIRECT_HEIGHT_MIN` | 300 UU | Min height |
| `REDIRECT_ANGLE_THRESHOLD` | 0.785 rad (45°) | Min direction change |
| `REDIRECT_MIN_BALL_SPEED` | 500 UU/s | Min ball speed |

**Player Review Questions:**
- Is 45° the right angle threshold?
- Should redirects require a certain ball speed BEFORE touch?
- Is the "toward opponent goal" check correct?

---

### Stall (Tornado Spin)

**Detection:**
```
1. Player is airborne at height > 300 UU
2. Roll rate > 3 rad/s AND yaw rate > 2 rad/s
3. Roll and yaw rates have OPPOSITE signs
4. Vertical velocity < 100 UU/s (near hover)
5. Horizontal velocity < 500 UU/s
6. Sustained for > 0.15s
   → Emit STALL
```

**Thresholds:**
| Constant | Value | Purpose |
|----------|-------|---------|
| `STALL_ROLL_RATE_MIN` | 3.0 rad/s | Min roll rate |
| `STALL_YAW_RATE_MIN` | 2.0 rad/s | Min yaw rate |
| `STALL_VERTICAL_VELOCITY_MAX` | 100 UU/s | Max vertical velocity |
| `STALL_HORIZONTAL_VELOCITY_MAX` | 500 UU/s | Max horizontal velocity |
| `STALL_HEIGHT_MIN` | 300 UU | Min height |
| `STALL_MIN_DURATION` | 0.15s | Min duration |

**Player Review Questions:**
- Are these rotation rates correct for a stall?
- Is 0.15s duration too short to be meaningful?
- Should stalls be linked to flip resets (stall → reset)?

---

### Air Roll

**Detection:**
```
1. Player is airborne
2. Roll rate > 2 rad/s (after excluding 0.2s flip rotation window)
3. Sustained for > 0.3s
   → Emit AIR_ROLL on end (with duration)
```

**Thresholds:**
| Constant | Value | Purpose |
|----------|-------|---------|
| `AIR_ROLL_RATE_THRESHOLD` | 2.0 rad/s | Min roll rate |
| `AIR_ROLL_MIN_DURATION` | 0.3s | Min duration |
| `AIR_ROLL_FLIP_EXCLUSION_WINDOW` | 0.2s | Skip detection after flip |

**Player Review Questions:**
- Is 2 rad/s the right threshold?
- Should we distinguish air roll left/right?
- Should we track continuous air roll vs tapped air roll?

---

## Known Limitations

1. **Dribble uses world-space coordinates** - May not work on slopes/ramps
2. **Wall bounce detection is position-based** - Doesn't verify actual velocity reversal
3. **No wall/air dribble detection** - Only ground dribbles (car z < 50)
4. **Flip direction is inferred** - Based on velocity + rotation, not input

---

## Field Constants Reference

| Constant | Value | Notes |
|----------|-------|-------|
| `FIELD.BACK_WALL_Y` | 5120 UU | |
| `FIELD.SIDE_WALL_X` | 4096 UU | |
| `FIELD.CEILING_Z` | ~2044 UU | |
| Ball radius | ~93 UU | |
| Car height | ~17 UU (ground level) | |

---

*Please review each section and flag any thresholds or logic that don't match your experience as a player!*

---

## Proposed Changes Based on Player Feedback

### 1. Speedflip - Tighten Cancel Window

**Current:** Cancel within 200ms of flip
**Problem:** Real speedflips require canceling within 100ms - that's what makes them hard

**Proposed Fix:**
```
SPEEDFLIP_CANCEL_WINDOW = 0.10  # 100ms, not 200ms
```

---

### 2. Wavedash - Remove Sideways Velocity Requirement

**Current:** Requires sideways velocity > 500 UU/s
**Problem:** Wavedashes can be in ANY direction - forward, backward, diagonal, sideways

**Proposed Fix:**
A wavedash is fundamentally:
1. Leave ground (jump or drive off surface)
2. Flip toward ground while still low
3. Land while flip animation is still active
4. Get speed boost from landing

Detection logic:
```
1. Player flips while airborne at low height (< 100 UU?)
2. Player lands within ~0.4s of flip start
3. Flip was angled downward (toward ground)
4. On landing, player has momentum (any direction)
→ WAVEDASH
```

Key insight: The flip must be oriented so wheels hit ground during flip animation. Remove the sideways velocity gate entirely.

---

### 3. Fast Aerial - Require Simultaneous Boost + Jump

**Current:** Boost used "within 0.3s" of jump, second jump within 0.5s
**Problem:** A TRUE fast aerial requires:
- Boost held DURING first jump (simultaneous input)
- Boost STILL held during second jump/double jump
- No boost = not a fast aerial, period

**Proposed Fix:**
```
Detection:
1. First jump detected
2. Check: was boost ACTIVE on the same frame as jump? (not "within 0.3s")
3. Second jump/flip detected
4. Check: was boost ACTIVE on the same frame as second jump?
5. If both jumps had simultaneous boost → FAST_AERIAL

Need to track:
- player.boost_active (is boost being used THIS frame, not just amount)
- Check boost_active == True on jump frames
```

This is much stricter - requires the actual simultaneous input pattern.

---

### 4. Musty Flick - Simplify, Remove Dribble Requirement

**Current:** Requires dribble state → backflip → Z velocity gain
**Problem:** Mustys can happen ANYWHERE:
- Ground dribble
- Ceiling shot
- Flip reset in air
- Off sidewall
- Off backwall
- 50/50
- Any hit where you'd normally flip

Core of a musty: **backflip that accelerates the ball**

**Proposed Fix:**
```
Detection:
1. Player does a backflip (flip_direction == "backward")
2. Player is near ball (contact proximity)
3. Ball velocity increases after contact
→ MUSTY_FLICK

Remove:
- Dribble state requirement
- Z velocity specific check (any acceleration counts)
- Ground-only restriction
```

The "full musty" vs "fast musty" distinction doesn't matter for detection - both are backflips that accelerate the ball.

---

### 5. Ceiling Shot - Flip-Based, Not Timer-Based

**Current:** Ceiling touch → ball touch within 3.0s
**Problem:** The real definition is:
- Touch ceiling with all 4 wheels (grants flip)
- Use that flip BEFORE all 4 wheels touch any surface again

**Proposed Fix:**
```
Detection:
1. Player touches ceiling (all 4 wheels, z > 1900)
   → Set has_ceiling_flip = True
2. Track: has player's 4 wheels touched ANY surface since?
3. If player uses flip while has_ceiling_flip == True:
   → CEILING_SHOT
4. Reset has_ceiling_flip when all 4 wheels touch any surface

Remove:
- 3.0s timer (irrelevant)
- Ball touch requirement? (or keep it - ceiling shot should involve the ball)
```

Question: Should ceiling shot require a ball touch, or just using the ceiling flip? I'd say require ball touch for it to be a "shot".

---

### 6. NEW: Skim

**Definition:** Ball is travelling toward opponent goal. Player in air touches ball with underside of car, accelerating it significantly.

**Why it works:** The underside touch at the right angle transfers momentum efficiently (physics magic).

**Proposed Detection:**
```
1. Ball is travelling toward opponent goal (velocity.y in goal direction)
2. Player is airborne
3. Player contacts ball with underside of car:
   - Same dot product check as flip reset (car_up · ball_to_car > 0.7)
   - Distance < proximity threshold
4. Ball velocity INCREASES after contact (not just direction change)
5. Player did NOT get a flip reset from this (distinguishes skim from reset)
→ SKIM

Thresholds to determine:
- Minimum ball velocity increase for "skim" vs normal touch
- Maybe require ball already moving fast (> 1000 UU/s?) before touch
```

Key difference from flip reset: skim is about accelerating the ball, not getting your flip back.

---

### 7. NEW: Psycho

**Definition:** The ultimate combo mechanic:
1. Ball heading toward your own backboard
2. Intentionally hit ball HARDER into your own backboard
3. Flip upside down
4. Skim touch the ball back toward opponent goal

**Proposed Detection:**
```
1. Ball is heading toward player's OWN goal (defensive situation)
2. Player hits ball, ball goes into own backboard
   - Ball velocity toward own goal INCREASES (intentional slam)
3. Player flips/rotates to get upside down
4. Player skim touches ball (underside contact)
5. Ball now heading toward OPPONENT goal
→ PSYCHO

This is a combo detection:
- Backboard read (intentional)
- + Flip to invert
- + Skim touch
- + Direction reversal toward opponent goal

All within a short window (~2-3 seconds?)
```

This is complex because it's really 3-4 mechanics chained:
1. Intentional backboard hit (ball speeds up into own wall)
2. Inversion (flip upside down)
3. Skim (underside ball contact)
4. Redirect toward opponent goal

Could potentially detect as: `BACKBOARD_READ` + `SKIM` in sequence = `PSYCHO`

---

## Implementation Priority

| Change | Difficulty | Impact |
|--------|------------|--------|
| Speedflip window (100ms) | Easy | High - current detection is too loose |
| Musty simplification | Easy | High - removes false negatives |
| Wavedash any-direction | Medium | Medium - current misses forward/back wavedashes |
| Ceiling shot flip-based | Medium | High - more accurate to real mechanic |
| Fast aerial simultaneous | Hard | High - need frame-level boost state |
| Skim (new) | Medium | Fun - advanced mechanic |
| Psycho (new) | Hard | Fun - ultimate flex detection |

---

## Questions for You

1. **Fast Aerial boost check:** Do replays even have frame-by-frame boost input data? Or just boost amount? If only amount, we might need to infer "simultaneous" from boost delta on the jump frame.

2. **Skim velocity threshold:** How much faster does the ball go after a good skim? 500 UU/s gain? 1000? Need to distinguish from regular touches.

3. **Psycho timing:** How long does a psycho typically take from backboard hit to skim? 1-2 seconds? Need a reasonable window.

4. **Ceiling shot + ball:** Should ceiling shot require ball contact, or just using the ceiling-granted flip? (I lean toward requiring ball touch for it to be a "shot")

5. **Wavedash height:** What's the max height for a wavedash flip? 50 UU? 100 UU? Need to distinguish from regular aerial flips.

---

## Expert Technical Review - Structural Improvements

*Based on detailed feedback from an experienced RL physics/replay analyst*

### Two Fundamental Problems We Need to Fix

#### Problem 1: World-Z Detection Breaks on Non-Flat Surfaces

**Current:** We detect jumps via `z_velocity_increase > 292 UU/s`

**Problem:** This only works when car is upright on flat ground. It will fail for:
- Jumps off walls and ramps (car's "up" ≠ world +Z)
- Aerial situations where car is tilted (fast aerials, preflips)
- Wavedashes and awkward recoveries

**The Fix:** RL's jump impulse is ~292 UU/s applied in the **car's local up direction**, not world Z.

```
# Instead of:
z_vel_increase = vel.z - prev_vel.z
if z_vel_increase > 292: # WRONG for walls/tilted cars

# Do:
car_up = rotation_to_up_vector(car.rotation)
delta_v = vel - prev_vel
impulse_in_car_up = dot(delta_v, car_up)
if impulse_in_car_up > 260:  # Slightly lower to account for gravity/timing
```

**Refactor Principle:** Anytime we use `ball_z - car_z` or `z_velocity_increase`, consider a car-local transform first.

#### Problem 2: Thresholds Near Hard Caps = Brittle Detection

**Current:** `rotation_rate > 5 rad/s` to detect flip

**Problem:** RL's max angular velocity is ~5.5 rad/s. We're saying "only call it a flip when angular velocity is almost maxed."

This causes:
- **False negatives:** Early cancels, light diagonal flips, shorter spikes
- **False positives:** Air roll or existing spin can hit 5 rad/s without being a flip

**The Fix:** Combine two smaller signals instead of one big threshold:
1. A second-jump event (distinct impulse or state transition consuming dodge)
2. A sudden change in angular velocity aligned with dodge axis

---

### Tick-Based Thinking

RL physics runs at **120 Hz**. Map everything to ticks for deterministic debugging:

| Seconds | Ticks |
|---------|-------|
| 0.05s | 6 ticks |
| 0.10s | 12 ticks |
| 0.15s | 18 ticks |
| 0.20s | 24 ticks |
| 0.25s | 30 ticks |
| 0.40s | 48 ticks |
| 0.50s | 60 ticks |
| 1.00s | 120 ticks |

---

### Per-Mechanic Technical Fixes

#### Jump / Double Jump / Flip

**Current issue:** World-Z based, rotation threshold too high

**Fixes:**
1. Replace `z_velocity_increase > 292` with `dot(Δv, car_up) > ~260` (tunable for gravity/sticky force)
2. Make flip vs double-jump depend on **dodge-style angular impulse**, not total rotation magnitude
   - Dodge signature: sharp step in |ω| plus axis alignment
   - Pitch-heavy = front/back flip
   - Yaw-heavy = side flip
3. The `time_since_ground > 0.1s` gate is suspicious - clarify if it's "since wheels left" or "must have been grounded recently"

#### Flip Cancel

**Current issue:** Single-frame reversal can trigger; missing "uncancel" handling

**Fixes:**
1. Define cancel relative to **flip's pitch intent**, not just "reversal"
   - Infer flip's pitch sign at flip start (front flip = positive, back flip = negative)
   - Require pitch angular velocity to become opposite sign OR fall below threshold while other axis continues
2. Add **persistence requirement** to prevent uncancel:
   - `cancel_detected_at` = first tick meeting criteria
   - `cancel_confirmed` only if criteria persists for ≥12-18 ticks (~0.1-0.15s)
3. Keep 0.25s max window for "did they attempt," add persistence for "did they get it"

#### Half-Flip

**Current issue:** Brittle with diagonal half-flips; players use air roll more than yaw

**Fixes:**
1. Require car ends **wheels-down-ish** shortly after:
   - Roll near 0 (mod 2π)
   - Pitch near 0
   - `dot(car_up, world_up) > threshold`
2. Change yaw requirement from ">143°" to "approaches 180° within tolerance"
3. Allow air-roll-driven yaw: measure **net heading reversal** via `dot(forward_vector, initial_forward) < -0.8`

#### Speedflip

**Current issue:** Will overcount diagonal flip cancels that aren't speedflips

**Additional signals to distinguish real speedflips:**
- Pre-flip forward speed threshold (already moving fast)
- Boost usage near the flip (reuse fast aerial boost tracking)
- Small yaw deviation at flip start (car isn't turning hard)
- Net forward acceleration spike immediately after cancel

**Window:** Trey confirmed 100ms (12 ticks) is correct for cancel timing.

#### Wavedash

**Current issue:** 0.4s window is huge (48 ticks); catches normal "landed then flipped"

**Fixes:**
1. Require wheels-grounded transition within **6-15 ticks (0.05-0.125s)** - much tighter
2. Require car pitch/roll at flip time indicates "dash" setup
3. Require noticeable **speed gain in car's forward direction** after
4. Remove sideways velocity requirement (Trey confirmed wavedashes work in any direction)

#### Fast Aerial

**Current issue:** Second jump window too permissive; should require simultaneous boost

**Fixes (per Trey's feedback):**
1. Boost must be **active on same frame** as first jump
2. Boost must be **active on same frame** as second jump
3. Consider jump-hold effects (holding first jump extends jump behavior)
4. Track boost sustained, not just "boost touched"

**Need to check:** Does replay data have frame-by-frame boost input, or just boost amount?

#### Flip Reset

**Current issue:** Only emits when they use the reset; distance/dot thresholds may need tuning

**Fixes:**
1. Emit **two events**:
   - `FLIP_RESET_TOUCH` at acquisition time
   - `FLIP_RESET_USE` if they spend it
2. Distance threshold: Ball radius is 91.25 UU. 120 UU center-to-center may be tight depending on what "car position" represents
3. Dot threshold 0.7 (~45°) is reasonable, but consider **speed-dependent thresholds** - high-speed resets can have less perfect alignment

#### Dribble

**Current issue:** XY < 100 is generous when ball radius is 91.25; world-space coords

**Fixes:**
1. Transform ball position to **car-local coordinates**
2. Use **oval footprint** (tighter side-to-side than front-to-back)
3. Add "ball relative vertical velocity small" condition (bouncy carries don't count)

#### Flick / Musty

**Current issue:** Musty requires dribble (wrong per Trey); needs ball-touch verification

**Fixes (per Trey):**
1. Remove dribble requirement for musty - can happen anywhere
2. Core of musty: **backflip + ball acceleration**
3. For classic musty, could optionally check: ball is behind car in car-local coords at flip start
4. For both: require the ball-touch happens in the detection window (velocity gain from opponent touch doesn't count)

#### Ceiling Shot

**Current issue:** 1900 UU threshold is way below actual ceiling (2044 UU)

**Fixes:**
1. Raise `CEILING_HEIGHT_THRESHOLD` closer to 2044 UU
2. Add "car is actually on ceiling" logic:
   - Vertical velocity near 0
   - Position stays near ceiling for multiple ticks
   - Orientation consistent with ceiling contact
3. Per Trey: Require using the **ceiling-granted flip** before 4 wheels touch any surface
4. Require ball contact for it to be a "shot"

#### Power Slide

**Current issue:** Detects "sliding/drifting" not specifically powerslide input

**Options:**
1. Rename to "Drift" or "High Slip Angle" (defensible without input data)
2. If keeping "Power Slide" label, add **yaw rate gating** so straight sideways bumps don't count

#### Ground Pinch

**Current issue:** Could confuse "hard clear off bounce" with intentional pinch

**Fixes:**
1. Require pre-touch ball is moving **downward or near-stationary**
2. Require post-touch ball launches with **strong upward component**

#### Double Touch

**Current issue:** Position-near-wall ≠ actual bounce

**Fixes:**
1. Detect bounce as **velocity component reversal** relative to wall normal:
   - Near back wall (y=±5120): require `sign(v_y)` flips from toward-wall to away-from-wall
   - Near side wall (x=±4096): require `sign(v_x)` flips
2. Tighten 3.0s window (current catches air dribbles with eventual second touch)

#### Redirect

**Current issue:** Will classify many normal aerial shots as redirects

**Fixes:**
1. Require ball's **incoming direction was not already strongly goalward**
2. Optionally require a teammate touched recently (pass context)
3. Optionally require touch point is in front of goal box region
4. Or: relabel to "Aerial Re-direction" and embrace broader meaning

#### Stall

**Current issue:** This is really a "tornado spin / near-hover" detector

**Options:**
1. Keep as "Stall" but tie to flip attempt that produces minimal translational impulse
2. Or relabel as "Tornado Spin" (more accurate without input data)

#### Air Roll

**Current issue:** Misses tiny DAR (directional air roll) taps; 0.2s flip exclusion may be too short

**Fixes:**
1. Keep current detector as `AIR_ROLL_HELD`
2. Add `AIR_ROLL_TAP`: lower duration (3-8 ticks), slightly higher roll-rate threshold
3. Replace fixed 0.2s flip exclusion with "exclude while in flip state" (dodge angular velocity can persist longer, especially with cancels)

---

### New Mechanics: Skim & Psycho

#### Skim (per Trey's definition)

**Core:** Underside touch on ball → ball accelerates AND redirects toward opponent goal

```
Detection:
1. Player is airborne
2. Ball is moving (any direction, any speed)
3. Player contacts ball with underside:
   - dot(car_up, ball_to_car) > 0.7
   - distance < proximity threshold
4. Ball velocity increases (any amount)
5. Ball trajectory changes toward opponent goal
6. NOT a flip reset (distinguishes skim from reset)
→ SKIM
```

**Note:** Don't require ball to already be moving toward goal - skim can redirect it goalward.

#### Psycho (per Trey's definition)

**Core:** Intentional backboard slam → flip upside down → skim redirect

```
Detection (combo mechanic, ~3 second window):
1. Ball heading toward player's OWN goal
2. Player hits ball INTO own backboard (ball velocity toward own goal INCREASES)
3. Player rotates/flips to get upside down
4. Player skim touches ball (underside contact)
5. Ball now heading toward OPPONENT goal
→ PSYCHO
```

Could implement as: `BACKBOARD_SLAM` + `SKIM` in sequence = `PSYCHO`

---

### Confidence Scoring (Future Improvement)

Instead of hard boolean gates, compute scores:

```python
cancel_score = f(cancel_latency, cancel_hold_duration, pitch_sign_consistency)
speedflip_score = f(diagonalness, cancel_latency, post_flip_forward_accel, yaw_deviation)
```

Set conservative thresholds for "emit mechanic" while logging "near misses" for tuning. Avoids rewriting everything when watching new replays.

---

### Corrected Constants

| Constant | Our Value | Correct Value | Source |
|----------|-----------|---------------|--------|
| Ceiling Z | ~2044 | 2044 | RLBot |
| Ball radius | ~93 | 91.25 UU | RLBot |
| Max angular velocity | - | ~5.5 rad/s | RLBot |
| Physics tick rate | - | 120 Hz | RLBot |

---

### Priority: What to Fix First

The expert recommends: **Rewrite Jump/DoubleJump/Flip to be car-local and tick-based first.**

Half our mechanics sit on top of those events. Once those primitives are rock solid, everything else becomes tuning.

---

## Final Technical Reality Check

*Critical sampling and input constraints that affect everything above*

### Reality #1: Replay Sample Rate is 30 Hz, Not 120 Hz

**The physics engine runs at 120 Hz, but saved replays are recorded at 30 Hz.**

This means:
| Time Window | Physics Ticks | **Replay Frames** |
|-------------|---------------|-------------------|
| 50ms | 6 ticks | **1.5 frames** |
| 100ms | 12 ticks | **3 frames** |
| 150ms | 18 ticks | **4.5 frames** |
| 200ms | 24 ticks | **6 frames** |

**Implications:**
- "12 ticks = 100ms" is true in the physics engine, but we only see **3 frames** in that window
- "50ms vs 100ms" distinctions should be treated as **buckets**, not razors
- Persistence checks like "confirm for 12-18 ticks" become "confirm for ~3-5 replay frames"
- We may undercount fast events due to sampling

**Example:** Speedflip cancel detection
- Physics reality: cancel must happen within ~100ms (12 ticks)
- Replay reality: we see ~3 frames, so score in buckets (great/ok/late), not exact timing

### Reality #2: Limited Input Data in Replays

**Replays do NOT contain full controller state.**

Available in .replay files:
- ✅ Throttle
- ✅ Steer
- ✅ Handbrake
- ✅ Jump
- ✅ Boost

**NOT available (must be inferred from physics):**
- ❌ Pitch input
- ❌ Yaw input
- ❌ Roll input (air roll left/right)
- ❌ Exact stick diagonals

**Implications:**
- Any detector that assumes "air roll held" as an input → must use angular velocity/orientation change instead
- "Stick diagonal" for speedflip → must infer from flip direction + angular impulse pattern
- Air roll TAP detection → must be based on short roll-rate bursts, not button state

### Reality #3: Car-Local Vectors Everywhere

World-Z gates fail the moment you're on a wall, ramp, or weird landing. **Always transform to car-local coordinates.**

---

## Per-Mechanic Final Refinements

### Jump / Double Jump / Flip - Final Tweaks

**Gravity/sticky-force awareness:**
- RL gravity: ~650 UU/s²
- Sticky force: ~325 UU/s² (briefly after surface contact)
- The `dot(Δv, car_up) > 260` threshold should account for these

**Flip vs double-jump discrimination:**
- Detect step-change in angular velocity + axis dominance (pitch vs yaw)
- Do NOT require anywhere near 5.5 rad/s - that misses early cancels and messy diagonals
- Lower threshold + axis check is more robust

**Ground gate:**
- Define in terms of contact transitions, not raw time
- RL jump timing effects are measured in frames, not tenths of seconds

### Flip Cancel - Final Tweaks

**30 Hz sampling adjustment:**
- "Confirm for 12-18 ticks" → "confirm for ~3-5 replay frames"
- Express persistence as frames with tolerance band
- Otherwise you'll undercount cancels just from sampling

### Speedflip - Final Tweaks

**Bucket scoring instead of razor thresholds:**
```python
speedflip_score = (
    cancel_latency_bucket(great=0, ok=1, late=2) +
    heading_deviation_bucket(...) +
    post_cancel_forward_accel_bucket(...) +  # Best discriminator!
    boost_active_bucket(...)
)
```

**The "net forward acceleration spike after cancel" is secretly the best discriminator** - it's the closest thing to ground truth that doesn't depend on input inference.

### Wavedash - Final Tweaks

**Require wheel-contact transition event:**
- Not just "is grounded" but "airborne→grounded transition occurred in window"
- Prevents "I was already on ground and flipped" from counting

### Fast Aerial - Final Tweaks

**Sampling tolerance for "same frame":**
- Implement as "same frame OR adjacent frame" (±1 replay frame)
- 30 Hz sampling means exact frame alignment is noisy

**Boost detection:**
- Boost button IS available in replays per research
- If parser exposes it, use directly
- If not, use boost-amount delta BUT guard against pad pickups (check for large positive jumps)

### Ceiling Shot - Final Tweaks

**Persistence for ceiling contact:**
- Use multiple frames near ceiling before asserting contact
- Not just single-threshold crossing
- 30 Hz means exact "ceiling contact ended" moment is noisy

### Skim - Final Tweaks

**Vector definition clarity (avoid sign mistakes):**
```python
# Instead of: dot(car_up, ball_to_car) > 0.7
# Use:
car_to_ball = ball_pos - car_pos
underside_contact = dot(car_up, car_to_ball) < -0.7  # Ball is in direction of car's DOWN
```
Same math, fewer sign mistakes.

**Flip reset is ORTHOGONAL to skim (per Trey):**
- Do NOT exclude skims that also trigger flip reset
- Many skim-like redirects will incidentally trigger reset if wheels land cleanly
- Options:
  1. Tag as `SKIM + RESET` (both events)
  2. Or just detect them independently - they're separate mechanics

### Psycho - Final Tweaks

**Use goal direction vectors, not raw Y sign:**
```python
# "Ball toward own goal" and "toward opponent goal"
goal_direction = get_opponent_goal_direction(player_team)
ball_toward_goal = dot(ball_velocity, goal_direction) > threshold
```
This survives side-of-field weirdness.

**Require actual wall bounce for "backboard slam":**
- Wall-bounce sign flip near back wall
- PLUS player touch within tight window
- Otherwise misclassifies random clears and ricochets

---

## Implementation Checklist

### Foundation (Do First)
- [ ] Implement car-local vector transforms everywhere
- [ ] Add `rotation_to_up_vector()`, `rotation_to_forward_vector()` helpers
- [ ] Refactor jump detection to use `dot(Δv, car_up)` instead of world-Z
- [ ] Add flip discrimination via angular impulse axis, not raw magnitude threshold

### Core Fixes
- [ ] Speedflip: 100ms window (but treat as ~3 frame bucket)
- [ ] Wavedash: Remove sideways requirement, add grounded-transition check
- [ ] Fast Aerial: Same-frame boost check with ±1 frame tolerance
- [ ] Ceiling Shot: Raise threshold to ~2040 UU, add persistence check
- [ ] Flip Cancel: Add persistence (3-5 frames), relative to flip intent

### Mechanic Refinements
- [ ] Musty: Remove dribble requirement, backflip + ball acceleration anywhere
- [ ] Dribble: Transform to car-local, oval footprint
- [ ] Double Touch: Velocity sign-flip for bounce detection
- [ ] Flip Reset: Split into TOUCH and USE events

### New Mechanics
- [ ] Skim: Underside contact + ball acceleration + toward goal (orthogonal to flip reset)
- [ ] Psycho: State machine BACKBOARD_SLAM → INVERTED → SKIM

### Future Improvements
- [ ] Confidence scoring for edge cases
- [ ] Air Roll TAP vs HELD distinction
- [ ] Speed-dependent thresholds for flip reset

---

## 30 Hz Sampling: Threshold Calibration Analysis

**Critical insight: Our thresholds were derived from 120 Hz physics specs, but we sample at 30 Hz.**

### The Math Problem

```
Jump impulse: 292 UU/s (instantaneous in physics)
Gravity: -650 UU/s²
Frame interval at 30 Hz: 33ms
Velocity lost per frame: 650 × 0.033 = 21.5 UU/s

If we sample 1 frame after impulse: we see 270 UU/s, not 292
If we sample 2 frames after: we see 249 UU/s
```

**Our threshold of 292 UU/s means we only detect jumps if we happen to sample on the exact impulse frame.** We're missing jumps due to timing luck.

### Current Thresholds vs Reality

| Threshold | Current | Problem | Recommended |
|-----------|---------|---------|-------------|
| `JUMP_Z_VELOCITY_THRESHOLD` | 292.0 | Exact physics value; misses post-gravity samples | **250.0** |
| `FLIP_ANGULAR_THRESHOLD` | 5.0 | 91% of max (5.5); misses decayed samples | **3.5** |
| `SPEEDFLIP_CANCEL_WINDOW` | 0.20s | Only 6 frames; treat as bucket | **≤6 frames bucket** |

### What This Means for Detection

| Category | Impact |
|----------|--------|
| **Broken (false negatives)** | Jump detection, flip detection - thresholds too tight |
| **Noisy but working** | Flip cancel timing, fast aerial "simultaneous" boost (±33ms precision) |
| **Fine** | Position-based (dribble, ceiling), duration-based (air roll), frame-to-frame deltas |

### The Fix

1. **Loosen physics-derived thresholds by 15-20%** to account for 1-2 frames of decay
2. **Stop claiming sub-frame timing precision** - we have ±33ms at best
3. **Use bucket scoring for timing** - not razor thresholds
4. **Accept probabilistic detection** for fast events (impulses, cancels)

---

## Constants Reference (Corrected)

| Constant | Value | Source |
|----------|-------|--------|
| Ceiling Z | 2044 UU | RLBot |
| Ball radius | 91.25 UU | RLBot |
| Max angular velocity | ~5.5 rad/s | RLBot |
| Physics tick rate | 120 Hz | RLBot |
| **Replay sample rate** | **30 Hz** | Reality |
| Jump impulse | ~292 UU/s (car-up) | RLBot |
| Gravity | ~650 UU/s² | RLBot |
| Sticky force | ~325 UU/s² | RLBot |
| Side wall X | ±4096 UU | RLBot |
| Back wall Y | ±5120 UU | RLBot |

---

## Summary: What We're Building

### Foundation Changes (Do First)
1. Car-local vector transforms everywhere
2. Lower `JUMP_Z_VELOCITY_THRESHOLD` from 292 → 250
3. Lower `FLIP_ANGULAR_THRESHOLD` from 5.0 → 3.5
4. Refactor jump/flip to use `dot(Δv, car_up)` instead of world-Z

### Core Mechanic Fixes
- **Speedflip:** 100ms window, bucket scoring, forward-accel discriminator
- **Wavedash:** Remove sideways requirement, require grounded-transition
- **Fast Aerial:** Same-frame boost (±1 frame tolerance)
- **Ceiling Shot:** Raise to 2040 UU, flip-based not timer-based
- **Flip Cancel:** Persistence (3-5 frames), relative to flip intent
- **Musty:** Remove dribble requirement - backflip + ball acceleration anywhere
- **Double Touch:** Velocity sign-flip for bounce detection

### New Mechanics
- **Skim:** Underside contact + ball acceleration + toward goal (orthogonal to flip reset)
- **Psycho:** State machine BACKBOARD_SLAM → INVERTED → SKIM (3s window)

### Reality Constraints
- 30 Hz sampling = ±33ms timing precision
- No pitch/yaw/roll inputs = must infer from physics
- Thresholds need 15-20% headroom below physics maximums
