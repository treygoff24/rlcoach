"""Defensive positioning analysis module.

Provides analysis of:
- Last defender situations
- Shadow defense effectiveness
- Defensive rotations
- Goal-side positioning
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum
from typing import Optional

from ..field_constants import FIELD, Vec3
from ..normalize import DEFAULT_FRAME_RATE
from ..parser.types import Frame, PlayerFrame


class DefensiveRole(Enum):
    """Defensive role classification."""
    LAST_DEFENDER = "last_defender"  # Furthest back, protecting goal
    SECOND_DEFENDER = "second_defender"  # Supporting last defender
    SHADOW = "shadow"  # Shadowing ball carrier
    PRESSURING = "pressuring"  # Applying pressure on ball
    RECOVERING = "recovering"  # Rotating back to defense
    OUT_OF_POSITION = "out_of_position"  # Ball-side but wrong position


class ShadowQuality(Enum):
    """Quality of shadow defense positioning."""
    EXCELLENT = "excellent"  # Perfect shadow, cutting off all angles
    GOOD = "good"  # Good position, most angles covered
    ADEQUATE = "adequate"  # Acceptable but some gaps
    POOR = "poor"  # Major gaps in coverage
    NONE = "none"  # Not shadowing


@dataclass(frozen=True)
class DefensiveSnapshot:
    """Snapshot of defensive situation for one team at a frame."""
    timestamp: float
    team: int  # 0 = blue, 1 = orange
    last_defender_id: Optional[str]
    last_defender_distance_to_goal: float
    second_defender_id: Optional[str]
    ball_distance_to_goal: float
    defensive_coverage: float  # 0.0 = no coverage, 1.0 = full coverage
    is_danger_zone: bool  # Ball in defensive third with threat
    player_roles: dict[str, DefensiveRole]


@dataclass(frozen=True)
class ShadowDefenseEvent:
    """A period of shadow defense by a player."""
    start_time: float
    end_time: float
    player_id: str
    quality: ShadowQuality
    average_shadow_angle: float  # How well positioned between ball and goal
    duration: float
    successful: bool  # Did shadow result in turnover/clear


# Field constants
DEFENSIVE_THIRD_Y = FIELD.BACK_WALL_Y * 0.33
DANGER_ZONE_Y = FIELD.BACK_WALL_Y * 0.5
SHADOW_ANGLE_TOLERANCE = 30.0  # Degrees from ideal shadow line
LAST_DEFENDER_BUFFER = 800.0  # Distance behind other teammates to be "last"


def _distance_to_own_goal(position: Vec3, team: int) -> float:
    """Calculate distance to own goal.

    Args:
        position: Position to measure from
        team: 0 = blue (goal at -Y), 1 = orange (goal at +Y)

    Returns:
        Distance in unreal units
    """
    goal_y = -FIELD.BACK_WALL_Y if team == 0 else FIELD.BACK_WALL_Y
    goal_center = Vec3(0.0, goal_y, FIELD.GOAL_HEIGHT / 2)

    dx = position.x - goal_center.x
    dy = position.y - goal_center.y
    dz = position.z - goal_center.z

    return math.sqrt(dx * dx + dy * dy + dz * dz)


def _is_goal_side(player_pos: Vec3, ball_pos: Vec3, team: int) -> bool:
    """Check if player is goal-side of the ball.

    Args:
        player_pos: Player position
        ball_pos: Ball position
        team: Player's team (0 = blue, 1 = orange)

    Returns:
        True if player is between ball and own goal
    """
    if team == 0:  # Blue defends negative Y
        return player_pos.y < ball_pos.y
    else:  # Orange defends positive Y
        return player_pos.y > ball_pos.y


def _calculate_shadow_angle(
    player_pos: Vec3,
    ball_pos: Vec3,
    team: int,
) -> float:
    """Calculate how well a player shadows the ball from goal.

    Args:
        player_pos: Player position
        ball_pos: Ball position
        team: Player's team

    Returns:
        Angle deviation from ideal shadow line (0 = perfect, 90 = perpendicular)
    """
    # Own goal center
    goal_y = -FIELD.BACK_WALL_Y if team == 0 else FIELD.BACK_WALL_Y
    goal_center = Vec3(0.0, goal_y, FIELD.GOAL_HEIGHT / 2)

    # Vector from ball to goal
    ball_to_goal = Vec3(
        goal_center.x - ball_pos.x,
        goal_center.y - ball_pos.y,
        0.0,  # Ignore Z for shadow calculation
    )

    # Vector from ball to player
    ball_to_player = Vec3(
        player_pos.x - ball_pos.x,
        player_pos.y - ball_pos.y,
        0.0,
    )

    # Normalize
    btg_mag = math.sqrt(ball_to_goal.x ** 2 + ball_to_goal.y ** 2)
    btp_mag = math.sqrt(ball_to_player.x ** 2 + ball_to_player.y ** 2)

    if btg_mag < 1.0 or btp_mag < 1.0:
        return 90.0

    # Dot product for angle
    dot = (ball_to_goal.x * ball_to_player.x + ball_to_goal.y * ball_to_player.y)
    cos_angle = dot / (btg_mag * btp_mag)
    cos_angle = max(-1.0, min(1.0, cos_angle))

    angle = math.degrees(math.acos(cos_angle))

    # If player is ball-side (not goal-side), shadow is ineffective
    if not _is_goal_side(player_pos, ball_pos, team):
        return 180.0 - angle  # Invert to show poor positioning

    return angle


def _assess_shadow_quality(angle: float, distance_to_ball: float) -> ShadowQuality:
    """Assess shadow defense quality.

    Args:
        angle: Shadow angle deviation from ideal
        distance_to_ball: Distance from shadowing player to ball

    Returns:
        ShadowQuality classification
    """
    # Too far to be effective shadow
    if distance_to_ball > 3000.0:
        return ShadowQuality.NONE

    # Distance penalty - further away = harder to shadow effectively
    distance_factor = max(0.0, 1.0 - distance_to_ball / 3000.0)

    # Adjusted angle considering distance
    effective_angle = angle / max(0.5, distance_factor)

    if effective_angle < 10.0:
        return ShadowQuality.EXCELLENT
    elif effective_angle < 25.0:
        return ShadowQuality.GOOD
    elif effective_angle < 45.0:
        return ShadowQuality.ADEQUATE
    else:
        return ShadowQuality.POOR


def _calculate_defensive_coverage(
    defenders: list[PlayerFrame],
    ball_pos: Vec3,
    team: int,
) -> float:
    """Calculate how well defenders cover the goal.

    Args:
        defenders: List of defending players
        ball_pos: Ball position
        team: Defending team

    Returns:
        Coverage score 0.0-1.0 (1.0 = fully covered)
    """
    if not defenders:
        return 0.0

    goal_y = -FIELD.BACK_WALL_Y if team == 0 else FIELD.BACK_WALL_Y
    goal_center = Vec3(0.0, goal_y, FIELD.GOAL_HEIGHT / 2)

    # Check coverage at different goal positions
    goal_positions = [
        Vec3(-FIELD.GOAL_WIDTH * 0.4, goal_y, FIELD.GOAL_HEIGHT * 0.3),
        Vec3(0.0, goal_y, FIELD.GOAL_HEIGHT * 0.3),
        Vec3(FIELD.GOAL_WIDTH * 0.4, goal_y, FIELD.GOAL_HEIGHT * 0.3),
        Vec3(-FIELD.GOAL_WIDTH * 0.3, goal_y, FIELD.GOAL_HEIGHT * 0.7),
        Vec3(0.0, goal_y, FIELD.GOAL_HEIGHT * 0.7),
        Vec3(FIELD.GOAL_WIDTH * 0.3, goal_y, FIELD.GOAL_HEIGHT * 0.7),
    ]

    covered_points = 0
    for goal_point in goal_positions:
        # Check if any defender is in the path
        for defender in defenders:
            if not _is_goal_side(defender.position, ball_pos, team):
                continue

            # Is defender close to line between ball and goal point?
            shadow_angle = _calculate_shadow_angle(defender.position, ball_pos, team)
            if shadow_angle < 30.0:
                covered_points += 1
                break

    return covered_points / len(goal_positions)


def analyze_defensive_frame(frame: Frame, team: int) -> DefensiveSnapshot:
    """Analyze defensive positioning for one team in a frame.

    Args:
        frame: Frame data
        team: Team to analyze (0 = blue, 1 = orange)

    Returns:
        DefensiveSnapshot with analysis results
    """
    ball_pos = frame.ball.position
    ball_dist_to_goal = _distance_to_own_goal(ball_pos, team)

    # Get team's players
    team_players = [p for p in frame.players if p.team == team]

    if not team_players:
        return DefensiveSnapshot(
            timestamp=frame.timestamp,
            team=team,
            last_defender_id=None,
            last_defender_distance_to_goal=0.0,
            second_defender_id=None,
            ball_distance_to_goal=ball_dist_to_goal,
            defensive_coverage=0.0,
            is_danger_zone=True,
            player_roles={},
        )

    # Sort by distance to own goal (closest = last defender)
    sorted_by_goal_dist = sorted(
        team_players,
        key=lambda p: _distance_to_own_goal(p.position, team)
    )

    last_defender = sorted_by_goal_dist[0]
    second_defender = sorted_by_goal_dist[1] if len(sorted_by_goal_dist) > 1 else None

    # Classify roles for each player
    player_roles: dict[str, DefensiveRole] = {}

    for i, player in enumerate(sorted_by_goal_dist):
        player_dist = _distance_to_own_goal(player.position, team)
        ball_dist = math.sqrt(
            (player.position.x - ball_pos.x) ** 2 +
            (player.position.y - ball_pos.y) ** 2 +
            (player.position.z - ball_pos.z) ** 2
        )

        if i == 0:
            player_roles[player.player_id] = DefensiveRole.LAST_DEFENDER
        elif i == 1:
            player_roles[player.player_id] = DefensiveRole.SECOND_DEFENDER
        elif ball_dist < 800.0:
            player_roles[player.player_id] = DefensiveRole.PRESSURING
        elif _is_goal_side(player.position, ball_pos, team):
            shadow_angle = _calculate_shadow_angle(player.position, ball_pos, team)
            if shadow_angle < 45.0:
                player_roles[player.player_id] = DefensiveRole.SHADOW
            else:
                player_roles[player.player_id] = DefensiveRole.RECOVERING
        else:
            player_roles[player.player_id] = DefensiveRole.OUT_OF_POSITION

    # Calculate coverage
    defenders_goal_side = [p for p in team_players if _is_goal_side(p.position, ball_pos, team)]
    defensive_coverage = _calculate_defensive_coverage(defenders_goal_side, ball_pos, team)

    # Check danger zone
    in_defensive_third = (
        (team == 0 and ball_pos.y < -DEFENSIVE_THIRD_Y) or
        (team == 1 and ball_pos.y > DEFENSIVE_THIRD_Y)
    )
    is_danger = in_defensive_third and defensive_coverage < 0.5

    return DefensiveSnapshot(
        timestamp=frame.timestamp,
        team=team,
        last_defender_id=last_defender.player_id,
        last_defender_distance_to_goal=round(_distance_to_own_goal(last_defender.position, team), 2),
        second_defender_id=second_defender.player_id if second_defender else None,
        ball_distance_to_goal=round(ball_dist_to_goal, 2),
        defensive_coverage=round(defensive_coverage, 3),
        is_danger_zone=is_danger,
        player_roles=player_roles,
    )


def analyze_defense(frames: list[Frame]) -> dict:
    """Comprehensive defensive analysis for the replay.

    Args:
        frames: Normalized frame data

    Returns:
        Dict with defensive analysis results
    """
    per_team: dict[str, dict] = {"blue": {}, "orange": {}}
    per_player: dict[str, dict] = {}
    danger_moments: list[dict] = []

    # Get all unique player IDs with their teams
    player_teams: dict[str, int] = {}
    for frame in frames:
        for player in frame.players:
            if player.player_id not in player_teams:
                player_teams[player.player_id] = player.team

    # Initialize per-player stats
    for player_id in player_teams:
        per_player[player_id] = {
            "time_as_last_defender": 0.0,
            "time_out_of_position": 0.0,
            "time_shadowing": 0.0,
            "shadow_quality_scores": [],
        }

    # Estimate frame rate from actual data for fallback dt
    estimated_fps = DEFAULT_FRAME_RATE
    if len(frames) >= 2:
        total_time = frames[-1].timestamp - frames[0].timestamp
        if total_time > 0:
            estimated_fps = max(1.0, (len(frames) - 1) / total_time)
    default_dt = 1.0 / estimated_fps

    # Analyze each frame
    prev_timestamp = frames[0].timestamp if frames else 0.0
    blue_danger_time = 0.0
    orange_danger_time = 0.0

    for frame in frames:
        dt = frame.timestamp - prev_timestamp
        if dt < 0 or dt > 1.0:  # Skip invalid time deltas
            dt = default_dt  # Use measured frame rate

        for team in [0, 1]:
            snapshot = analyze_defensive_frame(frame, team)

            # Track danger zone time
            if snapshot.is_danger_zone:
                if team == 0:
                    blue_danger_time += dt
                else:
                    orange_danger_time += dt

                danger_moments.append({
                    "timestamp": frame.timestamp,
                    "team": "blue" if team == 0 else "orange",
                    "coverage": snapshot.defensive_coverage,
                    "ball_distance": snapshot.ball_distance_to_goal,
                })

            # Update player role times
            for player_id, role in snapshot.player_roles.items():
                if player_id not in per_player:
                    continue

                if role == DefensiveRole.LAST_DEFENDER:
                    per_player[player_id]["time_as_last_defender"] += dt
                elif role == DefensiveRole.OUT_OF_POSITION:
                    per_player[player_id]["time_out_of_position"] += dt
                elif role == DefensiveRole.SHADOW:
                    per_player[player_id]["time_shadowing"] += dt

                    # Calculate shadow quality for this moment
                    player_frame = next(
                        (p for p in frame.players if p.player_id == player_id),
                        None
                    )
                    if player_frame:
                        shadow_angle = _calculate_shadow_angle(
                            player_frame.position,
                            frame.ball.position,
                            team
                        )
                        per_player[player_id]["shadow_quality_scores"].append(shadow_angle)

        prev_timestamp = frame.timestamp

    # Compute final stats - use max(, 0.1) to prevent division by zero in edge cases
    if len(frames) > 1:
        total_time = max(frames[-1].timestamp - frames[0].timestamp, 0.1)
    else:
        total_time = 0.1  # Minimal default for single-frame edge case

    for player_id, stats in per_player.items():
        # Average shadow angle (lower = better)
        shadow_scores = stats.get("shadow_quality_scores", [])
        if shadow_scores:
            avg_shadow = sum(shadow_scores) / len(shadow_scores)
            stats["average_shadow_angle"] = round(avg_shadow, 2)
        else:
            stats["average_shadow_angle"] = None

        # Round time stats
        stats["time_as_last_defender"] = round(stats["time_as_last_defender"], 2)
        stats["time_out_of_position"] = round(stats["time_out_of_position"], 2)
        stats["time_shadowing"] = round(stats["time_shadowing"], 2)

        # Remove internal tracking list
        del stats["shadow_quality_scores"]

    per_team["blue"] = {
        "danger_zone_time": round(blue_danger_time, 2),
        "danger_zone_pct": round(100 * blue_danger_time / total_time, 2),
    }
    per_team["orange"] = {
        "danger_zone_time": round(orange_danger_time, 2),
        "danger_zone_pct": round(100 * orange_danger_time / total_time, 2),
    }

    return {
        "per_team": per_team,
        "per_player": per_player,
        "danger_moments": danger_moments[:100],  # Limit to avoid huge output
        "total_danger_moments": len(danger_moments),
    }
