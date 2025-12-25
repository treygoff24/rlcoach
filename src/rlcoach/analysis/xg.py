"""Expected Goals (xG) model for shot quality assessment.

This module provides a simple but effective xG model based on:
- Distance from goal
- Angle to goal
- Ball speed
- Shot type (aerial, ground, wall)
- Defender positioning

The model uses logistic regression-style scoring with empirically tuned weights
based on Rocket League physics and common shot success rates.
"""

from __future__ import annotations

import bisect
import math
from dataclasses import dataclass
from enum import Enum

from ..events import TouchContext, TouchEvent
from ..field_constants import FIELD, Vec3
from ..parser.types import Frame, PlayerFrame


class ShotType(Enum):
    """Classification of shot type."""

    GROUND = "ground"
    AERIAL = "aerial"
    WALL = "wall"
    CEILING = "ceiling"
    REDIRECT = "redirect"  # Quick touch redirecting ball
    POWER_SHOT = "power_shot"  # High speed ground shot
    LOB = "lob"  # High arcing shot
    UNKNOWN = "unknown"


# Unit conversion constant: 1 UU ≈ 1.9 cm = 0.019 m
# To convert UU/s to km/h: multiply by 0.019 (m per UU) * 3.6 (s/h / m/km)
UU_S_TO_KPH = 0.019 * 3.6  # ≈ 0.0684


@dataclass(frozen=True)
class XGResult:
    """Result of xG calculation for a shot."""

    xg: float  # Expected goal probability (0.0 - 1.0)
    shot_type: ShotType
    distance_m: float  # Distance to goal in meters
    angle_degrees: float  # Angle to goal center
    ball_speed_kph: float
    is_open_net: bool  # No defenders between shot and goal
    defender_coverage: float  # 0.0 = open, 1.0 = fully covered
    factors: dict  # Breakdown of contributing factors


# Field constants for xG calculation
GOAL_CENTER_BLUE = Vec3(0.0, FIELD.BACK_WALL_Y, FIELD.GOAL_HEIGHT / 2)
GOAL_CENTER_ORANGE = Vec3(0.0, -FIELD.BACK_WALL_Y, FIELD.GOAL_HEIGHT / 2)
GOAL_WIDTH = FIELD.GOAL_WIDTH
GOAL_HEIGHT = FIELD.GOAL_HEIGHT


@dataclass
class XGConfig:
    """Configuration for xG model parameters.

    All parameters can be tuned to adjust the xG model behavior.
    Default values are empirically tuned for Rocket League.
    """

    # Distance parameters (in meters after UU conversion)
    optimal_distance_m: float = 15.0  # Distance where shots are most effective
    max_distance_penalty_m: float = 80.0  # Beyond this, xG drops significantly

    # Angle parameters (in degrees)
    optimal_angle: float = 0.0  # Direct angle to goal center
    max_angle_penalty: float = 60.0  # Beyond 60 degrees, very hard to score

    # Speed thresholds (in km/h after UU conversion)
    power_shot_speed_kph: float = 100.0
    optimal_shot_speed_kph: float = 70.0
    min_shot_speed_kph: float = 20.0

    # Base xG values by shot type
    base_xg_ground: float = 0.12
    base_xg_aerial: float = 0.08
    base_xg_wall: float = 0.06
    base_xg_ceiling: float = 0.04
    base_xg_redirect: float = 0.15
    base_xg_power_shot: float = 0.18
    base_xg_lob: float = 0.05
    base_xg_unknown: float = 0.08

    def get_base_xg(self, shot_type: ShotType) -> float:
        """Get base xG value for a shot type."""
        mapping = {
            ShotType.GROUND: self.base_xg_ground,
            ShotType.AERIAL: self.base_xg_aerial,
            ShotType.WALL: self.base_xg_wall,
            ShotType.CEILING: self.base_xg_ceiling,
            ShotType.REDIRECT: self.base_xg_redirect,
            ShotType.POWER_SHOT: self.base_xg_power_shot,
            ShotType.LOB: self.base_xg_lob,
            ShotType.UNKNOWN: self.base_xg_unknown,
        }
        return mapping.get(shot_type, self.base_xg_unknown)


# Default configuration instance
DEFAULT_XG_CONFIG = XGConfig()

# Legacy constants for backwards compatibility
OPTIMAL_DISTANCE_M = DEFAULT_XG_CONFIG.optimal_distance_m
MAX_DISTANCE_PENALTY_M = DEFAULT_XG_CONFIG.max_distance_penalty_m
OPTIMAL_ANGLE = DEFAULT_XG_CONFIG.optimal_angle
MAX_ANGLE_PENALTY = DEFAULT_XG_CONFIG.max_angle_penalty
POWER_SHOT_SPEED_KPH = DEFAULT_XG_CONFIG.power_shot_speed_kph
OPTIMAL_SHOT_SPEED_KPH = DEFAULT_XG_CONFIG.optimal_shot_speed_kph
MIN_SHOT_SPEED_KPH = DEFAULT_XG_CONFIG.min_shot_speed_kph

# Base xG values by shot type (legacy dict)
BASE_XG = {
    ShotType.GROUND: DEFAULT_XG_CONFIG.base_xg_ground,
    ShotType.AERIAL: DEFAULT_XG_CONFIG.base_xg_aerial,
    ShotType.WALL: DEFAULT_XG_CONFIG.base_xg_wall,
    ShotType.CEILING: DEFAULT_XG_CONFIG.base_xg_ceiling,
    ShotType.REDIRECT: DEFAULT_XG_CONFIG.base_xg_redirect,
    ShotType.POWER_SHOT: DEFAULT_XG_CONFIG.base_xg_power_shot,
    ShotType.LOB: DEFAULT_XG_CONFIG.base_xg_lob,
    ShotType.UNKNOWN: DEFAULT_XG_CONFIG.base_xg_unknown,
}


def _calculate_goal_distance(position: Vec3, target_team: int) -> float:
    """Calculate distance to target goal in meters.

    Args:
        position: Ball position
        target_team: 0 for blue goal (positive y), 1 for orange goal (negative y)

    Returns:
        Distance in meters (field units / 100)
    """
    goal_center = GOAL_CENTER_BLUE if target_team == 0 else GOAL_CENTER_ORANGE
    dx = position.x - goal_center.x
    dy = position.y - goal_center.y
    dz = position.z - goal_center.z
    return math.sqrt(dx * dx + dy * dy + dz * dz) / 100.0


def _calculate_goal_angle(position: Vec3, velocity: Vec3, target_team: int) -> float:
    """Calculate angle between shot trajectory and goal center.

    Args:
        position: Ball position
        velocity: Ball velocity
        target_team: 0 for blue goal, 1 for orange goal

    Returns:
        Angle in degrees (0 = direct line, 90 = perpendicular)
    """
    goal_center = GOAL_CENTER_BLUE if target_team == 0 else GOAL_CENTER_ORANGE

    # Vector from ball to goal center
    to_goal = Vec3(
        goal_center.x - position.x,
        goal_center.y - position.y,
        goal_center.z - position.z,
    )

    # Normalize vectors
    to_goal_mag = math.sqrt(to_goal.x**2 + to_goal.y**2 + to_goal.z**2)
    vel_mag = math.sqrt(velocity.x**2 + velocity.y**2 + velocity.z**2)

    if to_goal_mag < 1.0 or vel_mag < 1.0:
        return 90.0  # Can't calculate meaningful angle

    # Dot product gives cosine of angle
    dot = to_goal.x * velocity.x + to_goal.y * velocity.y + to_goal.z * velocity.z
    cos_angle = dot / (to_goal_mag * vel_mag)

    # Clamp to valid range for acos
    cos_angle = max(-1.0, min(1.0, cos_angle))

    return math.degrees(math.acos(cos_angle))


def _calculate_defender_coverage(
    ball_position: Vec3,
    ball_velocity: Vec3,
    defenders: list[PlayerFrame],
    target_team: int,
) -> tuple[float, bool]:
    """Calculate how well defenders cover the shot.

    Args:
        ball_position: Ball position
        ball_velocity: Ball velocity
        defenders: List of defending players
        target_team: 0 for blue goal, 1 for orange goal

    Returns:
        Tuple of (coverage score 0-1, is_open_net bool)
    """
    if not defenders:
        return 0.0, True

    goal_center = GOAL_CENTER_BLUE if target_team == 0 else GOAL_CENTER_ORANGE
    goal_y = goal_center.y

    # Calculate shot trajectory
    ball_speed = math.sqrt(ball_velocity.x**2 + ball_velocity.y**2 + ball_velocity.z**2)
    if ball_speed < 10.0:
        return 0.0, True  # Ball not moving, assume open

    # Time to goal (rough estimate)
    dy = abs(goal_y - ball_position.y)
    vy = abs(ball_velocity.y)
    if vy < 10.0:
        time_to_goal = 5.0  # Ball moving sideways, long time
    else:
        time_to_goal = dy / vy

    # Check each defender's ability to reach the ball path
    coverage_scores = []
    for defender in defenders:
        # Distance from defender to shot path
        # Simplified: just check horizontal distance to ball's projected path

        # Projected ball position when it reaches goal line
        proj_x = ball_position.x + ball_velocity.x * time_to_goal
        proj_z = ball_position.z + ball_velocity.z * time_to_goal

        # Defender position relative to projected shot
        dx = abs(defender.position.x - proj_x)
        dz = abs(defender.position.z - proj_z)

        # Is defender between ball and goal?
        defender_y = defender.position.y
        ball_y = ball_position.y

        if target_team == 0:  # Blue goal (positive y)
            between = ball_y < defender_y < goal_y
        else:  # Orange goal (negative y)
            between = goal_y < defender_y < ball_y

        if not between:
            continue

        # Defender speed matters - can they reach the ball?
        defender_speed = math.sqrt(
            defender.velocity.x**2 + defender.velocity.y**2 + defender.velocity.z**2
        )

        # Rough reachability (can defender close the gap in time?)
        gap_distance = math.sqrt(dx * dx + dz * dz)
        reach_time = gap_distance / max(
            defender_speed + 1000.0, 1.0
        )  # +1000 for boost potential

        if reach_time < time_to_goal:
            # Defender can potentially save
            coverage = 1.0 - (reach_time / time_to_goal)
            coverage_scores.append(min(1.0, coverage))

    if not coverage_scores:
        return 0.0, True

    # Return max coverage (best positioned defender)
    max_coverage = max(coverage_scores)
    return max_coverage, max_coverage < 0.3


def _classify_shot_type(
    ball_position: Vec3,
    ball_velocity: Vec3,
    touch_context: TouchContext | None,
) -> ShotType:
    """Classify the type of shot based on ball state.

    Args:
        ball_position: Ball position
        ball_velocity: Ball velocity
        touch_context: Touch context if available

    Returns:
        ShotType classification
    """
    speed_kph = (
        math.sqrt(ball_velocity.x**2 + ball_velocity.y**2 + ball_velocity.z**2)
        * UU_S_TO_KPH
    )

    height = ball_position.z

    # Use touch context if available
    if touch_context is not None:
        if touch_context == TouchContext.CEILING:
            return ShotType.CEILING
        elif touch_context == TouchContext.WALL:
            return ShotType.WALL
        elif touch_context == TouchContext.AERIAL:
            return ShotType.AERIAL
        elif touch_context == TouchContext.HALF_VOLLEY:
            return ShotType.REDIRECT

    # Classify by characteristics
    if speed_kph > POWER_SHOT_SPEED_KPH and height < 200.0:
        return ShotType.POWER_SHOT

    if height > 800.0:
        return ShotType.AERIAL

    if height > 400.0 and ball_velocity.z > 500.0:
        return ShotType.LOB

    if height < 150.0:
        return ShotType.GROUND

    return ShotType.UNKNOWN


def calculate_xg(
    ball_position: Vec3,
    ball_velocity: Vec3,
    shooter_team: int,
    frame: Frame | None = None,
    touch_context: TouchContext | None = None,
) -> XGResult:
    """Calculate expected goals probability for a shot.

    Args:
        ball_position: Ball position at shot time
        ball_velocity: Ball velocity at shot time
        shooter_team: Team taking the shot (0 = blue, 1 = orange)
        frame: Frame data for defender positions (optional)
        touch_context: Touch context classification (optional)

    Returns:
        XGResult with xG probability and breakdown
    """
    # Target is opposite goal
    target_team = 1 - shooter_team

    # Calculate base factors
    distance_m = _calculate_goal_distance(ball_position, target_team)
    angle_deg = _calculate_goal_angle(ball_position, ball_velocity, target_team)
    ball_speed_kph = (
        math.sqrt(ball_velocity.x**2 + ball_velocity.y**2 + ball_velocity.z**2)
        * UU_S_TO_KPH
    )

    # Get defenders (opponents)
    defenders = []
    if frame is not None:
        for player in frame.players:
            if player.team != shooter_team:
                defenders.append(player)

    defender_coverage, is_open_net = _calculate_defender_coverage(
        ball_position, ball_velocity, defenders, target_team
    )

    # Classify shot type
    shot_type = _classify_shot_type(ball_position, ball_velocity, touch_context)

    # Start with base xG for shot type
    base_xg = BASE_XG.get(shot_type, BASE_XG[ShotType.UNKNOWN])

    # Distance factor (peaks around optimal distance)
    if distance_m < OPTIMAL_DISTANCE_M:
        # Close range - slightly easier
        distance_factor = 1.0 + 0.2 * (1.0 - distance_m / OPTIMAL_DISTANCE_M)
    elif distance_m > MAX_DISTANCE_PENALTY_M:
        # Very long range - much harder
        distance_factor = 0.2
    else:
        # Normal range - linear decay
        range_pct = (distance_m - OPTIMAL_DISTANCE_M) / (
            MAX_DISTANCE_PENALTY_M - OPTIMAL_DISTANCE_M
        )
        distance_factor = 1.0 - 0.7 * range_pct

    # Angle factor (direct shots easier)
    if angle_deg < 20.0:
        angle_factor = 1.0
    elif angle_deg > MAX_ANGLE_PENALTY:
        angle_factor = 0.15
    else:
        angle_pct = (angle_deg - 20.0) / (MAX_ANGLE_PENALTY - 20.0)
        angle_factor = 1.0 - 0.75 * angle_pct

    # Speed factor
    if ball_speed_kph < MIN_SHOT_SPEED_KPH:
        speed_factor = 0.4  # Very slow shots easy to save
    elif ball_speed_kph < OPTIMAL_SHOT_SPEED_KPH:
        speed_factor = 0.6 + 0.4 * (ball_speed_kph / OPTIMAL_SHOT_SPEED_KPH)
    else:
        # Faster = better, up to a point
        speed_factor = min(1.3, 1.0 + 0.003 * (ball_speed_kph - OPTIMAL_SHOT_SPEED_KPH))

    # Defender factor
    defender_factor = 1.0 - 0.7 * defender_coverage
    if is_open_net:
        defender_factor = 1.5  # Open net bonus

    # Combine factors
    xg = base_xg * distance_factor * angle_factor * speed_factor * defender_factor

    # Clamp to valid range
    xg = max(0.01, min(0.95, xg))

    factors = {
        "base_xg": round(base_xg, 4),
        "distance_factor": round(distance_factor, 3),
        "angle_factor": round(angle_factor, 3),
        "speed_factor": round(speed_factor, 3),
        "defender_factor": round(defender_factor, 3),
    }

    return XGResult(
        xg=round(xg, 4),
        shot_type=shot_type,
        distance_m=round(distance_m, 2),
        angle_degrees=round(angle_deg, 1),
        ball_speed_kph=round(ball_speed_kph, 1),
        is_open_net=is_open_net,
        defender_coverage=round(defender_coverage, 3),
        factors=factors,
    )


def analyze_shots_xg(
    frames: list[Frame],
    touches: list[TouchEvent],
) -> dict:
    """Analyze all shots and calculate xG for each.

    Args:
        frames: Normalized frame data
        touches: List of touch events

    Returns:
        Dict with xG analysis results
    """
    # Only count actual SHOT outcomes for xG calculation
    # Previously included PASS which inflated shot counts
    shot_outcomes = {"SHOT"}

    shots_xg: list[dict] = []
    per_player: dict[str, dict] = {}

    # Build frame lookup for efficiency - use sorted timestamps for binary search
    frame_by_time: dict[float, Frame] = {}
    sorted_timestamps: list[float] = []
    for f in frames:
        ts = round(f.timestamp, 3)
        frame_by_time[ts] = f
        sorted_timestamps.append(ts)
    sorted_timestamps.sort()

    # Get player teams
    player_teams: dict[str, int] = {}
    for frame in frames:
        for player in frame.players:
            if player.player_id not in player_teams:
                player_teams[player.player_id] = player.team

    def find_nearest_frame(target_time: float) -> Frame | None:
        """Find frame nearest to target_time using binary search."""
        if not sorted_timestamps:
            return None

        # Try exact match first
        exact_key = round(target_time, 3)
        if exact_key in frame_by_time:
            return frame_by_time[exact_key]

        # Binary search for nearest timestamp
        idx = bisect.bisect_left(sorted_timestamps, target_time)

        # Compare neighboring timestamps
        candidates = []
        if idx > 0:
            candidates.append(sorted_timestamps[idx - 1])
        if idx < len(sorted_timestamps):
            candidates.append(sorted_timestamps[idx])

        if not candidates:
            return None

        nearest_ts = min(candidates, key=lambda t: abs(t - target_time))
        return frame_by_time.get(nearest_ts)

    for touch in touches:
        # Check if this is a shot-like touch
        if touch.outcome not in shot_outcomes:
            continue

        # Find the frame for this touch using binary search
        frame = find_nearest_frame(touch.t)

        if frame is None:
            continue

        # Get shooter team
        shooter_team = player_teams.get(touch.player_id, 0)

        # Calculate xG
        xg_result = calculate_xg(
            ball_position=frame.ball.position,
            ball_velocity=frame.ball.velocity,
            shooter_team=shooter_team,
            frame=frame,
            touch_context=touch.touch_context,
        )

        shot_data = {
            "timestamp": touch.t,
            "player_id": touch.player_id,
            "xg": xg_result.xg,
            "shot_type": xg_result.shot_type.value,
            "distance_m": xg_result.distance_m,
            "angle_degrees": xg_result.angle_degrees,
            "ball_speed_kph": xg_result.ball_speed_kph,
            "is_open_net": xg_result.is_open_net,
            "defender_coverage": xg_result.defender_coverage,
            "factors": xg_result.factors,
            "outcome": touch.outcome,
        }
        shots_xg.append(shot_data)

        # Aggregate per player
        if touch.player_id not in per_player:
            per_player[touch.player_id] = {
                "total_shots": 0,
                "total_xg": 0.0,
                "shots": [],
            }

        per_player[touch.player_id]["total_shots"] += 1
        per_player[touch.player_id]["total_xg"] += xg_result.xg
        per_player[touch.player_id]["shots"].append(shot_data)

    # Calculate team totals
    team_xg = {0: 0.0, 1: 0.0}
    for player_id, data in per_player.items():
        team = player_teams.get(player_id, 0)
        team_xg[team] += data["total_xg"]

    return {
        "shots": shots_xg,
        "per_player": per_player,
        "per_team": {
            "blue": {"total_xg": round(team_xg.get(0, 0.0), 3)},
            "orange": {"total_xg": round(team_xg.get(1, 0.0), 3)},
        },
        "total_shots": len(shots_xg),
    }
