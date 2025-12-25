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
from .boost import _merge_pickup_events, detect_boost_pickups, determine_team_sides
from .challenges import detect_challenge_events

# Constants - detection thresholds (exported for analyzer compatibility)
from .constants import (
    BALL_STATIONARY_THRESHOLD,
    BOOST_PICKUP_MIN_GAIN,
    CENTERLINE_TOLERANCE,
    CHALLENGE_MIN_BALL_SPEED_KPH,
    CHALLENGE_MIN_DISTANCE_UU,
    CHALLENGE_RADIUS_UU,
    CHALLENGE_WINDOW_S,
    DEMO_POSITION_TOLERANCE,
    GOAL_EXIT_THRESHOLD,
    GOAL_LINE_THRESHOLD,
    KICKOFF_CENTER_POSITION,
    KICKOFF_MAX_DURATION,
    KICKOFF_MIN_COOLDOWN,
    KICKOFF_POSITION_TOLERANCE,
    NEUTRAL_RETOUCH_WINDOW_S,
    PAD_ENVELOPES,
    PAD_NEUTRAL_TOLERANCE,
    TOUCH_PROXIMITY_THRESHOLD,
)
from .demos import detect_demos

# Detector functions
from .goals import detect_goals
from .kickoffs import detect_kickoffs

# Timeline builder
from .timeline import build_timeline
from .touches import detect_touches
from .types import (
    BoostPickupEvent,
    ChallengeEvent,
    DemoEvent,
    GoalEvent,
    KickoffEvent,
    PadEnvelope,
    PadState,
    TimelineEvent,
    TouchContext,
    TouchEvent,
)

# Utilities (exported for backward compatibility)
from .utils import (
    distance_3d as _distance_3d,
)
from .utils import (
    relative_speed as _relative_speed,
)
from .utils import (
    team_name as _team_name,
)
from .utils import (
    vector_magnitude as _vector_magnitude,
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
    # Constants
    "GOAL_LINE_THRESHOLD",
    "GOAL_EXIT_THRESHOLD",
    "TOUCH_PROXIMITY_THRESHOLD",
    "DEMO_POSITION_TOLERANCE",
    "BOOST_PICKUP_MIN_GAIN",
    "BALL_STATIONARY_THRESHOLD",
    "KICKOFF_CENTER_POSITION",
    "KICKOFF_POSITION_TOLERANCE",
    "KICKOFF_MAX_DURATION",
    "KICKOFF_MIN_COOLDOWN",
    "CHALLENGE_WINDOW_S",
    "CHALLENGE_RADIUS_UU",
    "CHALLENGE_MIN_DISTANCE_UU",
    "CHALLENGE_MIN_BALL_SPEED_KPH",
    "NEUTRAL_RETOUCH_WINDOW_S",
    "PAD_ENVELOPES",
    "CENTERLINE_TOLERANCE",
    "PAD_NEUTRAL_TOLERANCE",
    # Private helpers (for backward compat with underscore prefix)
    "_distance_3d",
    "_vector_magnitude",
    "_relative_speed",
    "_team_name",
    "_merge_pickup_events",
]
