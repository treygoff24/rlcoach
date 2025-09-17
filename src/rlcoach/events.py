"""Event detection and timeline aggregation for Rocket League replays.

This module identifies significant game events from normalized frame data:
- Goals: Ball crossing goal line with scorer attribution
- Demos: Player demolition events with attacker tracking
- Kickoffs: Match start and overtime kickoff detection
- Boost pickups: Player boost collection with pad classification
- Touches: Player-ball contact events with outcome classification

All detection uses deterministic thresholds and graceful degradation.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from .field_constants import FIELD, Vec3
from .parser.types import Header, Frame, PlayerFrame, BallFrame


# Detection thresholds - explicitly documented
GOAL_LINE_THRESHOLD = FIELD.BACK_WALL_Y * 0.99  # 5069 units from center
BALL_STATIONARY_THRESHOLD = 50.0  # Ball speed for kickoff detection (units/s)
TOUCH_PROXIMITY_THRESHOLD = 200.0  # Distance for player-ball contact (units)
BOOST_PAD_PROXIMITY_THRESHOLD = 150.0  # Distance to match boost pad pickup (units)
DEMO_POSITION_TOLERANCE = 500.0  # Max distance for demo attacker detection (units)


@dataclass(frozen=True)
class GoalEvent:
    """Goal event with scorer and shot metrics."""
    
    t: float  # Timestamp from match start
    frame: int | None = None
    scorer: str | None = None  # Player ID who scored
    team: str | None = None  # "BLUE" or "ORANGE"
    assist: str | None = None  # Player ID with assist
    shot_speed_kph: float = 0.0
    distance_m: float = 0.0
    on_target: bool = True
    tickmark_lead_seconds: float = 0.0


@dataclass(frozen=True)
class DemoEvent:
    """Demolition event with victim and attacker."""
    
    t: float
    victim: str
    attacker: str | None = None
    team_attacker: str | None = None  # "BLUE" or "ORANGE"
    team_victim: str | None = None
    location: Vec3 | None = None


@dataclass(frozen=True)  
class KickoffEvent:
    """Kickoff event with player analysis."""
    
    phase: str  # "INITIAL" or "OT"
    t_start: float
    players: list[dict[str, Any]]  # Player kickoff analysis
    outcome: str = "NEUTRAL"  # Simplified outcome


@dataclass(frozen=True)
class BoostPickupEvent:
    """Boost pad pickup event."""
    
    t: float
    player_id: str
    pad_type: str  # "SMALL" or "BIG"
    stolen: bool = False  # True if on opponent half
    pad_id: int = -1  # Index in boost pad arrays
    location: Vec3 | None = None
    frame: int | None = None


@dataclass(frozen=True)
class TouchEvent:
    """Player-ball contact event."""
    
    t: float
    player_id: str
    location: Vec3
    frame: int | None = None
    ball_speed_kph: float = 0.0
    outcome: str = "NEUTRAL"  # Simplified classification


@dataclass(frozen=True)
class TimelineEvent:
    """Timeline entry for chronological event aggregation."""
    
    t: float
    type: str  # Event type from schema enum
    frame: int | None = None
    player_id: str | None = None
    team: str | None = None
    data: dict[str, Any] | None = None


def detect_goals(frames: list[Frame], header: Header | None = None) -> list[GoalEvent]:
    """Detect goal events from ball position crossing goal lines.
    
    Args:
        frames: Normalized frame data
        header: Optional header for team score validation
        
    Returns:
        List of detected goal events
    """
    if not frames:
        return []
    
    goals = []
    last_touch_by_player = {}  # Track last player to touch ball
    last_touch_times = {}
    
    for i, frame in enumerate(frames):
        ball_y = frame.ball.position.y
        
        # Update last touch tracking (only if ball hasn't crossed goal line yet)
        if abs(ball_y) <= GOAL_LINE_THRESHOLD:
            for player in frame.players:
                # Simple proximity check for ball contact
                distance = _distance_3d(player.position, frame.ball.position)
                if distance < TOUCH_PROXIMITY_THRESHOLD:
                    last_touch_by_player[player.player_id] = player
                    last_touch_times[player.player_id] = frame.timestamp
        
        # Check for goal line crossing
        if abs(ball_y) > GOAL_LINE_THRESHOLD:
            # Determine scoring team based on ball Y position
            if ball_y > 0:
                # Ball in orange goal, blue team scored
                team = "BLUE"
            else:
                # Ball in blue goal, orange team scored  
                team = "ORANGE"
            
            # Find scorer and potential assist from recent touches
            scorer = None
            assist = None
            if last_touch_by_player:
                # Get most recent touch within last 5 seconds
                recent_touches = [
                    (pid, last_touch_times.get(pid, 0.0))
                    for pid in last_touch_by_player.keys()
                    if frame.timestamp - last_touch_times.get(pid, 0.0) < 5.0
                ]
                if recent_touches:
                    # Sort by most recent touch time
                    recent_touches.sort(key=lambda x: x[1], reverse=True)
                    scorer = recent_touches[0][0]
                    # Assist is second most recent by a different player
                    for pid, _t in recent_touches[1:]:
                        if pid != scorer:
                            assist = pid
                            break
            
            # Calculate shot speed from ball velocity
            ball_speed = _vector_magnitude(frame.ball.velocity)
            shot_speed_kph = ball_speed * 3.6  # Convert to km/h
            
            # Calculate distance (simplified)
            goal_line_y = GOAL_LINE_THRESHOLD if ball_y > 0 else -GOAL_LINE_THRESHOLD
            distance_m = abs(ball_y - goal_line_y) / 100.0  # Convert to meters
            
            scorer_id = scorer if scorer is not None else f"{team}_UNKNOWN_SCORER"

            goal = GoalEvent(
                t=frame.timestamp,
                frame=i,
                scorer=scorer_id,
                team=team,
                assist=assist,
                shot_speed_kph=shot_speed_kph,
                distance_m=distance_m,
                on_target=True
            )
            goals.append(goal)
            
            # Clear touch tracking after goal
            last_touch_by_player.clear()
            last_touch_times.clear()
    
    return goals


def detect_demos(frames: list[Frame]) -> list[DemoEvent]:
    """Detect demolition events from player state transitions.
    
    Args:
        frames: Normalized frame data
        
    Returns:
        List of detected demo events
    """
    if not frames:
        return []
    
    demos = []
    previous_demo_states = {}  # Track player demolition states
    
    for i, frame in enumerate(frames):
        for player in frame.players:
            player_id = player.player_id
            was_demolished = previous_demo_states.get(player_id, False)
            is_demolished = player.is_demolished
            
            # Detect demolition state transition (False -> True)
            if not was_demolished and is_demolished:
                # Find potential attacker - nearest enemy player
                attacker = None
                attacker_team = None
                min_distance = float('inf')
                
                for other_player in frame.players:
                    if (other_player.player_id != player_id and 
                        other_player.team != player.team and
                        not other_player.is_demolished):
                        
                        distance = _distance_3d(player.position, other_player.position)
                        if distance < DEMO_POSITION_TOLERANCE and distance < min_distance:
                            min_distance = distance
                            attacker = other_player.player_id
                            attacker_team = "BLUE" if other_player.team == 0 else "ORANGE"
                
                victim_team = "BLUE" if player.team == 0 else "ORANGE"
                
                demo = DemoEvent(
                    t=frame.timestamp,
                    victim=player_id,
                    attacker=attacker,
                    team_attacker=attacker_team,
                    team_victim=victim_team,
                    location=player.position
                )
                demos.append(demo)
            
            # Update state tracking
            previous_demo_states[player_id] = is_demolished
    
    return demos


def detect_kickoffs(frames: list[Frame], header: Header | None = None) -> list[KickoffEvent]:
    """Detect kickoff events from ball position and game state.
    
    Args:
        frames: Normalized frame data
        header: Optional header for match context
        
    Returns:
        List of detected kickoff events
    """
    if not frames:
        return []
    
    kickoffs = []
    in_kickoff = False
    kickoff_start_time = 0.0
    
    for i, frame in enumerate(frames):
        ball = frame.ball
        
        # Check if ball is at center and stationary (kickoff position)
        at_center = (
            abs(ball.position.x) < 100.0 and 
            abs(ball.position.y) < 100.0 and
            abs(ball.position.z - 93.15) < 50.0  # Ball spawn height
        )
        
        ball_speed = _vector_magnitude(ball.velocity)
        is_stationary = ball_speed < BALL_STATIONARY_THRESHOLD
        
        # Detect kickoff start
        if at_center and is_stationary and not in_kickoff:
            in_kickoff = True
            kickoff_start_time = frame.timestamp
        
        # Detect kickoff end (ball moves significantly)
        elif in_kickoff and (not at_center or ball_speed > BALL_STATIONARY_THRESHOLD * 2):
            # Determine phase (simplified - assume initial unless very late)
            phase = "OT" if frame.timestamp > 300.0 else "INITIAL"
            
            # Simple player analysis - just record positions
            player_analysis = []
            for player in frame.players:
                # Basic role detection from starting position
                distance_to_center = _distance_3d(
                    player.position, 
                    Vec3(0.0, 0.0, 17.0)
                )
                
                if distance_to_center < 1000.0:
                    role = "GO"  # Close to center
                else:
                    role = "BACK"  # Further away
                
                player_analysis.append({
                    "player_id": player.player_id,
                    "role": role,
                    "boost_used": 0.0,  # Would need frame-by-frame tracking
                    "approach_type": "UNKNOWN",
                    "time_to_first_touch": None
                })
            
            kickoff = KickoffEvent(
                phase=phase,
                t_start=kickoff_start_time,
                players=player_analysis,
                outcome="NEUTRAL"
            )
            kickoffs.append(kickoff)
            in_kickoff = False
    
    return kickoffs


def detect_boost_pickups(frames: list[Frame]) -> list[BoostPickupEvent]:
    """Detect boost pickup events from player boost amount increases.
    
    Args:
        frames: Normalized frame data
        
    Returns:
        List of detected boost pickup events
    """
    if not frames:
        return []
    
    pickups = []
    previous_boost_amounts = {}
    
    for i, frame in enumerate(frames):
        for player in frame.players:
            player_id = player.player_id
            current_boost = player.boost_amount
            previous_boost = previous_boost_amounts.get(player_id, current_boost)
            
            # Detect boost increase
            boost_increase = current_boost - previous_boost
            if boost_increase > 0:
                # Determine pad type from boost increase
                if boost_increase >= 80:  # Large pad (100 boost minus tolerance for rounding)
                    pad_type = "BIG"
                    boost_positions = FIELD.CORNER_BOOST_POSITIONS
                elif boost_increase >= 10:  # Small pad (12 boost minus tolerance)
                    pad_type = "SMALL"
                    boost_positions = FIELD.SMALL_BOOST_POSITIONS
                else:
                    # Ignore small incremental increases
                    previous_boost_amounts[player_id] = current_boost
                    continue
                
                # Find nearest boost pad
                nearest_pad_id = -1
                nearest_distance = float('inf')
                nearest_location = player.position
                
                for pad_id, pad_pos in enumerate(boost_positions):
                    distance = _distance_3d(player.position, pad_pos)
                    if distance < BOOST_PAD_PROXIMITY_THRESHOLD and distance < nearest_distance:
                        nearest_distance = distance
                        nearest_pad_id = pad_id
                        nearest_location = pad_pos
                
                # Determine if stolen (simplified - check field half)
                is_stolen = False
                if player.team == 0:  # Blue team
                    is_stolen = player.position.y > 1000.0  # In orange half
                elif player.team == 1:  # Orange team
                    is_stolen = player.position.y < -1000.0  # In blue half
                
                pickup = BoostPickupEvent(
                    t=frame.timestamp,
                    player_id=player_id,
                    pad_type=pad_type,
                    stolen=is_stolen,
                    pad_id=nearest_pad_id,
                    location=nearest_location,
                    frame=i,
                )
                pickups.append(pickup)
            
            previous_boost_amounts[player_id] = current_boost
    
    return pickups


def detect_touches(frames: list[Frame]) -> list[TouchEvent]:
    """Detect player-ball contact events.
    
    Args:
        frames: Normalized frame data
        
    Returns:
        List of detected touch events
    """
    if not frames:
        return []
    
    touches = []
    
    for i, frame in enumerate(frames):
        ball_speed = _vector_magnitude(frame.ball.velocity)
        
        for player in frame.players:
            # Check proximity to ball
            distance = _distance_3d(player.position, frame.ball.position)
            
            if distance < TOUCH_PROXIMITY_THRESHOLD:
                # Simple outcome classification based on ball speed change
                outcome = "NEUTRAL"
                if ball_speed > 1500.0:  # High speed
                    outcome = "SHOT"
                elif ball_speed > 800.0:  # Medium speed
                    outcome = "PASS"
                elif ball_speed < 200.0:  # Low speed
                    outcome = "DRIBBLE"
                
                touch = TouchEvent(
                    t=frame.timestamp,
                    frame=i,
                    player_id=player.player_id,
                    location=player.position,
                    ball_speed_kph=ball_speed * 3.6,
                    outcome=outcome
                )
                touches.append(touch)
    
    return touches


def build_timeline(events_dict: dict[str, list[Any]]) -> list[TimelineEvent]:
    """Build chronological timeline from all detected events.
    
    Args:
        events_dict: Dictionary of event type -> event list
        
    Returns:
        Sorted list of timeline events
    """
    timeline = []
    
    # Convert each event type to timeline entries
    for goals in events_dict.get('goals', []):
        timeline.append(TimelineEvent(
            t=goals.t,
            frame=goals.frame,
            type="GOAL",
            player_id=goals.scorer,
            team=goals.team,
            data={
                "shot_speed_kph": goals.shot_speed_kph,
                "distance_m": goals.distance_m,
                "assist": goals.assist
            }
        ))
    
    for demo in events_dict.get('demos', []):
        timeline.append(TimelineEvent(
            t=demo.t,
            type="DEMO",
            player_id=demo.victim,
            team=demo.team_victim,
            data={
                "attacker": demo.attacker,
                "location": demo.location
            }
        ))
    
    for kickoff in events_dict.get('kickoffs', []):
        timeline.append(TimelineEvent(
            t=kickoff.t_start,
            type="KICKOFF",
            data={
                "phase": kickoff.phase,
                "players": kickoff.players,
                "outcome": kickoff.outcome
            }
        ))
    
    for pickup in events_dict.get('boost_pickups', []):
        timeline.append(TimelineEvent(
            t=pickup.t,
            type="BOOST_PICKUP",
            player_id=pickup.player_id,
            data={
                "pad_type": pickup.pad_type,
                "stolen": pickup.stolen,
                "location": pickup.location
            }
        ))
    
    for touch in events_dict.get('touches', []):
        timeline.append(TimelineEvent(
            t=touch.t,
            frame=touch.frame,
            type="TOUCH",
            player_id=touch.player_id,
            data={
                "location": touch.location,
                "ball_speed_kph": touch.ball_speed_kph,
                "outcome": touch.outcome
            }
        ))
    
    # Sort chronologically, then by type for stable ordering
    timeline.sort(key=lambda e: (e.t, e.type))
    
    return timeline


def _distance_3d(pos1: Vec3, pos2: Vec3) -> float:
    """Calculate 3D Euclidean distance between two positions."""
    dx = pos1.x - pos2.x
    dy = pos1.y - pos2.y
    dz = pos1.z - pos2.z
    return math.sqrt(dx*dx + dy*dy + dz*dz)


def _vector_magnitude(vec: Vec3) -> float:
    """Calculate magnitude of a 3D vector."""
    return math.sqrt(vec.x*vec.x + vec.y*vec.y + vec.z*vec.z)
