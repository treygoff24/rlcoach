"""Detection thresholds and constants for event detection.

All numeric constants used by event detectors are centralized here
for easy tuning and documentation.
"""

from __future__ import annotations

from ..field_constants import FIELD, Vec3
from .types import PadEnvelope

# =============================================================================
# Goal Detection
# =============================================================================
GOAL_LINE_THRESHOLD = FIELD.BACK_WALL_Y - FIELD.GOAL_DEPTH  # Front plane of goal
GOAL_EXIT_THRESHOLD = GOAL_LINE_THRESHOLD - 200.0
GOAL_LOOKBACK_WINDOW_S = 1.0  # Look back up to 1 second before goal frame
MIN_SHOT_VELOCITY_UU_S = 500.0  # Minimum velocity to consider as valid shot speed

# =============================================================================
# Demo Detection
# =============================================================================
DEMO_POSITION_TOLERANCE = 500.0  # Max distance for demo attacker detection (units)

# =============================================================================
# Touch Detection
# =============================================================================
TOUCH_PROXIMITY_THRESHOLD = 200.0  # Distance for player-ball contact (units)
TOUCH_DEBOUNCE_TIME = 0.2  # seconds
TOUCH_LOCATION_EPS = 120.0  # uu
MIN_BALL_SPEED_FOR_TOUCH = 120.0  # uu/s
MIN_RELATIVE_SPEED_FOR_TOUCH = 180.0  # uu/s

# Touch context thresholds
WALL_PROXIMITY_THRESHOLD = 150.0  # Distance from wall to consider wall touch
CEILING_HEIGHT_THRESHOLD = 1900.0  # Height to consider ceiling touch
AERIAL_HEIGHT_THRESHOLD = 300.0  # Height to consider aerial touch
HALF_VOLLEY_HEIGHT = 100.0  # Height for half volley detection

# =============================================================================
# Boost Pickup Detection
# =============================================================================
BOOST_PICKUP_MIN_GAIN = 1.0  # Minimum net gain to record a pickup event
BOOST_HISTORY_WINDOW_S = 0.45
BOOST_HISTORY_MAX_SAMPLES = 18
BIG_PAD_EXTRA_RADIUS = 220.0
SMALL_PAD_EXTRA_RADIUS = 140.0
BIG_PAD_RESPAWN_S = 10.0
SMALL_PAD_RESPAWN_S = 4.0
PAD_RESPAWN_TOLERANCE = 0.15
BOOST_PICKUP_MERGE_WINDOW = 0.6
DEBUG_BOOST_ENV = "RLCOACH_DEBUG_BOOST_EVENTS"
BIG_PAD_MIN_GAIN = 70.0
RESPAWN_BOOST_AMOUNT = 33.0
RESPAWN_DISTANCE_THRESHOLD = 800.0
CHAIN_PAD_RADIUS = 1500.0

# Pad neutral zone
CENTERLINE_TOLERANCE = 1200.0  # Within this Y range is considered neutral half
PAD_NEUTRAL_TOLERANCE = 1200.0

# =============================================================================
# Kickoff Detection
# =============================================================================
BALL_STATIONARY_THRESHOLD = 50.0  # Ball speed for kickoff detection (units/s)
KICKOFF_CENTER_POSITION = Vec3(0.0, 0.0, 93.15)
KICKOFF_POSITION_TOLERANCE = 120.0
KICKOFF_MAX_DURATION = 5.0
KICKOFF_MIN_COOLDOWN = 5.0
MIN_ORIENTATION_SAMPLES = 5

# Kickoff approach type keys
APPROACH_TYPE_KEYS = [
    "SPEEDFLIP",
    "STANDARD_FRONTFLIP",
    "STANDARD_DIAGONAL",
    "STANDARD_WAVEDASH",
    "STANDARD_BOOST",
    "DELAY",
    "FAKE_STATIONARY",
    "FAKE_HALFFLIP",
    "FAKE_AGGRESSIVE",
    "STANDARD",  # Generic fallback
    "UNKNOWN",
]

# =============================================================================
# Challenge Detection
# =============================================================================
CHALLENGE_WINDOW_S = 1.2
CHALLENGE_RADIUS_UU = 1000.0
CHALLENGE_MIN_DISTANCE_UU = 200.0
CHALLENGE_MIN_BALL_SPEED_KPH = 15.0
NEUTRAL_RETOUCH_WINDOW_S = 0.25

# Challenge risk calculation weights
RISK_LOW_BOOST_THRESHOLD = 20
RISK_AHEAD_OF_BALL_WEIGHT = 0.4
RISK_LOW_BOOST_WEIGHT = 0.3
RISK_LAST_MAN_WEIGHT = 0.3

# =============================================================================
# Precomputed Pad Envelopes
# =============================================================================
PAD_ENVELOPES: dict[int, PadEnvelope] = {}
for _pad in FIELD.BOOST_PADS:
    _base_radius = _pad.radius + (BIG_PAD_EXTRA_RADIUS if _pad.is_big else SMALL_PAD_EXTRA_RADIUS)
    _height_tol = 220.0 if _pad.is_big else 150.0
    _max_distance = _base_radius + (650.0 if _pad.is_big else 420.0)
    PAD_ENVELOPES[_pad.pad_id] = PadEnvelope(
        radius=_base_radius, max_distance=_max_distance, height_tolerance=_height_tol
    )
