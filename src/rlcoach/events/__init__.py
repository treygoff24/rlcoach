"""Event detection and timeline aggregation for Rocket League replays.

This package identifies significant game events from normalized frame data:
- Goals: Ball crossing goal line with scorer attribution
- Demos: Player demolition events with attacker tracking
- Kickoffs: Match start and overtime kickoff detection
- Boost pickups: Player boost collection with pad classification
- Touches: Player-ball contact events with outcome classification
- Challenges: 50/50 challenge detection with outcome

All detection uses deterministic thresholds and graceful degradation.

Example:
    from rlcoach.events import detect_goals, detect_touches, build_timeline

    goals = detect_goals(frames, header)
    touches = detect_touches(frames)
    timeline = build_timeline({
        'goals': goals,
        'touches': touches,
    })
"""

# Types - all event dataclasses and enums
from .types import (
    GoalEvent,
    DemoEvent,
    KickoffEvent,
    BoostPickupEvent,
    PadState,
    PadEnvelope,
    TouchContext,
    TouchEvent,
    ChallengeEvent,
    TimelineEvent,
)

# Constants - detection thresholds (exported for analyzer compatibility)
from .constants import (
    GOAL_LINE_THRESHOLD,
    GOAL_EXIT_THRESHOLD,
    TOUCH_PROXIMITY_THRESHOLD,
    DEMO_POSITION_TOLERANCE,
    BOOST_PICKUP_MIN_GAIN,
    BALL_STATIONARY_THRESHOLD,
    KICKOFF_CENTER_POSITION,
    KICKOFF_POSITION_TOLERANCE,
    KICKOFF_MAX_DURATION,
    KICKOFF_MIN_COOLDOWN,
    CHALLENGE_WINDOW_S,
    CHALLENGE_RADIUS_UU,
    CHALLENGE_MIN_DISTANCE_UU,
    CHALLENGE_MIN_BALL_SPEED_KPH,
    NEUTRAL_RETOUCH_WINDOW_S,
    PAD_ENVELOPES,
    CENTERLINE_TOLERANCE,
    PAD_NEUTRAL_TOLERANCE,
)

# Detector functions
from .goals import detect_goals
from .demos import detect_demos
from .kickoffs import detect_kickoffs
from .boost import detect_boost_pickups, determine_team_sides, _merge_pickup_events
from .touches import detect_touches
from .challenges import detect_challenge_events

# Timeline builder
from .timeline import build_timeline

# Utilities (exported for backward compatibility)
from .utils import (
    distance_3d as _distance_3d,
    vector_magnitude as _vector_magnitude,
    relative_speed as _relative_speed,
    team_name as _team_name,
)

__all__ = [
    # Event types
    "GoalEvent",
    "DemoEvent",
    "KickoffEvent",
    "BoostPickupEvent",
    "PadState",
    "PadEnvelope",
    "TouchContext",
    "TouchEvent",
    "ChallengeEvent",
    "TimelineEvent",
    # Detector functions
    "detect_goals",
    "detect_demos",
    "detect_kickoffs",
    "detect_boost_pickups",
    "detect_touches",
    "detect_challenge_events",
    "determine_team_sides",
    # Timeline
    "build_timeline",
    # Constants (commonly used externally)
    "GOAL_LINE_THRESHOLD",
    "TOUCH_PROXIMITY_THRESHOLD",
    "CHALLENGE_WINDOW_S",
    "CHALLENGE_RADIUS_UU",
    "PAD_ENVELOPES",
    # Private helpers (for backward compat with underscore prefix)
    "_distance_3d",
    "_vector_magnitude",
    "_relative_speed",
    "_team_name",
    "_merge_pickup_events",
]
