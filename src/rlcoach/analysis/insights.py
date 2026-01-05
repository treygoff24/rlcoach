"""Coaching insights generation based on player performance metrics."""

from __future__ import annotations

from typing import Any

# Priority levels for insight ranking (higher = more impactful)
PRIORITY_CRITICAL = 100  # Major issues blocking improvement
PRIORITY_HIGH = 75  # Significant areas for growth
PRIORITY_MEDIUM = 50  # Moderate improvement opportunities
PRIORITY_LOW = 25  # Minor optimizations
PRIORITY_INFO = 10  # Positive feedback / informational


def generate_player_insights(analysis_data: dict[str, Any]) -> list[dict[str, Any]]:
    """Generate coaching insights for a specific player.

    Args:
        analysis_data: Complete player analysis data including all metrics

    Returns:
        List of insight objects with severity, message, evidence, and priority
    """
    insights = []
    player_id = analysis_data.get("player_id")

    # Positioning insights
    positioning = analysis_data.get("positioning", {})
    insights.extend(_analyze_positioning_insights(positioning, player_id))

    # Boost economy insights
    boost = analysis_data.get("boost", {})
    insights.extend(_analyze_boost_insights(boost, player_id))

    # Movement insights
    movement = analysis_data.get("movement", {})
    insights.extend(_analyze_movement_insights(movement, player_id))

    # Rotation compliance insights
    rotation_compliance = analysis_data.get("rotation_compliance", {})
    insights.extend(_analyze_rotation_insights(rotation_compliance, player_id))

    # Fundamentals insights
    fundamentals = analysis_data.get("fundamentals", {})
    insights.extend(_analyze_fundamentals_insights(fundamentals, player_id))

    # Challenges insights
    challenges = analysis_data.get("challenges", {})
    insights.extend(_analyze_challenges_insights(challenges, player_id))

    # Sort by priority (highest first)
    insights.sort(key=lambda x: x.get("priority", 0), reverse=True)

    return insights


def generate_team_insights(
    per_team_analysis: dict[str, Any], per_player_analysis: dict[str, Any]
) -> list[dict[str, Any]]:
    """Generate coaching insights for the entire team/match.

    Args:
        per_team_analysis: Team-level analysis data
        per_player_analysis: All player analysis data

    Returns:
        List of team-level insight objects
    """
    insights = []

    blue_data = per_team_analysis.get("blue", {})
    orange_data = per_team_analysis.get("orange", {})

    # Team fundamentals comparison
    insights.extend(_analyze_team_fundamentals(blue_data, orange_data))

    # Boost economy team analysis
    insights.extend(_analyze_team_boost(blue_data, orange_data))

    # Kickoff performance
    insights.extend(_analyze_team_kickoffs(blue_data, orange_data))

    # Team positioning coordination
    insights.extend(_analyze_team_positioning(blue_data, orange_data))

    return insights


def _analyze_positioning_insights(
    positioning: dict, player_id: str
) -> list[dict[str, Any]]:
    """Generate positioning-related insights."""
    insights = []

    ahead_ball_pct = positioning.get("ahead_ball_pct", 0)
    third_man_pct = positioning.get("third_man_pct", 0)
    first_man_pct = positioning.get("first_man_pct", 0)

    # Too much time ahead of ball without being primary attacker
    if ahead_ball_pct > 45 and first_man_pct < 40:
        insights.append(
            {
                "severity": "SUGGESTION",
                "priority": PRIORITY_HIGH,
                "message": (
                    "Over-committing to offense without ball control"
                ),
                "contributing_factors": [
                    f"Ahead of ball {ahead_ball_pct:.0f}% of the time",
                    f"But only first man {first_man_pct:.0f}% of the time",
                    "This leaves teammates in difficult rotation positions",
                ],
                "recommendation": (
                    "Focus on back-post positioning when not actively "
                    "challenging. Let plays develop before committing."
                ),
                "evidence": {
                    "ahead_ball_pct": ahead_ball_pct,
                    "first_man_pct": first_man_pct,
                },
            }
        )

    # Not enough third man presence in 3v3
    if third_man_pct is not None and third_man_pct < 25:
        insights.append(
            {
                "severity": "SUGGESTION",
                "priority": PRIORITY_MEDIUM,
                "message": (
                    "Insufficient third man coverage"
                ),
                "contributing_factors": [
                    f"Only in third man position {third_man_pct:.0f}% of the time",
                    "Third man should be ~30-35% in balanced 3v3 rotation",
                ],
                "recommendation": (
                    "After rotating back, hold position briefly before "
                    "pushing up. Trust teammates to maintain pressure."
                ),
                "evidence": {"third_man_pct": third_man_pct},
            }
        )

    # Too much first man time (ball chasing indicator)
    if first_man_pct > 60:
        insights.append(
            {
                "severity": "WARNING",
                "priority": PRIORITY_CRITICAL,
                "message": (
                    "Potential ball-chasing detected"
                ),
                "contributing_factors": [
                    f"First man position {first_man_pct:.0f}% of the time",
                    "Healthy first man % is 30-45% depending on playstyle",
                    "Excessive first man time disrupts team rotation",
                ],
                "recommendation": (
                    "Practice 'fake challenging' — approach ball then peel "
                    "back to create passing opportunities for teammates."
                ),
                "evidence": {"first_man_pct": first_man_pct},
            }
        )

    return insights


def _analyze_boost_insights(boost: dict, player_id: str) -> list[dict[str, Any]]:
    """Generate boost economy insights."""
    insights = []

    time_zero_boost_s = boost.get("time_zero_boost_s", 0)
    avg_boost = boost.get("avg_boost", 0)
    waste = boost.get("waste", 0)
    stolen_big_pads = boost.get("stolen_big_pads", 0)

    # Too much time at zero boost
    if time_zero_boost_s > 60:
        insights.append(
            {
                "severity": "SUGGESTION",
                "priority": PRIORITY_HIGH,
                "message": "Boost starvation limiting options",
                "contributing_factors": [
                    f"Spent {time_zero_boost_s:.0f}s at zero boost",
                    f"Average boost level only {avg_boost:.0f}",
                    "Zero boost = no aerial threat, slow recovery",
                ],
                "recommendation": (
                    "Prioritize small pads on rotation. A quick detour "
                    "through mid-boost is often faster than going for corners."
                ),
                "evidence": {
                    "time_zero_boost_s": time_zero_boost_s,
                    "avg_boost": avg_boost,
                },
            }
        )

    # High boost waste
    if waste > 200:
        insights.append(
            {
                "severity": "INFO",
                "priority": PRIORITY_LOW,
                "message": "Boost efficiency can improve",
                "contributing_factors": [
                    f"Wasted {waste:.0f} units of boost",
                    "Waste = collecting boost when nearly full",
                ],
                "recommendation": (
                    "Before grabbing big boost, check your meter. "
                    "If above 70, small pads may be more efficient."
                ),
                "evidence": {"boost_waste": waste},
            }
        )

    # Good corner boost stealing
    if stolen_big_pads >= 3:
        insights.append(
            {
                "severity": "INFO",
                "priority": PRIORITY_INFO,
                "message": "Effective boost denial",
                "contributing_factors": [
                    f"Stole {stolen_big_pads} corner boosts from opponents",
                    "Boost denial limits opponent options",
                ],
                "recommendation": (
                    "Keep it up! Starving opponents of boost is as valuable "
                    "as getting it yourself."
                ),
                "evidence": {"stolen_big_pads": stolen_big_pads},
            }
        )

    return insights


def _analyze_movement_insights(movement: dict, player_id: str) -> list[dict[str, Any]]:
    """Generate movement and mechanics insights."""
    insights = []

    time_slow_s = movement.get("time_slow_s", 0)
    time_supersonic_s = movement.get("time_supersonic_s", 0)
    aerial_count = movement.get("aerial_count", 0)

    # Too much slow time
    total_time = time_slow_s + movement.get("time_boost_speed_s", 0) + time_supersonic_s
    if total_time > 0:
        slow_pct = (time_slow_s / total_time) * 100
        if slow_pct > 60:
            insights.append(
                {
                    "severity": "SUGGESTION",
                    "priority": PRIORITY_MEDIUM,
                    "message": "Low momentum limiting play impact",
                    "contributing_factors": [
                        f"{slow_pct:.0f}% of time at low speed",
                        "Slow speed = late to challenges, easy to read",
                        f"Only {time_supersonic_s:.0f}s at supersonic",
                    ],
                    "recommendation": (
                        "Focus on maintaining momentum through turns. "
                        "Use powerslide to preserve speed while redirecting."
                    ),
                    "evidence": {
                        "slow_speed_percentage": slow_pct,
                        "time_slow_s": time_slow_s,
                    },
                }
            )

    # Very few aerials in a long match
    if aerial_count < 5 and total_time > 300:  # 5+ minute match
        insights.append(
            {
                "severity": "INFO",
                "priority": PRIORITY_LOW,
                "message": "Limited aerial presence",
                "contributing_factors": [
                    f"Only {aerial_count} aerial attempts in a 5+ minute game",
                    "Aerials create unpredictable threats",
                ],
                "recommendation": (
                    "Practice basic aerials in training. Even simple "
                    "aerial challenges force opponents to respect your airspace."
                ),
                "evidence": {"aerial_count": aerial_count},
            }
        )

    return insights


def _analyze_rotation_insights(
    rotation_compliance: dict, player_id: str
) -> list[dict[str, Any]]:
    """Generate rotation compliance insights."""
    insights = []

    score = rotation_compliance.get("score_0_to_100", 100)
    flags = rotation_compliance.get("flags", [])

    # Poor rotation score
    if score < 70:
        insights.append(
            {
                "severity": "WARNING",
                "priority": PRIORITY_CRITICAL,
                "message": "Rotation issues impacting team play",
                "contributing_factors": [
                    f"Rotation score: {score:.0f}/100",
                    "Poor rotation = double commits & open nets",
                    f"Violation flags: {', '.join(flags) if flags else 'various'}",
                ],
                "recommendation": (
                    "After every touch, rotate far post. Never cut "
                    "in front of a teammate who has momentum toward ball."
                ),
                "evidence": {"rotation_score": score, "violation_flags": flags},
            }
        )

    # Specific rotation violations
    if "double_commit" in str(flags):
        insights.append(
            {
                "severity": "SUGGESTION",
                "priority": PRIORITY_HIGH,
                "message": "Double commits detected",
                "contributing_factors": [
                    "Multiple instances of two players challenging simultaneously",
                    "Leaves net completely open on counter",
                ],
                "recommendation": (
                    "If teammate is closer, shadow the play instead of "
                    "challenging. Be ready to pick up the second touch."
                ),
                "evidence": {"violation_type": "double_commit", "flags": flags},
            }
        )

    return insights


def _analyze_fundamentals_insights(
    fundamentals: dict, player_id: str
) -> list[dict[str, Any]]:
    """Generate fundamentals performance insights."""
    insights = []

    shooting_percentage = fundamentals.get("shooting_percentage", 0)
    shots = fundamentals.get("shots", 0)

    # Low shooting percentage with reasonable shot count
    if shooting_percentage < 20 and shots >= 5:
        insights.append(
            {
                "severity": "SUGGESTION",
                "priority": PRIORITY_HIGH,
                "message": "Shot quality needs improvement",
                "contributing_factors": [
                    f"{shooting_percentage:.0f}% shot conversion ({shots} attempts)",
                    "Low percentage suggests poor shot selection or placement",
                ],
                "recommendation": (
                    "Wait for better angles before shooting. A pass that "
                    "creates a 50% chance is better than a 10% shot."
                ),
                "evidence": {
                    "shooting_percentage": shooting_percentage,
                    "shots": shots,
                },
            }
        )

    # High shooting percentage
    if shooting_percentage > 40 and shots >= 3:
        insights.append(
            {
                "severity": "INFO",
                "priority": PRIORITY_INFO,
                "message": "Excellent shot selection",
                "contributing_factors": [
                    f"{shooting_percentage:.0f}% shooting accuracy",
                    "Taking high-quality opportunities only",
                ],
                "recommendation": (
                    "Great discipline! Consider if you could create "
                    "even more high-% chances with better positioning."
                ),
                "evidence": {
                    "shooting_percentage": shooting_percentage,
                    "shots": shots,
                },
            }
        )

    return insights


def _analyze_challenges_insights(
    challenges: dict, player_id: str
) -> list[dict[str, Any]]:
    """Generate challenge/50-50 insights."""
    insights = []

    first_to_ball_pct = challenges.get("first_to_ball_pct", 0)
    wins = challenges.get("wins", 0)
    contests = challenges.get("contests", 0)

    # Poor first-to-ball rate
    if first_to_ball_pct < 40 and contests >= 10:
        insights.append(
            {
                "severity": "SUGGESTION",
                "priority": PRIORITY_MEDIUM,
                "message": "Late to ball in challenges",
                "contributing_factors": [
                    f"First to ball only {first_to_ball_pct:.0f}% of the time",
                    "Being second to ball = reactive instead of proactive",
                ],
                "recommendation": (
                    "Read bounces earlier and commit sooner. Position "
                    "closer to where the ball will be, not where it is."
                ),
                "evidence": {
                    "first_to_ball_pct": first_to_ball_pct,
                    "contests": contests,
                },
            }
        )

    # Good challenge success rate
    if contests > 0:
        win_rate = (wins / contests) * 100
        if win_rate > 60 and contests >= 8:
            insights.append(
                {
                    "severity": "INFO",
                    "priority": PRIORITY_INFO,
                    "message": "Strong challenge mechanics",
                    "contributing_factors": [
                        f"{win_rate:.0f}% challenge win rate",
                        f"Won {wins} of {contests} contested situations",
                    ],
                    "recommendation": (
                        "Solid 50/50 mechanics. Now focus on choosing "
                        "which challenges to take for maximum impact."
                    ),
                    "evidence": {
                        "challenge_win_rate": win_rate,
                        "wins": wins,
                        "contests": contests,
                    },
                }
            )

    return insights


def _analyze_team_fundamentals(
    blue_data: dict, orange_data: dict
) -> list[dict[str, Any]]:
    """Generate team fundamentals insights."""
    insights = []

    blue_shooting = blue_data.get("fundamentals", {}).get("shooting_percentage", 0)
    orange_shooting = orange_data.get("fundamentals", {}).get("shooting_percentage", 0)

    # Significant shooting percentage advantage
    if blue_shooting - orange_shooting > 15:
        insights.append(
            {
                "severity": "INFO",
                "message": (
                    f"BLUE team shooting advantage: {blue_shooting:.1f}% "
                    f"vs {orange_shooting:.1f}%"
                ),
                "evidence": {
                    "blue_shooting": blue_shooting,
                    "orange_shooting": orange_shooting,
                },
            }
        )
    elif orange_shooting - blue_shooting > 15:
        insights.append(
            {
                "severity": "INFO",
                "message": (
                    f"ORANGE team shooting advantage: {orange_shooting:.1f}% "
                    f"vs {blue_shooting:.1f}%"
                ),
                "evidence": {
                    "blue_shooting": blue_shooting,
                    "orange_shooting": orange_shooting,
                },
            }
        )

    return insights


def _analyze_team_boost(blue_data: dict, orange_data: dict) -> list[dict[str, Any]]:
    """Generate team boost economy insights."""
    insights = []

    blue_stolen = blue_data.get("boost", {}).get("boost_stolen", 0)
    orange_stolen = orange_data.get("boost", {}).get("boost_stolen", 0)

    # Boost denial advantage
    if blue_stolen - orange_stolen > 500:
        insights.append(
            {
                "severity": "INFO",
                "message": (
                    f"BLUE team boost control advantage: {blue_stolen:.0f} "
                    f"vs {orange_stolen:.0f} boost stolen"
                ),
                "evidence": {
                    "blue_stolen": blue_stolen,
                    "orange_stolen": orange_stolen,
                },
            }
        )
    elif orange_stolen - blue_stolen > 500:
        insights.append(
            {
                "severity": "INFO",
                "message": (
                    f"ORANGE team boost control advantage: {orange_stolen:.0f} "
                    f"vs {blue_stolen:.0f} boost stolen"
                ),
                "evidence": {
                    "blue_stolen": blue_stolen,
                    "orange_stolen": orange_stolen,
                },
            }
        )

    return insights


def _analyze_team_kickoffs(blue_data: dict, orange_data: dict) -> list[dict[str, Any]]:
    """Generate team kickoff insights."""
    insights = []

    blue_first = blue_data.get("kickoffs", {}).get("first_possession", 0)
    orange_first = orange_data.get("kickoffs", {}).get("first_possession", 0)
    total_kickoffs = blue_first + orange_first

    # Kickoff advantage
    if total_kickoffs >= 3:
        if blue_first >= orange_first + 2:
            insights.append(
                {
                    "severity": "INFO",
                    "message": (
                        f"BLUE kickoff advantage: won first possession "
                        f"{blue_first}/{total_kickoffs} times"
                    ),
                    "evidence": {
                        "blue_first_possession": blue_first,
                        "orange_first_possession": orange_first,
                    },
                }
            )
        elif orange_first >= blue_first + 2:
            insights.append(
                {
                    "severity": "INFO",
                    "message": (
                        f"ORANGE kickoff advantage: won first possession "
                        f"{orange_first}/{total_kickoffs} times"
                    ),
                    "evidence": {
                        "blue_first_possession": blue_first,
                        "orange_first_possession": orange_first,
                    },
                }
            )

    return insights


def _analyze_team_positioning(
    blue_data: dict, orange_data: dict
) -> list[dict[str, Any]]:
    """Generate team positioning insights."""
    insights = []

    blue_ahead = blue_data.get("positioning", {}).get("ahead_ball_pct", 0)
    orange_ahead = orange_data.get("positioning", {}).get("ahead_ball_pct", 0)

    # Team overcommit warning
    if blue_ahead > 50 and orange_ahead > 50:
        insights.append(
            {
                "severity": "WARNING",
                "message": (
                    "Both teams showing high ahead-of-ball positioning - "
                    "consider more defensive structure"
                ),
                "evidence": {
                    "blue_ahead_ball_pct": blue_ahead,
                    "orange_ahead_ball_pct": orange_ahead,
                },
            }
        )

    return insights
