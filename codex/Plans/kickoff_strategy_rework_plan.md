# Kickoff Strategy Detection Rework Plan

## Problem Statement

The current `_classify_approach_type()` function in `events.py:1505` has fundamentally flawed heuristics:

1. **SPEEDFLIP** - Uses arbitrary 0.45s threshold without validation
2. **DELAY** - Misunderstands what a delay kickoff is (movement delay vs brake timing)
3. **FAKE** - Too simplistic; doesn't account for diagonal half-flip fakes or aggressive fakes
4. **STANDARD** - Just checks if boost was used; doesn't distinguish flip types

## Strategy Definitions (Ground Truth)

| Strategy | Description | Key Signatures |
|----------|-------------|----------------|
| **SPEEDFLIP** | Diagonal flip with immediate flip cancel + air roll to reach ball fastest | Fast first touch (~2.4-2.6s from diagonal), high boost usage, flip cancel detected |
| **STANDARD_FRONTFLIP** | Front flip toward ball | Forward flip detected, no flip cancel, moderate speed |
| **STANDARD_DIAGONAL** | Diagonal flip without cancel (no air roll recovery) | Diagonal flip detected, no flip cancel |
| **STANDARD_WAVEDASH** | Wavedash kickoff approach | Wavedash mechanic detected during kickoff window |
| **STANDARD_BOOST** | Hold boost, no flip, drive straight at ball | No flip detected, high boost usage, continuous forward movement |
| **DELAY** | Normal approach but brake right before 50/50 | Speed profile shows deceleration spike near ball contact |
| **FAKE** | Don't contest the ball at all | Never reaches ball proximity OR moves away from ball |
| **CHEAT** | Second player pushes up to steal possession | Role is CHEAT and gets first/second touch |

## Data Collection Requirements

### Current Data (in `_update_kickoff_state`)
- `start_pos`, `last_pos` - positions
- `start_boost`, `min_boost` - boost tracking
- `movement_start_time` - when player moved 150+ units
- `max_distance` - max distance from start
- `first_touch_time` - time to first ball contact
- `role` - GO/CHEAT/WING/BACK

### New Data Needed
```python
# Per-player kickoff tracking additions:
{
    # Velocity tracking
    "velocities": [],           # List of (t, speed) tuples
    "max_speed": 0.0,           # Peak speed during kickoff
    "speed_at_contact": 0.0,    # Speed when touching ball (for delay detection)

    # Position trajectory
    "positions": [],            # List of (t, Vec3) for path analysis
    "distance_to_ball_min": float('inf'),  # Closest approach to ball
    "reached_ball": False,      # Did player get within contact range?

    # Mechanics during kickoff window
    "flips": [],                # List of flip events with direction
    "flip_cancels": [],         # Flip cancel detections
    "wavedashes": [],           # Wavedash events
    "jumped": False,            # Did player jump?

    # Directional movement
    "moved_toward_ball": bool,  # Net movement toward ball center
    "moved_away_from_ball": bool,  # Moved backward (fake indicator)
}
```

## Implementation Plan

### Phase 1: Enhanced Data Collection

**File:** `events.py`

1. Modify `_start_kickoff()` to initialize new tracking fields
2. Modify `_update_kickoff_state()` to collect:
   - Velocity samples (magnitude)
   - Position trajectory
   - Minimum distance to ball
   - Direction of movement relative to ball

3. Add mechanics integration:
   - Call `detect_mechanics_for_player()` on kickoff frames subset
   - Or inline lighter-weight flip/cancel detection for kickoff window only

### Phase 2: Speedflip Detection

**Key insight:** Speedflip is characterized by:
- Diagonal flip with immediate flip cancel
- Air roll to recover car orientation
- Results in fastest possible time to ball

**Validation approach:**
- Run pipeline on pro replays
- Extract first touch times for diagonal spawns
- Speedflips from diagonal should be ~2.4-2.6s
- Non-speedflip approaches should be noticeably slower (~2.8-3.2s)

**Heuristics:**
```python
def _is_speedflip(pdata: dict, mechanics: list[MechanicEvent]) -> bool:
    # Must have a flip
    flips = [m for m in mechanics if m.mechanic_type == MechanicType.FLIP]
    if not flips:
        return False

    first_flip = flips[0]

    # Flip must be diagonal
    if first_flip.direction != "diagonal":
        return False

    # Look for flip cancel (rapid pitch change reversal)
    flip_cancels = [m for m in mechanics if m.mechanic_type == MechanicType.FLIP_CANCEL]
    if not flip_cancels:
        return False

    # Flip cancel must occur shortly after flip start
    cancel_delay = flip_cancels[0].timestamp - first_flip.timestamp
    if cancel_delay > 0.3:  # Cancel should be almost immediate
        return False

    return True
```

**Threshold research task:**
- Extract first_touch_time from all kickoffs in pro replays
- Group by spawn position (diagonal vs corner vs back)
- Compare times for speedflip vs non-speedflip approaches
- Establish data-driven thresholds

### Phase 3: Delay Kickoff Detection

**Key insight:** Delay kickoff = normal approach + brake before contact

**Heuristics:**
```python
def _is_delay_kickoff(pdata: dict) -> bool:
    velocities = pdata.get("velocities", [])
    contact_time = pdata.get("first_touch_time")

    if not velocities or contact_time is None:
        return False

    # Find velocity profile near contact
    pre_contact_velocities = [
        (t, v) for t, v in velocities
        if contact_time - 0.5 < t < contact_time
    ]

    if len(pre_contact_velocities) < 3:
        return False

    # Look for deceleration spike: high speed followed by sudden drop
    max_speed = max(v for _, v in pre_contact_velocities)
    final_speed = pre_contact_velocities[-1][1]

    # Significant deceleration (>30% speed drop) near contact
    speed_drop = (max_speed - final_speed) / max(max_speed, 1)

    return speed_drop > 0.30 and max_speed > 1800  # Was going fast, then slowed
```

### Phase 4: Fake Kickoff Detection

**Types of fakes:**

1. **Stationary fake**: Don't move at all
2. **Half-flip fake**: Half-flip backward to grab corner boost
3. **Aggressive fake**: Drive toward where opponent will hit the ball

**Heuristics:**
```python
def _is_fake_kickoff(pdata: dict, kickoff_duration: float) -> tuple[bool, str]:
    reached_ball = pdata.get("reached_ball", False)
    max_distance = pdata.get("max_distance", 0)
    moved_away = pdata.get("moved_away_from_ball", False)
    boost_used = pdata["start_boost"] - pdata["min_boost"]

    # Type 1: Stationary fake
    if max_distance < 100 and boost_used < 5:
        return True, "FAKE_STATIONARY"

    # Type 2: Half-flip backward (common on diagonal)
    # Moved significant distance but AWAY from ball
    if moved_away and max_distance > 300:
        return True, "FAKE_HALFFLIP"

    # Type 3: Didn't reach ball proximity despite moving toward it
    # (went to intercept opponent's hit instead)
    if not reached_ball and max_distance > 500:
        # Check if they ended up near expected ball destination
        # This requires ball trajectory prediction - may simplify to:
        return True, "FAKE_AGGRESSIVE"

    return False, None
```

### Phase 5: Standard Kickoff Subtypes

**Subtypes:**
- `STANDARD_FRONTFLIP`: Forward flip detected
- `STANDARD_DIAGONAL`: Diagonal flip, no cancel
- `STANDARD_WAVEDASH`: Wavedash mechanic detected
- `STANDARD_BOOST`: No flip, high boost usage

**Heuristics:**
```python
def _classify_standard_kickoff(pdata: dict, mechanics: list[MechanicEvent]) -> str:
    flips = [m for m in mechanics if m.mechanic_type == MechanicType.FLIP]
    wavedashes = [m for m in mechanics if m.mechanic_type == MechanicType.WAVEDASH]

    if wavedashes:
        return "STANDARD_WAVEDASH"

    if not flips:
        # No flip = boost-only kickoff
        return "STANDARD_BOOST"

    first_flip = flips[0]

    if first_flip.direction == "forward":
        return "STANDARD_FRONTFLIP"
    elif first_flip.direction == "diagonal":
        return "STANDARD_DIAGONAL"
    elif first_flip.direction == "backward":
        # Backward flip during kickoff approach = likely fake or mistake
        return "STANDARD_BACKFLIP"  # Or reclassify as fake

    return "STANDARD"
```

### Phase 6: Updated Classification Function

```python
APPROACH_KEYS = [
    "SPEEDFLIP",
    "STANDARD_FRONTFLIP",
    "STANDARD_DIAGONAL",
    "STANDARD_WAVEDASH",
    "STANDARD_BOOST",
    "DELAY",
    "FAKE_STATIONARY",
    "FAKE_HALFFLIP",
    "FAKE_AGGRESSIVE",
    "UNKNOWN",
]

def _classify_approach_type(
    pdata: dict[str, Any],
    kickoff_start_time: float,
    kickoff_duration: float,
    mechanics: list[MechanicEvent] | None = None,
) -> str:
    """Classify kickoff approach type from movement, mechanics, and timing."""

    # Get mechanics for this player during kickoff window if not provided
    if mechanics is None:
        mechanics = []

    # 1. Check for fake first (didn't contest)
    is_fake, fake_type = _is_fake_kickoff(pdata, kickoff_duration)
    if is_fake:
        return fake_type

    # 2. Check for delay (contested but braked)
    if _is_delay_kickoff(pdata):
        return "DELAY"

    # 3. Check for speedflip
    if _is_speedflip(pdata, mechanics):
        return "SPEEDFLIP"

    # 4. Classify standard subtypes
    return _classify_standard_kickoff(pdata, mechanics)
```

## Schema Updates

**File:** `schemas/report.json` (if approach_types enum is defined)

Update `approach_types` enum:
```json
{
    "approach_types": {
        "type": "object",
        "properties": {
            "SPEEDFLIP": {"type": "integer"},
            "STANDARD_FRONTFLIP": {"type": "integer"},
            "STANDARD_DIAGONAL": {"type": "integer"},
            "STANDARD_WAVEDASH": {"type": "integer"},
            "STANDARD_BOOST": {"type": "integer"},
            "DELAY": {"type": "integer"},
            "FAKE_STATIONARY": {"type": "integer"},
            "FAKE_HALFFLIP": {"type": "integer"},
            "FAKE_AGGRESSIVE": {"type": "integer"},
            "UNKNOWN": {"type": "integer"}
        }
    }
}
```

**File:** `kickoffs.py`

Update `APPROACH_KEYS` to match new types.

## Validation Plan

### Step 1: Pro Replay Analysis
```bash
# Run pipeline on pro replays and examine kickoff data
source .venv/bin/activate
python -m rlcoach.cli analyze Replay_files/*.replay --adapter rust --out /tmp/pro_analysis --pretty
```

### Step 2: Extract Kickoff Metrics
- Write a script to extract all kickoff first_touch_times grouped by spawn position
- Analyze distribution to validate speedflip timing thresholds

### Step 3: Manual Verification
- For a few replays, manually watch kickoffs and verify detection accuracy
- Compare against ballchasing.com kickoff stats if available

## Test Updates

**File:** `tests/test_events.py` or `tests/analysis/test_kickoffs.py`

Add test cases:
- Speedflip detection with flip cancel
- Delay kickoff with deceleration spike
- Various fake types
- Standard subtype classification

Use synthetic frames from `tests/fixtures/builders.py` to construct controlled test scenarios.

## Migration Notes

- Old `APPROACH_KEYS` list is smaller; update `kickoffs.py:16` with new keys
- Reports using old keys will need schema version bump
- Consider backward compatibility: map old "STANDARD" to "STANDARD_FRONTFLIP" in migration

## Open Questions

1. **Flip cancel detection**: Does `mechanics.py` currently detect flip cancels? Need to verify or add.
2. **Spanish kickoff**: Not included yet. Requires detecting hook trajectory around ball. May add later.
3. **Diagonal spawn thresholds**: Need empirical data on time-to-touch for speedflip vs non-speedflip from diagonal.

---

## New Report Metrics: Mechanics Counts

In addition to kickoff strategy rework, we need to surface key mechanics as explicit per-player and per-team counts in the reports.

### Metrics to Add

| Metric | Description | Detection Source |
|--------|-------------|------------------|
| **wavedash_count** | Total wavedashes performed | `mechanics.py` already tracks this |
| **speedflip_count** | Total speedflips (not just kickoffs) | New - detect diagonal flip + cancel anywhere |
| **halfflip_count** | Total half-flips (backward flip + cancel to 180) | New - needs detection logic |

### Current State

**Wavedash**: Already detected in `mechanics.py:180-191` and `recovery.py:208-212`. Already exposed in `per_player` via:
- `mechanics_player["wavedash_count"]` (`analysis/__init__.py:185`)
- `recovery_player["wavedash_count"]` (`analysis/__init__.py:198`)

**Speedflip**: Only detected during kickoffs (poorly). Not tracked as a general mechanic.

**Half-flip**: Not currently detected anywhere.

### Implementation Plan

#### Phase 7: Half-flip Detection

**Definition**: A half-flip is:
1. Backward flip initiated
2. Immediate flip cancel (pull stick forward to stop rotation)
3. Air roll 180° to face forward
4. Results in quick 180° direction change

**Add to `mechanics.py`:**

```python
class MechanicType(Enum):
    # ... existing ...
    HALF_FLIP = "half_flip"
    SPEEDFLIP = "speedflip"  # General speedflip, not just kickoffs

def _detect_half_flip(
    flip_event: MechanicEvent,
    subsequent_frames: list[Frame],
    player_id: str,
) -> bool:
    """Detect if a backward flip was a half-flip."""
    if flip_event.direction != "backward":
        return False

    # Look for rapid yaw change (180° rotation) within ~0.5s of flip
    # Combined with flip cancel (pitch rate reversal)

    # Half-flip signature:
    # 1. Backward flip starts
    # 2. Within 0.2s, pitch rate reverses (cancel)
    # 3. Within 0.5s total, car yaw changes ~180°

    # Implementation requires tracking rotation through subsequent frames
    # ...
    return False  # Placeholder

def _detect_speedflip_general(
    flip_event: MechanicEvent,
    cancel_event: MechanicEvent | None,
) -> bool:
    """Detect speedflip outside of kickoff context."""
    if flip_event.direction != "diagonal":
        return False
    if cancel_event is None:
        return False

    # Cancel must be nearly immediate
    cancel_delay = cancel_event.timestamp - flip_event.timestamp
    return cancel_delay < 0.25
```

#### Phase 8: Update Mechanics Analysis Output

**File:** `mechanics.py`

Update `analyze_mechanics()` return structure:

```python
per_player[player_id] = {
    "jump_count": counts.get("jump", 0),
    "double_jump_count": counts.get("double_jump", 0),
    "flip_count": counts.get("flip", 0),
    "wavedash_count": counts.get("wavedash", 0),
    "aerial_count": counts.get("aerial", 0),
    "halfflip_count": counts.get("half_flip", 0),      # NEW
    "speedflip_count": counts.get("speedflip", 0),     # NEW
    "total_mechanics": sum(counts.values()),
}
```

#### Phase 9: Add Team-Level Aggregation

**File:** `analysis/__init__.py`

Currently mechanics are only per-player. Add team aggregation:

```python
def _analyze_team(...):
    # ... existing code ...

    # Aggregate mechanics for team
    team_mechanics = {
        "total_wavedashes": 0,
        "total_speedflips": 0,
        "total_halfflips": 0,
        "total_aerials": 0,
    }

    for player_id in team_player_ids:
        player_mech = cached_mechanics.get("per_player", {}).get(player_id, {})
        team_mechanics["total_wavedashes"] += player_mech.get("wavedash_count", 0)
        team_mechanics["total_speedflips"] += player_mech.get("speedflip_count", 0)
        team_mechanics["total_halfflips"] += player_mech.get("halfflip_count", 0)
        team_mechanics["total_aerials"] += player_mech.get("aerial_count", 0)

    return {
        # ... existing ...
        "mechanics": team_mechanics,
    }
```

#### Phase 10: Update Report Output

**File:** `report.py`

Ensure mechanics data flows through to final report structure. Currently `mechanics_player` is included in `complete_analysis` but may not be in the final serialized output. Verify and add if missing.

**File:** `report_markdown.py`

Add mechanics section to markdown dossier:

```markdown
### Mechanics

| Player | Wavedashes | Speedflips | Half-flips | Aerials |
|--------|------------|------------|------------|---------|
| Player1 | 5 | 3 | 2 | 8 |
| Player2 | 3 | 4 | 1 | 12 |

**Team Totals:**
- Blue: 8 wavedashes, 7 speedflips, 3 half-flips
- Orange: 6 wavedashes, 5 speedflips, 4 half-flips
```

### Schema Updates for Mechanics

**File:** `schemas/report.json`

Add to player analysis schema:
```json
{
    "mechanics": {
        "type": "object",
        "properties": {
            "jump_count": {"type": "integer"},
            "double_jump_count": {"type": "integer"},
            "flip_count": {"type": "integer"},
            "wavedash_count": {"type": "integer"},
            "halfflip_count": {"type": "integer"},
            "speedflip_count": {"type": "integer"},
            "aerial_count": {"type": "integer"},
            "total_mechanics": {"type": "integer"}
        }
    }
}
```

Add to team analysis schema:
```json
{
    "mechanics": {
        "type": "object",
        "properties": {
            "total_wavedashes": {"type": "integer"},
            "total_speedflips": {"type": "integer"},
            "total_halfflips": {"type": "integer"},
            "total_aerials": {"type": "integer"}
        }
    }
}
```

---

## Task Breakdown

### Kickoff Strategy Rework
1. [ ] Run pro replays through pipeline, extract kickoff timing data
2. [ ] Analyze timing data to establish speedflip thresholds
3. [ ] Add velocity tracking to `_update_kickoff_state()`
4. [ ] Add position trajectory tracking
5. [ ] Add "moved toward/away from ball" tracking
6. [ ] Integrate or inline flip detection during kickoff window
7. [ ] Implement `_is_speedflip()` with flip cancel check
8. [ ] Implement `_is_delay_kickoff()` with deceleration detection
9. [ ] Implement `_is_fake_kickoff()` with subtypes
10. [ ] Implement `_classify_standard_kickoff()` with subtypes
11. [ ] Rewrite `_classify_approach_type()` with new logic
12. [ ] Update `APPROACH_KEYS` in `kickoffs.py`

### Mechanics Metrics
13. [ ] Add `HALF_FLIP` and `SPEEDFLIP` to `MechanicType` enum
14. [ ] Implement `_detect_half_flip()` in `mechanics.py`
15. [ ] Implement `_detect_speedflip_general()` in `mechanics.py`
16. [ ] Update `detect_mechanics_for_player()` to detect new types
17. [ ] Update `analyze_mechanics()` return structure with new counts
18. [ ] Add team-level mechanics aggregation in `_analyze_team()`
19. [ ] Update `report_markdown.py` with mechanics table

### Finalization
20. [ ] Update JSON schema for new fields
21. [ ] Write/update unit tests for new mechanics detection
22. [ ] Write/update unit tests for kickoff strategies
23. [ ] Validate against pro replays
24. [ ] Update golden test fixtures
