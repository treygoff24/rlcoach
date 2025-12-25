"""Physics constants for Rocket League analysis.

This module centralizes game physics constants used across analysis modules.
All values are in Unreal Units (UU) unless otherwise noted.

References:
- RLBot wiki: https://wiki.rlbot.org/botmaking/useful-game-values/
- Community research and empirical measurements
"""

from __future__ import annotations

# =============================================================================
# Unit Conversions
# =============================================================================

# 1 UU ≈ 1.9 cm = 0.019 m (empirical measurement)
UU_TO_METERS: float = 0.019

# Convert UU/s to km/h: multiply by 0.019 (m per UU) * 3.6 (s/h / m/km)
UU_S_TO_KPH: float = UU_TO_METERS * 3.6  # ≈ 0.0684


# =============================================================================
# Speed Thresholds (UU/s)
# =============================================================================

# Speed categories (aligned with ballchasing/RL community standards)
SLOW_SPEED_MAX_UU_S: float = 1400.0  # Below this is "slow"
BOOST_SPEED_MAX_UU_S: float = 2200.0  # Below this is "boost speed"
SUPERSONIC_SPEED_UU_S: float = 2200.0  # At or above this is "supersonic"

# Supersonic threshold squared (for avoiding sqrt in hot paths)
SUPERSONIC_SPEED_SQUARED: float = SUPERSONIC_SPEED_UU_S**2


# =============================================================================
# Gravity and Physics
# =============================================================================

# Vertical gravity acceleration
GRAVITY_UU_S2: float = -650.0  # UU/s^2 downward

# Ball physics
BALL_RADIUS_UU: float = 93.15  # Ball collision radius
BALL_MAX_SPEED_UU_S: float = 6000.0  # Maximum ball speed


# =============================================================================
# Car Physics
# =============================================================================

# Car dimensions (approximate for Octane)
CAR_HEIGHT_UU: float = 17.0  # Height of car hitbox center when on ground
CAR_MAX_SPEED_UU_S: float = 2300.0  # Max car speed without boost
CAR_BOOST_ACCELERATION_UU_S2: float = 991.67  # Acceleration when boosting

# Jump physics
JUMP_Z_VELOCITY_UU_S: float = 292.0  # Initial z velocity on jump
DOUBLE_JUMP_Z_VELOCITY_UU_S: float = 292.0  # Same for double jump


# =============================================================================
# Ground and Air Detection
# =============================================================================

# Height thresholds for ground detection
GROUND_HEIGHT_THRESHOLD_UU: float = 25.0  # Below this = on ground
AIRBORNE_MIN_HEIGHT_UU: float = 50.0  # Minimum height for "meaningful" airborne

# Air classifications
LOW_AIR_MAX_HEIGHT_UU: float = 200.0  # Below this = low air
HIGH_AIR_MIN_HEIGHT_UU: float = 200.0  # Above this = high air
AERIAL_HEIGHT_THRESHOLD_UU: float = 200.0  # Height for aerial classification


# =============================================================================
# Boost Amounts
# =============================================================================

# Boost capacity
MAX_BOOST: float = 100.0

# Boost pad amounts
BIG_PAD_BOOST: float = 100.0
SMALL_PAD_BOOST: float = 12.0

# Boost consumption rate
BOOST_CONSUMPTION_PER_SECOND: float = 33.3  # Approximate usage rate


# =============================================================================
# xG Model Constants
# =============================================================================

# Shot speed thresholds for xG calculations (in KPH for readability)
POWER_SHOT_SPEED_KPH: float = 100.0  # High-speed shot threshold
OPTIMAL_SHOT_SPEED_KPH: float = 70.0  # Optimal shot speed for xG
MIN_SHOT_SPEED_KPH: float = 20.0  # Minimum speed for a meaningful shot


# =============================================================================
# Detection Thresholds
# =============================================================================

# Flip/mechanic detection
FLIP_ANGULAR_THRESHOLD_RAD_S: float = 5.0  # Angular velocity for flip detection
JUMP_COOLDOWN_S: float = 0.1  # Minimum time between jump detections

# Wavedash detection
WAVEDASH_LANDING_WINDOW_S: float = 0.2  # Time window after flip for wavedash
WAVEDASH_SPEED_BOOST_RATIO: float = 1.15  # Speed increase indicating wavedash

# Recovery detection
STABLE_VELOCITY_THRESHOLD_UU_S: float = 100.0  # Velocity change for "stable"
STABLE_FRAMES_REQUIRED: int = 3  # Frames of stability for control regained


# =============================================================================
# Distance Thresholds
# =============================================================================

# Shadow defense
SHADOW_MAX_DISTANCE_UU: float = 3000.0  # Max distance to be effective shadow
SHADOW_ANGLE_TOLERANCE_DEG: float = 30.0  # Angle tolerance for good shadow

# Defensive positioning
LAST_DEFENDER_BUFFER_UU: float = 800.0  # Distance behind teammates for "last"
