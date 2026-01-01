"""Mechanics detection module - infer jump/flip/dodge from physics state."""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from enum import Enum

from ..events.utils import is_toward_opponent_goal
from ..field_constants import FIELD, Vec3
from ..parser.types import Frame, PlayerFrame, Rotation

logger = logging.getLogger(__name__)


class MechanicType(Enum):
    """Types of mechanics that can be detected."""

    # Existing mechanics
    JUMP = "jump"
    DOUBLE_JUMP = "double_jump"
    FLIP = "flip"
    DODGE = "dodge"
    WAVEDASH = "wavedash"
    FLIP_CANCEL = "flip_cancel"
    AERIAL = "aerial"
    HALF_FLIP = "half_flip"
    SPEEDFLIP = "speedflip"

    # Phase 1 - New mechanics
    FAST_AERIAL = "fast_aerial"
    FLIP_RESET = "flip_reset"
    AIR_ROLL = "air_roll"

    # Phase 2 - New mechanics
    DRIBBLE = "dribble"
    FLICK = "flick"
    MUSTY_FLICK = "musty_flick"
    CEILING_SHOT = "ceiling_shot"
    POWER_SLIDE = "power_slide"

    # Phase 3 - New mechanics
    GROUND_PINCH = "ground_pinch"
    DOUBLE_TOUCH = "double_touch"
    REDIRECT = "redirect"
    STALL = "stall"

    # Phase 5 - Advanced mechanics
    SKIM = "skim"  # Underside contact + ball acceleration toward goal
    PSYCHO = "psycho"  # Backboard slam + invert + skim combo


@dataclass(frozen=True)
class MechanicEvent:
    """A detected mechanic event."""

    timestamp: float
    player_id: str
    mechanic_type: MechanicType
    position: Vec3
    velocity: Vec3
    # Additional context
    direction: str | None = None  # forward, backward, left, right, diagonal
    height: float = 0.0  # height above ground when mechanic started
    duration: float | None = None  # how long the mechanic lasted (for flips)
    # New fields for extended mechanics
    ball_position: Vec3 | None = None  # For ball-related mechanics (flicks, pinches)
    ball_velocity_change: float | None = None  # Velocity delta for flicks/pinches
    boost_used: int | None = None  # Boost consumed for fast aerial tracking


@dataclass
class PlayerMechanicsState:
    """Track mechanics state for a single player across frames."""

    # Jump tracking
    is_airborne: bool = False
    airborne_start_time: float | None = None
    has_jumped: bool = False  # First jump used
    has_double_jumped: bool = False  # Second jump used
    has_flipped: bool = False  # Flip used (consumes second jump)
    last_ground_time: float = 0.0

    # Physics tracking for derivative detection
    prev_z_velocity: float = 0.0
    prev_z_position: float = 17.0  # Car ground level
    prev_velocity: Vec3 | None = None  # Full velocity for car-local transforms
    prev_angular_x: float = 0.0  # pitch rate
    prev_angular_y: float = 0.0  # yaw rate
    prev_angular_z: float = 0.0  # roll rate (for flip discrimination)
    prev_rotation_pitch: float = 0.0
    prev_rotation_yaw: float = 0.0
    prev_rotation_roll: float = 0.0

    # Flip tracking
    flip_start_time: float | None = None
    flip_initial_rotation: tuple[float, float, float] | None = None
    flip_direction: str | None = None  # Direction of most recent flip
    flip_cancel_detected: bool = False  # Was flip cancelled?
    # Flip cancel persistence (Phase 8)
    flip_pitch_intent: int = 0  # +1 = front flip, -1 = back flip, 0 = side
    flip_cancel_start_time: float | None = None  # When cancel criteria first met
    flip_cancel_confirmed: bool = False  # Cancel persisted for 3+ frames
    # Speedflip tracking (Phase 10)
    vel_at_flip_start: Vec3 | None = None  # For forward accel check
    boost_used_since_flip: int = 0

    # Landing detection
    last_velocity_z: float = 0.0

    # Half-flip/speedflip tracking
    initial_yaw: float = 0.0  # Yaw at flip start for 180° detection
    prev_yaw: float = 0.0  # Previous yaw for rotation tracking
    # Wavedash tracking (Phase 4)
    pitch_at_flip_start: float = 0.0  # For dash setup check
    roll_at_flip_start: float = 0.0

    # === NEW: Extended mechanics tracking ===

    # Fast aerial tracking
    first_jump_time: float | None = None
    second_jump_time: float | None = None  # When second jump/flip occurred
    boost_at_first_jump: int = 0
    boost_used_since_jump: int = 0
    boost_used_in_window: bool = False  # Boost used within 0.3s of first jump
    fast_aerial_detected: bool = False  # Prevent duplicate detections
    # Phase 7: Same-frame boost check
    recent_boost_deltas: list = None  # list of (timestamp, delta)

    # Flip reset tracking
    flip_reset_touch_time: float | None = None  # Time of underside ball contact
    flip_available_from_reset: bool = False  # Can flip again after reset

    # Air roll tracking
    air_roll_start_time: float | None = None
    is_air_rolling: bool = False

    # Dribble tracking
    dribble_start_time: float | None = None
    is_dribbling: bool = False
    ball_speed_at_dribble_start: float = 0.0
    ball_speed_at_flip_start: float = 0.0  # For flick detection
    ball_z_velocity_at_flip_start: float = 0.0  # For musty flick detection

    # Power slide tracking
    power_slide_start_time: float | None = None
    is_power_sliding: bool = False

    # Ceiling shot tracking (Phase 5)
    last_ceiling_touch_time: float | None = None
    ceiling_contact_frames: int = 0  # Persistence counter
    has_ceiling_flip: bool = False  # Ceiling-granted flip available
    had_surface_contact_since_ceiling: bool = False  # Invalidates ceiling flip
    left_ceiling_yet: bool = False  # Track ceiling→falling transition
    flip_after_ceiling: bool = False  # Flip occurred after ceiling contact

    # Double touch tracking
    aerial_touch_count_since_ground: int = 0
    first_aerial_touch_time: float | None = None
    last_touch_timestamp: float | None = None  # For touch debounce
    wall_bounce_detected: bool = False

    # Stall tracking
    stall_start_time: float | None = None
    is_stalling: bool = False

    # Psycho tracking (Phase 14)
    psycho_state: str | None = None  # "INVERTING" or "SKIM_READY"
    psycho_slam_time: float | None = None  # When backboard slam occurred
    psycho_waiting_for_bounce: bool = False  # Waiting for wall bounce after slam

    # Ball tracking for velocity deltas
    prev_ball_speed: float = 0.0
    prev_ball_z_velocity: float = 0.0
    prev_ball_velocity: Vec3 | None = None  # Full velocity for redirect detection

    # Boost tracking
    prev_boost_amount: int = 100


# Physics constants for detection thresholds
GROUND_HEIGHT_THRESHOLD = 25.0  # Car is on ground if z < this
JUMP_Z_VELOCITY_THRESHOLD = 250.0  # Minimum z velocity spike for jump (UU/s)
# Lowered from 292 to 250 to account for gravity decay between 30 Hz samples
DOUBLE_JUMP_Z_VELOCITY_THRESHOLD = 250.0  # Same threshold for double jump
FLIP_ANGULAR_THRESHOLD = 3.5  # Radians/second rotation rate for flip detection
# Lowered from 5.0 to 3.5 - 91% of max was too tight, missed early cancels
JUMP_COOLDOWN = 0.1  # Minimum time between jump detections (seconds)
AERIAL_HEIGHT_THRESHOLD = 200.0  # Height threshold for aerial classification
WAVEDASH_LANDING_WINDOW_MIN = 0.05  # Min time after flip for wavedash (tight!)
WAVEDASH_LANDING_WINDOW_MAX = 0.125  # Max time - reduced from 0.4
WAVEDASH_SPEED_GAIN_MIN = 100.0  # Minimum forward speed gain for wavedash

# Half-flip and speedflip detection constants
FLIP_CANCEL_PITCH_REVERSAL_THRESHOLD = 3.0  # rad/s pitch rate reversal for flip cancel
FLIP_CANCEL_WINDOW = 0.25  # Time window after flip to detect cancel
HALF_FLIP_YAW_CHANGE_THRESHOLD = 2.5  # ~143 degrees in radians for half-flip
HALF_FLIP_DETECTION_WINDOW = 0.6  # Time window to complete half-flip
SPEEDFLIP_CANCEL_WINDOW = 0.10  # Speedflip cancel within 100ms (~3 frames at 30 Hz)

# === NEW: Extended mechanics thresholds ===

# Fast aerial detection
FAST_AERIAL_BOOST_WINDOW = (
    0.3  # seconds - boost must be used within this window after jump
)
FAST_AERIAL_SECOND_JUMP_WINDOW = 0.5  # seconds - second jump/flip within this window
FAST_AERIAL_HEIGHT_THRESHOLD = 300.0  # UU - must reach this height
FAST_AERIAL_TIME_TO_HEIGHT = 1.0  # seconds - must reach height within this time

# Flip reset detection
FLIP_RESET_PROXIMITY = (
    120.0  # UU - ball-car distance for contact (ball radius ~93 + margin)
)
FLIP_RESET_DOT_THRESHOLD = 0.7  # dot product threshold (ball roughly under car)
FLIP_RESET_WINDOW = 2.0  # seconds - max time between touch and reset flip

# Air roll detection
AIR_ROLL_RATE_THRESHOLD = 2.0  # rad/s - minimum roll rate for air roll
AIR_ROLL_MIN_DURATION = 0.3  # seconds - minimum sustained duration
AIR_ROLL_FLIP_EXCLUSION_WINDOW = 0.2  # seconds - skip air roll check after flip

# Dribble detection
DRIBBLE_XY_RADIUS = 100.0  # UU - ball within this XY radius of car center
DRIBBLE_Z_MIN = (
    90.0  # UU - minimum ball Z above car (car roof ~17 + ball radius ~93 - margin)
)
DRIBBLE_Z_MAX = 180.0  # UU - maximum ball Z above car
DRIBBLE_CAR_HEIGHT_MAX = 50.0  # UU - car must be grounded (not on wall)
DRIBBLE_RELATIVE_VELOCITY_MAX = (
    300.0  # UU/s - max relative velocity between ball and car
)
DRIBBLE_MIN_DURATION = 0.5  # seconds - minimum dribble duration

# Flick detection
FLICK_VELOCITY_GAIN = 500.0  # UU/s - minimum ball velocity gain for flick
FLICK_DETECTION_WINDOW = 0.3  # seconds - window after flip to check for flick
MUSTY_FLICK_Z_VELOCITY_GAIN = 800.0  # UU/s - minimum ball Z velocity gain for musty

# Ceiling shot detection
CEILING_HEIGHT_THRESHOLD = 2040.0  # UU - closer to actual ceiling (2044 UU)
CEILING_SHOT_WINDOW = 3.0  # seconds - max time between ceiling touch and ball touch

# Power slide detection
POWER_SLIDE_VELOCITY_THRESHOLD = 500.0  # UU/s - minimum sideways velocity
POWER_SLIDE_MIN_DURATION = 0.2  # seconds - minimum duration

# Ground pinch detection
GROUND_PINCH_HEIGHT_MAX = 100.0  # UU - ball must be near ground
GROUND_PINCH_EXIT_VELOCITY_MIN = 3000.0  # UU/s - minimum post-touch speed
GROUND_PINCH_VELOCITY_DELTA_MIN = 1500.0  # UU/s - minimum velocity gain from touch

# Double touch detection
DOUBLE_TOUCH_WINDOW = 3.0  # seconds - max time between touches
DOUBLE_TOUCH_HEIGHT_MIN = 300.0  # UU - aligned with AERIAL_HEIGHT_THRESHOLD
WALL_PROXIMITY = 200.0  # UU - distance from wall to detect wall bounce
TOUCH_DEBOUNCE_TIME = 0.1  # seconds - min time between touches to count as separate

# Redirect detection
REDIRECT_HEIGHT_MIN = 300.0  # UU - minimum height for redirect (aerial touch)
REDIRECT_ANGLE_THRESHOLD = 0.785  # radians (45 degrees)
REDIRECT_MIN_BALL_SPEED = 500.0  # UU/s - minimum ball speed for redirect

# Stall detection
STALL_ROLL_RATE_MIN = 3.0  # rad/s - minimum roll rate
STALL_YAW_RATE_MIN = 2.0  # rad/s - minimum yaw rate
STALL_VERTICAL_VELOCITY_MAX = 100.0  # UU/s - max vertical velocity (near hover)
STALL_HORIZONTAL_VELOCITY_MAX = 500.0  # UU/s - max horizontal velocity
STALL_HEIGHT_MIN = 300.0  # UU - minimum height for stall
STALL_MIN_DURATION = 0.15  # seconds - minimum duration

# Ball contact proximity (for inline touch detection)
BALL_CONTACT_PROXIMITY = 200.0  # UU - distance threshold for ball contact

# Skim detection (Phase 13)
SKIM_DOT_THRESHOLD = -0.7  # Ball below car (underside contact)

# Psycho detection (Phase 14)
PSYCHO_WINDOW = 3.0  # seconds - max time from backboard slam to skim
PSYCHO_INVERT_THRESHOLD = -0.5  # car_up · world_up < this = inverted


def _get_rotation_values(rotation: Rotation | Vec3) -> tuple[float, float, float]:
    """Extract pitch, yaw, roll from rotation (handles both formats).

    Args:
        rotation: Rotation object (Rotation dataclass or legacy Vec3)

    Returns:
        Tuple of (pitch, yaw, roll) in radians

    Note:
        Returns (0.0, 0.0, 0.0) for unrecognized types with a warning.
    """
    if isinstance(rotation, Rotation):
        return (rotation.pitch, rotation.yaw, rotation.roll)
    elif isinstance(rotation, Vec3):
        # Legacy format: x=pitch, y=yaw, z=roll
        return (rotation.x, rotation.y, rotation.z)

    # Log warning for unexpected types
    logger.warning(
        "Unrecognized rotation type %s, defaulting to (0, 0, 0)",
        type(rotation).__name__,
    )
    return (0.0, 0.0, 0.0)


def _get_flip_direction(
    velocity: Vec3, rotation_change: tuple[float, float, float], yaw: float
) -> str:
    """Determine flip direction based on velocity and rotation change."""
    pitch_rate, yaw_rate, roll_rate = rotation_change

    # Dominant rotation axis determines flip type
    if abs(pitch_rate) > abs(roll_rate) and abs(pitch_rate) > abs(yaw_rate):
        return "forward" if pitch_rate > 0 else "backward"
    elif abs(roll_rate) > abs(pitch_rate) and abs(roll_rate) > abs(yaw_rate):
        return "left" if roll_rate > 0 else "right"
    else:
        # Mixed or diagonal flip
        return "diagonal"


def _normalize_angle(angle: float) -> float:
    """Normalize angle to [-pi, pi] range."""
    # Use modulo for efficiency - handles any magnitude angle
    angle = (angle + math.pi) % (2 * math.pi) - math.pi
    return angle


def _rotation_to_up_vector(rotation: Rotation | Vec3) -> Vec3:
    """Convert car rotation to up vector (pointing out of car roof).

    Uses Euler angles to compute the up vector in world coordinates.
    The up vector is the Z-axis of the car's local coordinate system
    transformed to world coordinates.

    Args:
        rotation: Rotation with pitch, yaw, roll in radians

    Returns:
        Vec3 unit vector pointing "up" from the car's roof
    """
    pitch, yaw, roll = _get_rotation_values(rotation)

    # Compute rotation matrix components
    # Up vector is the third column of the rotation matrix
    # For Euler angles (pitch, yaw, roll) in ZYX order:
    cp = math.cos(pitch)
    sp = math.sin(pitch)
    cy = math.cos(yaw)
    sy = math.sin(yaw)
    cr = math.cos(roll)
    sr = math.sin(roll)

    # Up vector (Z-axis of rotated frame)
    up_x = cy * sp * cr + sy * sr
    up_y = sy * sp * cr - cy * sr
    up_z = cp * cr

    return Vec3(up_x, up_y, up_z)


def _distance(a: Vec3, b: Vec3) -> float:
    """Calculate Euclidean distance between two Vec3 points."""
    dx = a.x - b.x
    dy = a.y - b.y
    dz = a.z - b.z
    return math.sqrt(dx * dx + dy * dy + dz * dz)


def _magnitude(v: Vec3) -> float:
    """Calculate magnitude of a Vec3."""
    return math.sqrt(v.x * v.x + v.y * v.y + v.z * v.z)


def _dot(a: Vec3, b: Vec3) -> float:
    """Calculate dot product of two Vec3."""
    return a.x * b.x + a.y * b.y + a.z * b.z


def _normalize_vec(v: Vec3) -> Vec3:
    """Normalize a Vec3 to unit length."""
    mag = _magnitude(v)
    if mag < 0.0001:
        return Vec3(0.0, 0.0, 0.0)
    return Vec3(v.x / mag, v.y / mag, v.z / mag)


def _cross(a: Vec3, b: Vec3) -> Vec3:
    """Calculate cross product of two Vec3."""
    return Vec3(
        a.y * b.z - a.z * b.y,
        a.z * b.x - a.x * b.z,
        a.x * b.y - a.y * b.x,
    )


def _rotation_to_forward_vector(rotation: Rotation | Vec3) -> Vec3:
    """Convert car rotation to forward vector (pointing out of car nose).

    Uses Euler angles to compute the forward vector in world coordinates.
    The forward vector is the X-axis of the car's local coordinate system
    transformed to world coordinates.

    Args:
        rotation: Rotation with pitch, yaw, roll in radians

    Returns:
        Vec3 unit vector pointing "forward" from the car's nose
    """
    pitch, yaw, roll = _get_rotation_values(rotation)

    # Compute rotation matrix components
    # Forward vector is the first column of the rotation matrix
    # For Euler angles (pitch, yaw, roll) in ZYX order:
    cp = math.cos(pitch)
    sp = math.sin(pitch)
    cy = math.cos(yaw)
    sy = math.sin(yaw)

    # Forward vector (X-axis of rotated frame)
    # Simplified: only depends on pitch and yaw for forward direction
    forward_x = cy * cp
    forward_y = sy * cp
    forward_z = -sp

    return Vec3(forward_x, forward_y, forward_z)


def detect_mechanics_for_player(
    frames: list[Frame],
    player_id: str,
) -> list[MechanicEvent]:
    """Detect mechanics for a single player from frame data.

    Args:
        frames: Normalized frame data
        player_id: Player ID to analyze

    Returns:
        List of detected mechanic events
    """
    events: list[MechanicEvent] = []
    state = PlayerMechanicsState()

    prev_frame: Frame | None = None
    prev_player: PlayerFrame | None = None

    # Lookup player team (needed for redirect goal direction check)
    player_team: int | None = None
    for frame in frames:
        for p in frame.players:
            if p.player_id == player_id:
                player_team = p.team
                break
        if player_team is not None:
            break

    for frame in frames:
        # Find player in this frame
        player: PlayerFrame | None = None
        for p in frame.players:
            if p.player_id == player_id:
                player = p
                break

        if player is None:
            prev_frame = frame
            continue

        timestamp = frame.timestamp
        pos = player.position
        vel = player.velocity
        rot = player.rotation

        pitch, yaw, roll = _get_rotation_values(rot)

        # Calculate derivatives if we have previous frame
        if prev_player is not None and prev_frame is not None:
            dt = max(timestamp - prev_frame.timestamp, 0.001)  # Prevent div by zero

            # Rotation rate (angular velocity approximation)
            # Normalize angle deltas to handle ±π wraparound
            pitch_rate = _normalize_angle(pitch - state.prev_rotation_pitch) / dt
            yaw_rate = _normalize_angle(yaw - state.prev_rotation_yaw) / dt
            roll_rate = _normalize_angle(roll - state.prev_rotation_roll) / dt

            # Detect ground state
            was_airborne = state.is_airborne
            is_on_ground = pos.z < GROUND_HEIGHT_THRESHOLD or player.is_on_ground

            if is_on_ground and was_airborne:
                # Just landed
                # Check for wavedash (Phase 4 fix)
                # Tight window + pitch/roll setup + speed gain
                if state.flip_start_time is not None:
                    landing_window = timestamp - state.flip_start_time
                    if (
                        WAVEDASH_LANDING_WINDOW_MIN
                        <= landing_window
                        <= WAVEDASH_LANDING_WINDOW_MAX
                    ):
                        # Check pitch/roll at flip time (dash setup)
                        flip_pitch = state.pitch_at_flip_start
                        flip_roll = state.roll_at_flip_start
                        is_dash_setup = (
                            abs(flip_pitch) > 0.2 or abs(flip_roll) > 0.2
                        )  # ~11 degrees

                        # Check speed gain in car's forward direction
                        car_forward = _rotation_to_forward_vector(rot)
                        forward_speed_now = _dot(vel, car_forward)
                        forward_speed_before = (
                            _dot(state.prev_velocity, car_forward)
                            if state.prev_velocity
                            else 0
                        )

                        if (
                            is_dash_setup
                            and forward_speed_now
                            > forward_speed_before + WAVEDASH_SPEED_GAIN_MIN
                        ):
                            events.append(
                                MechanicEvent(
                                    timestamp=timestamp,
                                    player_id=player_id,
                                    mechanic_type=MechanicType.WAVEDASH,
                                    position=pos,
                                    velocity=vel,
                                    height=0.0,
                                    duration=landing_window,
                                )
                            )

                # Reset airborne state
                state.is_airborne = False
                state.has_jumped = False
                state.has_double_jumped = False
                state.has_flipped = False
                state.airborne_start_time = None
                state.flip_start_time = None
                state.last_ground_time = timestamp

                # Reset extended mechanics state on landing
                state.first_jump_time = None
                state.second_jump_time = None
                state.boost_at_first_jump = 0
                state.boost_used_since_jump = 0
                state.boost_used_in_window = False
                state.fast_aerial_detected = False
                state.flip_reset_touch_time = None
                state.flip_available_from_reset = False
                state.aerial_touch_count_since_ground = 0
                state.first_aerial_touch_time = None
                state.last_touch_timestamp = None
                state.wall_bounce_detected = False

                # End air roll segment on landing
                if state.is_air_rolling and state.air_roll_start_time is not None:
                    duration = timestamp - state.air_roll_start_time
                    if duration >= AIR_ROLL_MIN_DURATION:
                        events.append(
                            MechanicEvent(
                                timestamp=state.air_roll_start_time,
                                player_id=player_id,
                                mechanic_type=MechanicType.AIR_ROLL,
                                position=pos,
                                velocity=vel,
                                height=pos.z,
                                duration=duration,
                            )
                        )
                state.is_air_rolling = False
                state.air_roll_start_time = None

                # Reset stall state on landing
                state.is_stalling = False
                state.stall_start_time = None

                # Reset ceiling touch time on landing (prevents false positives)
                state.last_ceiling_touch_time = None

            elif not is_on_ground and not was_airborne:
                # Just became airborne
                state.is_airborne = True
                state.airborne_start_time = timestamp

            elif not is_on_ground:
                # Already airborne - detect mechanics

                # Jump detection: car-local impulse detection
                # Uses dot(Δv, car_up) to work on walls, ramps, tilted cars
                car_up = _rotation_to_up_vector(rot)
                if state.prev_velocity is not None:
                    delta_v = Vec3(
                        vel.x - state.prev_velocity.x,
                        vel.y - state.prev_velocity.y,
                        vel.z - state.prev_velocity.z,
                    )
                    impulse_in_car_up = _dot(delta_v, car_up)
                else:
                    # Fallback to world-Z for first frame
                    impulse_in_car_up = vel.z - state.prev_z_velocity

                time_since_ground = timestamp - state.last_ground_time

                if (
                    impulse_in_car_up > JUMP_Z_VELOCITY_THRESHOLD
                    and time_since_ground > JUMP_COOLDOWN
                ):

                    # Check rotation rate to distinguish jump vs flip
                    total_rot_rate = math.sqrt(
                        pitch_rate * pitch_rate + roll_rate * roll_rate
                    )

                    if total_rot_rate > FLIP_ANGULAR_THRESHOLD:
                        # This is a flip/dodge - but a flip requires a jump first!
                        # In RL, you jump then flip, so we count the jump too
                        if not state.has_flipped:
                            # First, count the jump that preceded this flip
                            # (flips consume the second jump)
                            if not state.has_jumped:
                                state.has_jumped = True
                                # Track for fast aerial detection
                                state.first_jump_time = timestamp
                                state.boost_at_first_jump = player.boost_amount
                                state.boost_used_since_jump = 0
                                events.append(
                                    MechanicEvent(
                                        timestamp=timestamp,
                                        player_id=player_id,
                                        mechanic_type=MechanicType.JUMP,
                                        position=pos,
                                        velocity=vel,
                                        height=pos.z,
                                    )
                                )

                            state.has_flipped = True
                            state.second_jump_time = timestamp  # For fast aerial
                            state.flip_start_time = timestamp
                            state.flip_cancel_detected = False
                            state.flip_cancel_confirmed = False  # Reset for new flip
                            # Track if flip occurred after ceiling contact
                            if state.has_ceiling_flip:
                                state.flip_after_ceiling = True
                            state.flip_cancel_start_time = None
                            # Record orientation at flip start (for wavedash/speedflip)
                            state.pitch_at_flip_start = pitch
                            state.roll_at_flip_start = roll
                            state.vel_at_flip_start = vel
                            state.boost_used_since_flip = 0
                            # Record pitch intent for flip cancel detection
                            state.flip_pitch_intent = (
                                1 if pitch_rate > 0 else -1 if pitch_rate < 0 else 0
                            )
                            # Record ball state for flick/musty detection
                            if frame.ball is not None:
                                state.ball_speed_at_flip_start = _magnitude(
                                    frame.ball.velocity
                                )
                                state.ball_z_velocity_at_flip_start = (
                                    frame.ball.velocity.z
                                )
                            # End air roll on flip (flip rotation != air roll)
                            if state.is_air_rolling and state.air_roll_start_time:
                                duration = timestamp - state.air_roll_start_time
                                if duration >= AIR_ROLL_MIN_DURATION:
                                    events.append(
                                        MechanicEvent(
                                            timestamp=state.air_roll_start_time,
                                            player_id=player_id,
                                            mechanic_type=MechanicType.AIR_ROLL,
                                            position=pos,
                                            velocity=vel,
                                            height=pos.z,
                                            duration=duration,
                                        )
                                    )
                                state.is_air_rolling = False
                                state.air_roll_start_time = None
                            flip_dir = _get_flip_direction(
                                vel, (pitch_rate, yaw_rate, roll_rate), yaw
                            )
                            state.flip_direction = flip_dir
                            state.initial_yaw = yaw

                            mechanic_type = MechanicType.FLIP

                            events.append(
                                MechanicEvent(
                                    timestamp=timestamp,
                                    player_id=player_id,
                                    mechanic_type=mechanic_type,
                                    position=pos,
                                    velocity=vel,
                                    direction=flip_dir,
                                    height=pos.z,
                                )
                            )
                    else:
                        # Pure vertical jump (jump or double jump)
                        if not state.has_jumped:
                            state.has_jumped = True
                            # Track for fast aerial detection
                            state.first_jump_time = timestamp
                            state.boost_at_first_jump = player.boost_amount
                            state.boost_used_since_jump = 0
                            events.append(
                                MechanicEvent(
                                    timestamp=timestamp,
                                    player_id=player_id,
                                    mechanic_type=MechanicType.JUMP,
                                    position=pos,
                                    velocity=vel,
                                    height=pos.z,
                                )
                            )
                        elif not state.has_double_jumped and not state.has_flipped:
                            state.has_double_jumped = True
                            state.second_jump_time = timestamp  # For fast aerial
                            events.append(
                                MechanicEvent(
                                    timestamp=timestamp,
                                    player_id=player_id,
                                    mechanic_type=MechanicType.DOUBLE_JUMP,
                                    position=pos,
                                    velocity=vel,
                                    height=pos.z,
                                )
                            )
                            # Check for fast aerial on double jump
                            if (
                                state.first_jump_time is not None
                                and not state.fast_aerial_detected
                            ):
                                time_since_first_jump = (
                                    timestamp - state.first_jump_time
                                )
                                if (
                                    time_since_first_jump
                                    <= FAST_AERIAL_SECOND_JUMP_WINDOW
                                    and state.boost_used_since_jump > 0
                                ):
                                    # Potential fast aerial, confirm on height check
                                    pass  # Height check done separately below

                # Aerial detection (high altitude)
                if (
                    pos.z > AERIAL_HEIGHT_THRESHOLD
                    and state.has_jumped
                    and state.airborne_start_time is not None
                ):
                    airborne_duration = timestamp - state.airborne_start_time
                    # Only mark as aerial after sustained flight
                    if airborne_duration > 0.5 and not any(
                        e.mechanic_type == MechanicType.AERIAL
                        and e.player_id == player_id
                        and timestamp - e.timestamp < 1.0
                        for e in events
                    ):
                        events.append(
                            MechanicEvent(
                                timestamp=timestamp,
                                player_id=player_id,
                                mechanic_type=MechanicType.AERIAL,
                                position=pos,
                                velocity=vel,
                                height=pos.z,
                            )
                        )

                # Fast aerial: jump + boost + 2nd jump within timing, height > 300 UU
                if (
                    state.first_jump_time is not None
                    and state.second_jump_time is not None
                    and not state.fast_aerial_detected
                    and (state.has_double_jumped or state.has_flipped)
                    and pos.z > FAST_AERIAL_HEIGHT_THRESHOLD
                ):
                    time_since_first_jump = timestamp - state.first_jump_time
                    second_jump_window = state.second_jump_time - state.first_jump_time
                    if (
                        time_since_first_jump <= FAST_AERIAL_TIME_TO_HEIGHT
                        and second_jump_window <= FAST_AERIAL_SECOND_JUMP_WINDOW
                        and state.boost_used_in_window  # Boost in 0.3s window
                    ):
                        state.fast_aerial_detected = True
                        events.append(
                            MechanicEvent(
                                timestamp=timestamp,
                                player_id=player_id,
                                mechanic_type=MechanicType.FAST_AERIAL,
                                position=pos,
                                velocity=vel,
                                height=pos.z,
                                boost_used=state.boost_used_since_jump,
                            )
                        )

                # Flip cancel detection (Phase 8)
                # pitch reversal relative to intent, 3+ frames persistence
                if (
                    state.has_flipped
                    and state.flip_start_time is not None
                    and not state.flip_cancel_confirmed
                ):
                    flip_elapsed = timestamp - state.flip_start_time
                    if flip_elapsed <= FLIP_CANCEL_WINDOW:  # Within 0.25s
                        # Check pitch reversal relative to intent
                        # Use FLIP_CANCEL_PITCH_REVERSAL_THRESHOLD (3.0 rad/s)
                        threshold = FLIP_CANCEL_PITCH_REVERSAL_THRESHOLD
                        pitch_reversed = (
                            state.flip_pitch_intent > 0 and pitch_rate < -threshold
                        ) or (state.flip_pitch_intent < 0 and pitch_rate > threshold)

                        if pitch_reversed:
                            if state.flip_cancel_start_time is None:
                                state.flip_cancel_start_time = timestamp
                            elif timestamp - state.flip_cancel_start_time >= 0.1:
                                # Persistence confirmed (~3 frames at 30 Hz)
                                state.flip_cancel_confirmed = True
                                state.flip_cancel_detected = True
                                events.append(
                                    MechanicEvent(
                                        timestamp=timestamp,
                                        player_id=player_id,
                                        mechanic_type=MechanicType.FLIP_CANCEL,
                                        position=pos,
                                        velocity=vel,
                                        direction=state.flip_direction,
                                        height=pos.z,
                                    )
                                )
                        else:
                            # Cancel criteria no longer met - reset
                            state.flip_cancel_start_time = None

                # Half-flip and speedflip detection
                if (
                    state.has_flipped
                    and state.flip_start_time is not None
                    and state.flip_cancel_detected
                ):
                    flip_elapsed = timestamp - state.flip_start_time

                    # Check for half-flip (backward flip + cancel + 180° turn)
                    if (
                        state.flip_direction == "backward"
                        and flip_elapsed < HALF_FLIP_DETECTION_WINDOW
                    ):
                        # Calculate yaw change from flip start
                        yaw_change = abs(_normalize_angle(yaw - state.initial_yaw))
                        if yaw_change > HALF_FLIP_YAW_CHANGE_THRESHOLD:
                            # This is a half-flip
                            if not any(
                                e.mechanic_type == MechanicType.HALF_FLIP
                                and e.player_id == player_id
                                and abs(timestamp - e.timestamp) < 0.3
                                for e in events
                            ):
                                events.append(
                                    MechanicEvent(
                                        timestamp=timestamp,
                                        player_id=player_id,
                                        mechanic_type=MechanicType.HALF_FLIP,
                                        position=pos,
                                        velocity=vel,
                                        direction="backward",
                                        height=pos.z,
                                        duration=flip_elapsed,
                                    )
                                )

                    # Check for speedflip (diagonal flip + cancel within 100ms)
                    elif (
                        state.flip_direction == "diagonal"
                        and flip_elapsed < SPEEDFLIP_CANCEL_WINDOW
                    ):
                        # Speedflip = diagonal flip with immediate cancel
                        # Already detected cancel, now classify as speedflip
                        if not any(
                            e.mechanic_type == MechanicType.SPEEDFLIP
                            and e.player_id == player_id
                            and abs(timestamp - e.timestamp) < 0.3
                            for e in events
                        ):
                            events.append(
                                MechanicEvent(
                                    timestamp=timestamp,
                                    player_id=player_id,
                                    mechanic_type=MechanicType.SPEEDFLIP,
                                    position=pos,
                                    velocity=vel,
                                    direction="diagonal",
                                    height=pos.z,
                                    duration=flip_elapsed,
                                )
                            )

                # Flip reset detection (Phase 2)
                # Ball contact on underside while airborne restores flip
                if state.is_airborne and frame.ball is not None:
                    # Check for expiry of existing reset
                    if (
                        state.flip_available_from_reset
                        and state.flip_reset_touch_time is not None
                    ):
                        time_since_reset = timestamp - state.flip_reset_touch_time
                        if time_since_reset > FLIP_RESET_WINDOW:
                            # Reset expired
                            state.flip_available_from_reset = False
                            state.flip_reset_touch_time = None

                    # Check for new underside contact (allows refresh)
                    if state.has_flipped or state.flip_available_from_reset:
                        ball_pos = frame.ball.position
                        car_up = _rotation_to_up_vector(rot)

                        # Ball-to-car vector (normalized)
                        btc = Vec3(
                            pos.x - ball_pos.x,
                            pos.y - ball_pos.y,
                            pos.z - ball_pos.z,
                        )
                        btc_norm = _normalize_vec(btc)

                        # Check underside contact: ball below/behind car
                        dot_product = _dot(car_up, btc_norm)
                        dist = _distance(pos, ball_pos)

                        if (
                            dot_product > FLIP_RESET_DOT_THRESHOLD
                            and dist < FLIP_RESET_PROXIMITY
                        ):
                            # Underside contact detected - refresh reset
                            state.flip_available_from_reset = True
                            state.flip_reset_touch_time = timestamp
                            # Reset has_flipped so new flips can be detected
                            state.has_flipped = False

                # Check if flip was used after reset (emit FLIP_RESET event)
                if (
                    state.flip_available_from_reset
                    and state.flip_reset_touch_time is not None
                ):
                    # If player just flipped (within this frame's flip detection)
                    # We detect this by checking if a flip was just added
                    flip_events = [
                        e
                        for e in events
                        if e.mechanic_type == MechanicType.FLIP
                        and e.player_id == player_id
                        and abs(e.timestamp - timestamp) < 0.05
                    ]
                    if flip_events and state.flip_available_from_reset:
                        # Window check
                        time_since_reset = timestamp - state.flip_reset_touch_time
                        if time_since_reset <= FLIP_RESET_WINDOW:
                            events.append(
                                MechanicEvent(
                                    timestamp=state.flip_reset_touch_time,
                                    player_id=player_id,
                                    mechanic_type=MechanicType.FLIP_RESET,
                                    position=pos,
                                    velocity=vel,
                                    height=pos.z,
                                    ball_position=(
                                        frame.ball.position if frame.ball else None
                                    ),
                                )
                            )
                        # Reset the flag after use
                        state.flip_available_from_reset = False
                        state.flip_reset_touch_time = None

                # Skim detection (Phase 13)
                # Underside ball contact + ball acceleration + toward opponent goal
                if state.is_airborne and frame.ball is not None:
                    ball_pos = frame.ball.position
                    ball_dist = _distance(pos, ball_pos)
                    car_up_for_skim = _rotation_to_up_vector(rot)

                    # Car-to-ball vector for underside check
                    car_to_ball = Vec3(
                        ball_pos.x - pos.x,
                        ball_pos.y - pos.y,
                        ball_pos.z - pos.z,
                    )
                    car_to_ball_norm = _normalize_vec(car_to_ball)

                    # Ball is in direction of car's DOWN (underside contact)
                    dot_val = _dot(car_up_for_skim, car_to_ball_norm)
                    underside_contact = dot_val < SKIM_DOT_THRESHOLD

                    if underside_contact and ball_dist < BALL_CONTACT_PROXIMITY:
                        current_speed = _magnitude(frame.ball.velocity)
                        if current_speed > state.prev_ball_speed:  # Ball accelerated
                            # Check toward opponent goal
                            if player_team is not None and is_toward_opponent_goal(
                                player_team, frame.ball.velocity
                            ):
                                if not any(
                                    e.mechanic_type == MechanicType.SKIM
                                    and e.player_id == player_id
                                    and abs(e.timestamp - timestamp) < 0.3
                                    for e in events
                                ):
                                    speed_gain = current_speed - state.prev_ball_speed
                                    events.append(
                                        MechanicEvent(
                                            timestamp=timestamp,
                                            player_id=player_id,
                                            mechanic_type=MechanicType.SKIM,
                                            position=pos,
                                            velocity=vel,
                                            height=pos.z,
                                            ball_position=ball_pos,
                                            ball_velocity_change=speed_gain,
                                        )
                                    )

                                    # Check for psycho (skim after backboard slam)
                                    slam_time = state.psycho_slam_time
                                    psycho_in_window = (
                                        slam_time
                                        and timestamp - slam_time < PSYCHO_WINDOW
                                    )
                                    if (
                                        state.psycho_state == "SKIM_READY"
                                        and psycho_in_window
                                    ):
                                        events.append(
                                            MechanicEvent(
                                                timestamp=timestamp,
                                                player_id=player_id,
                                                mechanic_type=MechanicType.PSYCHO,
                                                position=pos,
                                                velocity=vel,
                                                height=pos.z,
                                                ball_position=ball_pos,
                                            )
                                        )
                                        # Reset psycho state
                                        state.psycho_state = None
                                        state.psycho_slam_time = None

                # Psycho state machine (Phase 14)
                # State 1: Detect intentional backboard slam
                if frame.ball is not None and player_team is not None:
                    ball_pos = frame.ball.position
                    ball_vel = frame.ball.velocity

                    # Own goal direction based on team
                    if player_team == 0:
                        own_goal_y = -FIELD.BACK_WALL_Y
                    else:
                        own_goal_y = FIELD.BACK_WALL_Y
                    near_own_backboard = abs(ball_pos.y - own_goal_y) < WALL_PROXIMITY

                    # Ball heading toward own goal?
                    ball_toward_own_goal = (player_team == 0 and ball_vel.y < -500) or (
                        player_team == 1 and ball_vel.y > 500
                    )

                    if near_own_backboard and ball_toward_own_goal:
                        ball_dist = _distance(pos, ball_pos)
                        if ball_dist < BALL_CONTACT_PROXIMITY:
                            # Check if ball velocity toward own goal INCREASED
                            if state.prev_ball_velocity is not None:
                                prev_toward = abs(state.prev_ball_velocity.y)
                                curr_toward = abs(ball_vel.y)
                                if curr_toward > prev_toward + 200:  # Intentional slam
                                    state.psycho_waiting_for_bounce = True
                                    state.psycho_slam_time = timestamp

                    # Detect wall bounce for psycho
                    if state.psycho_waiting_for_bounce and near_own_backboard:
                        if state.prev_ball_velocity is not None:
                            # Y velocity sign flip = bounce
                            prev_y = state.prev_ball_velocity.y
                            if player_team == 0:
                                bounced = prev_y < 0 and ball_vel.y > 0
                            else:
                                bounced = prev_y > 0 and ball_vel.y < 0
                            if bounced:
                                state.psycho_state = "INVERTING"
                                state.psycho_waiting_for_bounce = False

                # State 2: Check for inversion
                if state.psycho_state == "INVERTING":
                    car_up_psycho = _rotation_to_up_vector(rot)
                    world_up = Vec3(0, 0, 1)
                    if _dot(car_up_psycho, world_up) < PSYCHO_INVERT_THRESHOLD:
                        state.psycho_state = "SKIM_READY"

                # Reset psycho on landing or timeout
                if not state.is_airborne:
                    state.psycho_state = None
                    state.psycho_slam_time = None
                    state.psycho_waiting_for_bounce = False
                elif (
                    state.psycho_slam_time is not None
                    and timestamp - state.psycho_slam_time > PSYCHO_WINDOW
                ):
                    state.psycho_state = None
                    state.psycho_slam_time = None

                # Air roll detection (Phase 2)
                # Sustained roll rotation > 2.0 rad/s for > 0.3s while airborne
                if state.is_airborne:
                    # Skip air roll check during flip-induced rotation
                    time_since_flip = (
                        timestamp - state.flip_start_time
                        if state.flip_start_time
                        else float("inf")
                    )
                    exclude_for_flip = time_since_flip < AIR_ROLL_FLIP_EXCLUSION_WINDOW

                    if not exclude_for_flip:
                        # Use absolute roll rate
                        abs_roll_rate = abs(roll_rate)

                        if abs_roll_rate > AIR_ROLL_RATE_THRESHOLD:
                            if not state.is_air_rolling:
                                # Start air roll
                                state.is_air_rolling = True
                                state.air_roll_start_time = timestamp
                        else:
                            if state.is_air_rolling and state.air_roll_start_time:
                                # End air roll - check duration
                                duration = timestamp - state.air_roll_start_time
                                if duration >= AIR_ROLL_MIN_DURATION:
                                    events.append(
                                        MechanicEvent(
                                            timestamp=state.air_roll_start_time,
                                            player_id=player_id,
                                            mechanic_type=MechanicType.AIR_ROLL,
                                            position=pos,
                                            velocity=vel,
                                            height=pos.z,
                                            duration=duration,
                                        )
                                    )
                                state.is_air_rolling = False
                                state.air_roll_start_time = None
                else:
                    # Landed - end any ongoing air roll
                    if state.is_air_rolling and state.air_roll_start_time:
                        duration = timestamp - state.air_roll_start_time
                        if duration >= AIR_ROLL_MIN_DURATION:
                            events.append(
                                MechanicEvent(
                                    timestamp=state.air_roll_start_time,
                                    player_id=player_id,
                                    mechanic_type=MechanicType.AIR_ROLL,
                                    position=pos,
                                    velocity=vel,
                                    height=pos.z,
                                    duration=duration,
                                )
                            )
                    state.is_air_rolling = False
                    state.air_roll_start_time = None

            # === GROUND-BASED MECHANICS (run when grounded) ===
            # These must be OUTSIDE the airborne-only block

            # Dribble detection (Phase 3)
            # Ball on car roof for > 0.5s, ground dribbles only
            if is_on_ground and frame.ball is not None:
                ball_pos = frame.ball.position
                ball_vel = frame.ball.velocity

                # Calculate ball-to-car offset
                dx = ball_pos.x - pos.x
                dy = ball_pos.y - pos.y
                dz = ball_pos.z - pos.z

                # Horizontal distance
                xy_dist = math.sqrt(dx * dx + dy * dy)

                # Relative velocity between ball and car
                rel_vel = Vec3(
                    ball_vel.x - vel.x,
                    ball_vel.y - vel.y,
                    ball_vel.z - vel.z,
                )
                rel_speed = _magnitude(rel_vel)

                # Check dribble conditions
                is_in_dribble_envelope = (
                    xy_dist < DRIBBLE_XY_RADIUS
                    and DRIBBLE_Z_MIN < dz < DRIBBLE_Z_MAX
                    and pos.z < DRIBBLE_CAR_HEIGHT_MAX
                    and rel_speed < DRIBBLE_RELATIVE_VELOCITY_MAX
                )

                if is_in_dribble_envelope:
                    if not state.is_dribbling:
                        # Start dribble
                        state.is_dribbling = True
                        state.dribble_start_time = timestamp
                        state.ball_speed_at_dribble_start = _magnitude(ball_vel)
                else:
                    if state.is_dribbling and state.dribble_start_time:
                        # End dribble - check duration
                        duration = timestamp - state.dribble_start_time
                        if duration >= DRIBBLE_MIN_DURATION:
                            events.append(
                                MechanicEvent(
                                    timestamp=state.dribble_start_time,
                                    player_id=player_id,
                                    mechanic_type=MechanicType.DRIBBLE,
                                    position=pos,
                                    velocity=vel,
                                    height=pos.z,
                                    duration=duration,
                                    ball_position=ball_pos,
                                )
                            )
                        state.is_dribbling = False
                        state.dribble_start_time = None
                        state.ball_speed_at_dribble_start = 0.0
            elif not is_on_ground and state.is_dribbling:
                # End dribble when going airborne
                if state.dribble_start_time:
                    duration = timestamp - state.dribble_start_time
                    if duration >= DRIBBLE_MIN_DURATION:
                        events.append(
                            MechanicEvent(
                                timestamp=state.dribble_start_time,
                                player_id=player_id,
                                mechanic_type=MechanicType.DRIBBLE,
                                position=pos,
                                velocity=vel,
                                height=pos.z,
                                duration=duration,
                            )
                        )
                state.is_dribbling = False
                state.dribble_start_time = None
                state.ball_speed_at_dribble_start = 0.0

            # Flick and Musty detection
            # Flick: Ball departs car during flip from dribble with velocity gain
            # Musty: Backflip + ball acceleration (ANYWHERE - Phase 6 fix)
            if (
                state.has_flipped
                and state.flip_start_time is not None
                and frame.ball is not None
            ):
                flip_elapsed = timestamp - state.flip_start_time
                if flip_elapsed <= FLICK_DETECTION_WINDOW:
                    ball_pos = frame.ball.position
                    ball_dist = _distance(pos, ball_pos)
                    current_ball_speed = _magnitude(frame.ball.velocity)
                    pre_speed = state.ball_speed_at_flip_start or 0
                    speed_delta = current_ball_speed - pre_speed

                    # Phase 6: Musty flick works ANYWHERE - no dribble requirement
                    # Just needs: backward flip + ball proximity + ball acceleration
                    if (
                        state.flip_direction == "backward"
                        and ball_dist < BALL_CONTACT_PROXIMITY
                        and current_ball_speed > state.prev_ball_speed  # Any accel
                    ):
                        if not any(
                            e.mechanic_type == MechanicType.MUSTY_FLICK
                            and e.player_id == player_id
                            and abs(e.timestamp - timestamp) < 0.3
                            for e in events
                        ):
                            events.append(
                                MechanicEvent(
                                    timestamp=timestamp,
                                    player_id=player_id,
                                    mechanic_type=MechanicType.MUSTY_FLICK,
                                    position=pos,
                                    velocity=vel,
                                    height=pos.z,
                                    ball_position=ball_pos,
                                    ball_velocity_change=speed_delta,
                                )
                            )

                    # Regular flick: requires dribble context + speed gain
                    dx = ball_pos.x - pos.x
                    dy = ball_pos.y - pos.y
                    dz = ball_pos.z - pos.z
                    xy_dist = math.sqrt(dx * dx + dy * dy)
                    was_dribbling = state.is_dribbling or (
                        xy_dist < DRIBBLE_XY_RADIUS
                        and DRIBBLE_Z_MIN < dz < DRIBBLE_Z_MAX
                    )

                    # Regular flick: speed gain > 500 (from dribble, not a musty)
                    if (
                        was_dribbling
                        and speed_delta > FLICK_VELOCITY_GAIN
                        and state.flip_direction != "backward"  # Not a musty
                    ):
                        if not any(
                            e.mechanic_type == MechanicType.FLICK
                            and e.player_id == player_id
                            and abs(e.timestamp - timestamp) < 0.3
                            for e in events
                        ):
                            events.append(
                                MechanicEvent(
                                    timestamp=timestamp,
                                    player_id=player_id,
                                    mechanic_type=MechanicType.FLICK,
                                    position=pos,
                                    velocity=vel,
                                    height=pos.z,
                                    ball_position=ball_pos,
                                    ball_velocity_change=speed_delta,
                                )
                            )

            # Ceiling shot detection (Phase 5 - flip-based with persistence)
            # Requires: ceiling contact with orientation check, grants flip,
            # ceiling shot emits when flip is used before any surface contact
            car_up_check = _rotation_to_up_vector(rot)
            world_down = Vec3(0, 0, -1)
            car_upside_down = _dot(car_up_check, world_down) > 0.7

            # Ceiling contact tracking with persistence and orientation
            if pos.z > CEILING_HEIGHT_THRESHOLD and abs(vel.z) < 50 and car_upside_down:
                state.ceiling_contact_frames += 1
                if state.ceiling_contact_frames >= 2:  # ~66ms persistence
                    state.has_ceiling_flip = True
                    state.last_ceiling_touch_time = timestamp
                    state.had_surface_contact_since_ceiling = False
                    state.left_ceiling_yet = False  # Reset for new ceiling contact
            else:
                state.ceiling_contact_frames = 0

            # Track when player LEAVES ceiling (transition from ceiling to falling)
            if state.has_ceiling_flip and not state.left_ceiling_yet:
                still_on_ceiling = pos.z > CEILING_HEIGHT_THRESHOLD and car_upside_down
                if not still_on_ceiling:
                    state.left_ceiling_yet = True

            # Track surface contact AFTER leaving ceiling (invalidates ceiling flip)
            if state.has_ceiling_flip and state.left_ceiling_yet:
                on_ground = player.is_on_ground or pos.z < GROUND_HEIGHT_THRESHOLD
                near_wall = (
                    abs(pos.x) > FIELD.SIDE_WALL_X - 50
                    or abs(pos.y) > FIELD.BACK_WALL_Y - 50
                )
                back_on_ceiling = pos.z > CEILING_HEIGHT_THRESHOLD and car_upside_down
                if on_ground or near_wall or back_on_ceiling:
                    state.had_surface_contact_since_ceiling = True

            # Ceiling shot = flip used AFTER ceiling grant + ball touch,
            # BEFORE any surface contact
            if (
                state.has_ceiling_flip
                and state.flip_after_ceiling  # Flip occurred after ceiling contact
                and frame.ball is not None
                and not state.had_surface_contact_since_ceiling
            ):
                ball_dist = _distance(pos, frame.ball.position)
                if ball_dist < BALL_CONTACT_PROXIMITY:
                    if not any(
                        e.mechanic_type == MechanicType.CEILING_SHOT
                        and e.player_id == player_id
                        and abs(e.timestamp - timestamp) < 0.5
                        for e in events
                    ):
                        events.append(
                            MechanicEvent(
                                timestamp=timestamp,
                                player_id=player_id,
                                mechanic_type=MechanicType.CEILING_SHOT,
                                position=pos,
                                velocity=vel,
                                height=pos.z,
                                ball_position=frame.ball.position,
                            )
                        )
                    state.has_ceiling_flip = False  # Reset after use
                    state.flip_after_ceiling = False

            # Power slide detection (Phase 4)
            # Sideways velocity > 500 UU/s while grounded for > 0.2s
            if not state.is_airborne:
                # Compute car forward vector from yaw
                forward_x = math.cos(yaw)
                forward_y = math.sin(yaw)

                # Project velocity onto forward vector
                forward_vel = vel.x * forward_x + vel.y * forward_y

                # Sideways velocity = total - forward projection
                sideways_x = vel.x - forward_vel * forward_x
                sideways_y = vel.y - forward_vel * forward_y
                sideways_speed = math.sqrt(
                    sideways_x * sideways_x + sideways_y * sideways_y
                )

                if sideways_speed > POWER_SLIDE_VELOCITY_THRESHOLD:
                    if not state.is_power_sliding:
                        # Start power slide
                        state.is_power_sliding = True
                        state.power_slide_start_time = timestamp
                else:
                    if state.is_power_sliding and state.power_slide_start_time:
                        # End power slide - check duration
                        duration = timestamp - state.power_slide_start_time
                        if duration >= POWER_SLIDE_MIN_DURATION:
                            events.append(
                                MechanicEvent(
                                    timestamp=state.power_slide_start_time,
                                    player_id=player_id,
                                    mechanic_type=MechanicType.POWER_SLIDE,
                                    position=pos,
                                    velocity=vel,
                                    height=pos.z,
                                    duration=duration,
                                )
                            )
                        state.is_power_sliding = False
                        state.power_slide_start_time = None
            else:
                # Airborne - end any power slide
                if state.is_power_sliding and state.power_slide_start_time:
                    duration = timestamp - state.power_slide_start_time
                    if duration >= POWER_SLIDE_MIN_DURATION:
                        events.append(
                            MechanicEvent(
                                timestamp=state.power_slide_start_time,
                                player_id=player_id,
                                mechanic_type=MechanicType.POWER_SLIDE,
                                position=pos,
                                velocity=vel,
                                height=pos.z,
                                duration=duration,
                            )
                        )
                state.is_power_sliding = False
                state.power_slide_start_time = None

            # Ground pinch detection (Phase 5)
            # Ball pinched with ground, velocity gain > 1500 UU/s
            if frame.ball is not None:
                ball_pos = frame.ball.position
                ball_dist = _distance(pos, ball_pos)

                if (
                    ball_dist < BALL_CONTACT_PROXIMITY
                    and ball_pos.z < GROUND_PINCH_HEIGHT_MAX
                ):
                    current_ball_speed = _magnitude(frame.ball.velocity)
                    speed_delta = current_ball_speed - state.prev_ball_speed

                    if (
                        current_ball_speed > GROUND_PINCH_EXIT_VELOCITY_MIN
                        and speed_delta > GROUND_PINCH_VELOCITY_DELTA_MIN
                    ):
                        if not any(
                            e.mechanic_type == MechanicType.GROUND_PINCH
                            and e.player_id == player_id
                            and abs(e.timestamp - timestamp) < 0.3
                            for e in events
                        ):
                            events.append(
                                MechanicEvent(
                                    timestamp=timestamp,
                                    player_id=player_id,
                                    mechanic_type=MechanicType.GROUND_PINCH,
                                    position=pos,
                                    velocity=vel,
                                    height=pos.z,
                                    ball_position=ball_pos,
                                    ball_velocity_change=speed_delta,
                                )
                            )

            # Double touch detection (Phase 9 - velocity sign-flip bounce)
            # Two aerial touches without landing, VERIFIED wall bounce between
            if frame.ball is not None and state.is_airborne:
                ball_pos = frame.ball.position
                ball_vel = frame.ball.velocity
                ball_dist = _distance(pos, ball_pos)

                # Phase 9: Use velocity sign-flip to verify actual wall bounce
                # Not just position near wall - actual velocity reversal
                near_back_wall = abs(ball_pos.y) > FIELD.BACK_WALL_Y - WALL_PROXIMITY
                near_side_wall = abs(ball_pos.x) > FIELD.SIDE_WALL_X - WALL_PROXIMITY

                if state.prev_ball_velocity is not None:
                    prev_vel = state.prev_ball_velocity

                    # Back wall bounce: v_y sign flips
                    if near_back_wall:
                        if ball_pos.y > 0:  # Positive end (opponent goal direction)
                            bounced = prev_vel.y > 0 and ball_vel.y < 0
                        else:  # Negative end
                            bounced = prev_vel.y < 0 and ball_vel.y > 0
                        if bounced:
                            state.wall_bounce_detected = True

                    # Side wall bounce: v_x sign flips
                    if near_side_wall:
                        if ball_pos.x > 0:  # Right wall
                            bounced = prev_vel.x > 0 and ball_vel.x < 0
                        else:  # Left wall
                            bounced = prev_vel.x < 0 and ball_vel.x > 0
                        if bounced:
                            state.wall_bounce_detected = True

                # Check for aerial touch (with debounce)
                if (
                    ball_dist < BALL_CONTACT_PROXIMITY
                    and pos.z > DOUBLE_TOUCH_HEIGHT_MIN
                ):
                    # Only count as new touch if debounce time has passed
                    is_new_touch = (
                        state.last_touch_timestamp is None
                        or timestamp - state.last_touch_timestamp > TOUCH_DEBOUNCE_TIME
                    )

                    if is_new_touch:
                        state.last_touch_timestamp = timestamp

                        if state.aerial_touch_count_since_ground == 0:
                            # First aerial touch
                            state.aerial_touch_count_since_ground = 1
                            state.first_aerial_touch_time = timestamp
                            state.wall_bounce_detected = False
                        elif (
                            state.aerial_touch_count_since_ground >= 1
                            and state.first_aerial_touch_time is not None
                        ):
                            time_since_first = timestamp - state.first_aerial_touch_time
                            if (
                                time_since_first <= DOUBLE_TOUCH_WINDOW
                                and state.wall_bounce_detected
                            ):
                                # Second touch with wall bounce - double touch!
                                events.append(
                                    MechanicEvent(
                                        timestamp=timestamp,
                                        player_id=player_id,
                                        mechanic_type=MechanicType.DOUBLE_TOUCH,
                                        position=pos,
                                        velocity=vel,
                                        height=pos.z,
                                        ball_position=ball_pos,
                                    )
                                )
                            # Reset for potential further touches
                            state.aerial_touch_count_since_ground = 1
                            state.first_aerial_touch_time = timestamp
                            state.wall_bounce_detected = False

            # Redirect detection (Phase 5)
            # Aerial touch that changes ball direction > 45 degrees
            if (
                frame.ball is not None
                and state.is_airborne
                and pos.z > REDIRECT_HEIGHT_MIN
            ):
                ball_pos = frame.ball.position
                ball_dist = _distance(pos, ball_pos)

                if ball_dist < BALL_CONTACT_PROXIMITY:
                    current_ball_speed = _magnitude(frame.ball.velocity)

                    if (
                        current_ball_speed > REDIRECT_MIN_BALL_SPEED
                        and state.prev_ball_velocity is not None
                    ):
                        # Compute direction change using actual velocities
                        pre_dir = _normalize_vec(state.prev_ball_velocity)
                        post_dir = _normalize_vec(frame.ball.velocity)
                        dot_val = _dot(pre_dir, post_dir)
                        dot_clamped = max(-1.0, min(1.0, dot_val))
                        angle = math.acos(dot_clamped)

                        # Redirect: >45 degrees AND toward opponent goal
                        is_toward_goal = (
                            player_team is not None
                            and is_toward_opponent_goal(
                                player_team, frame.ball.velocity
                            )
                        )

                        if angle > REDIRECT_ANGLE_THRESHOLD and is_toward_goal:
                            if not any(
                                e.mechanic_type == MechanicType.REDIRECT
                                and e.player_id == player_id
                                and abs(e.timestamp - timestamp) < 0.3
                                for e in events
                            ):
                                events.append(
                                    MechanicEvent(
                                        timestamp=timestamp,
                                        player_id=player_id,
                                        mechanic_type=MechanicType.REDIRECT,
                                        position=pos,
                                        velocity=vel,
                                        height=pos.z,
                                        ball_position=ball_pos,
                                    )
                                )

            # Stall detection (Phase 5)
            # Tornado spin with near-zero vertical velocity mid-air
            if (
                state.is_airborne
                and pos.z > STALL_HEIGHT_MIN
                and prev_player is not None
            ):
                abs_roll_rate = abs(roll_rate)
                abs_yaw_rate = abs(yaw_rate)

                # Check tornado pattern
                is_tornado = (
                    abs_roll_rate > STALL_ROLL_RATE_MIN
                    and abs_yaw_rate > STALL_YAW_RATE_MIN
                    and (
                        (roll_rate > 0 and yaw_rate < 0)
                        or (roll_rate < 0 and yaw_rate > 0)
                    )
                )

                # Check hover condition
                abs_z_vel = abs(vel.z)
                xy_speed = math.sqrt(vel.x * vel.x + vel.y * vel.y)
                is_hovering = (
                    abs_z_vel < STALL_VERTICAL_VELOCITY_MAX
                    and xy_speed < STALL_HORIZONTAL_VELOCITY_MAX
                )

                if is_tornado and is_hovering:
                    if not state.is_stalling:
                        # Start tracking stall
                        state.is_stalling = True
                        state.stall_start_time = timestamp
                    elif state.stall_start_time is not None:
                        # Check if we've stalled long enough
                        stall_duration = timestamp - state.stall_start_time
                        if stall_duration >= STALL_MIN_DURATION:
                            if not any(
                                e.mechanic_type == MechanicType.STALL
                                and e.player_id == player_id
                                and abs(e.timestamp - timestamp) < 0.5
                                for e in events
                            ):
                                events.append(
                                    MechanicEvent(
                                        timestamp=timestamp,
                                        player_id=player_id,
                                        mechanic_type=MechanicType.STALL,
                                        position=pos,
                                        velocity=vel,
                                        height=pos.z,
                                        duration=stall_duration,
                                    )
                                )
                else:
                    # Stall conditions no longer met
                    state.is_stalling = False
                    state.stall_start_time = None

        # Update state for next frame
        state.prev_z_velocity = vel.z
        state.prev_z_position = pos.z
        state.prev_velocity = vel  # Full velocity for car-local transforms
        state.prev_rotation_pitch = pitch
        state.prev_rotation_yaw = yaw
        state.prev_rotation_roll = roll
        state.last_velocity_z = vel.z
        state.prev_yaw = yaw

        # Track boost usage for fast aerial detection
        if state.first_jump_time is not None:
            # Boost decreased = boost used
            boost_delta = state.prev_boost_amount - player.boost_amount
            if boost_delta > 0:
                state.boost_used_since_jump += boost_delta
                # Check if boost was used within the 0.3s window
                time_since_jump = timestamp - state.first_jump_time
                if time_since_jump <= FAST_AERIAL_BOOST_WINDOW:
                    state.boost_used_in_window = True
        state.prev_boost_amount = player.boost_amount

        # Track ball state for future mechanics
        if frame.ball is not None:
            ball_speed = _magnitude(frame.ball.velocity)
            state.prev_ball_speed = ball_speed
            state.prev_ball_z_velocity = frame.ball.velocity.z
            state.prev_ball_velocity = frame.ball.velocity

        # Store angular rates for flip cancel/discrimination
        if prev_player is not None and prev_frame is not None:
            state.prev_angular_x = pitch_rate
            state.prev_angular_y = yaw_rate
            state.prev_angular_z = roll_rate

        prev_frame = frame
        prev_player = player

    return events


def analyze_mechanics(frames: list[Frame]) -> dict:
    """Analyze mechanics for all players in replay.

    Args:
        frames: Normalized frame data

    Returns:
        Dict with mechanics analysis results
    """
    # Get all unique player IDs
    player_ids: set[str] = set()
    for frame in frames:
        for player in frame.players:
            player_ids.add(player.player_id)

    # Detect mechanics for each player
    per_player: dict[str, dict] = {}
    all_events: list[dict] = []

    for player_id in sorted(player_ids):
        events = detect_mechanics_for_player(frames, player_id)

        # Aggregate counts by mechanic type
        counts: dict[str, int] = {}
        for event in events:
            mtype = event.mechanic_type.value
            counts[mtype] = counts.get(mtype, 0) + 1

            # Add to flat event list
            event_dict = {
                "timestamp": event.timestamp,
                "player_id": event.player_id,
                "mechanic_type": mtype,
                "position": {
                    "x": event.position.x,
                    "y": event.position.y,
                    "z": event.position.z,
                },
                "velocity": {
                    "x": event.velocity.x,
                    "y": event.velocity.y,
                    "z": event.velocity.z,
                },
                "direction": event.direction,
                "height": event.height,
                "duration": event.duration,
            }
            # Add optional fields if present
            if event.ball_position is not None:
                event_dict["ball_position"] = {
                    "x": event.ball_position.x,
                    "y": event.ball_position.y,
                    "z": event.ball_position.z,
                }
            if event.ball_velocity_change is not None:
                event_dict["ball_velocity_change"] = event.ball_velocity_change
            if event.boost_used is not None:
                event_dict["boost_used"] = event.boost_used
            all_events.append(event_dict)

        # Compute duration totals for mechanics that have durations
        air_roll_events = [
            e for e in events if e.mechanic_type == MechanicType.AIR_ROLL
        ]
        dribble_events = [e for e in events if e.mechanic_type == MechanicType.DRIBBLE]
        power_slide_events = [
            e for e in events if e.mechanic_type == MechanicType.POWER_SLIDE
        ]

        air_roll_total_time = sum((e.duration or 0) for e in air_roll_events)
        dribble_total_time = sum((e.duration or 0) for e in dribble_events)
        power_slide_total_time = sum((e.duration or 0) for e in power_slide_events)

        per_player[player_id] = {
            # Existing mechanics
            "jump_count": counts.get("jump", 0),
            "double_jump_count": counts.get("double_jump", 0),
            "flip_count": counts.get("flip", 0),
            "wavedash_count": counts.get("wavedash", 0),
            "aerial_count": counts.get("aerial", 0),
            "halfflip_count": counts.get("half_flip", 0),
            "speedflip_count": counts.get("speedflip", 0),
            "flip_cancel_count": counts.get("flip_cancel", 0),
            # New mechanics
            "fast_aerial_count": counts.get("fast_aerial", 0),
            "flip_reset_count": counts.get("flip_reset", 0),
            "air_roll_count": len(air_roll_events),
            "air_roll_total_time_s": round(air_roll_total_time, 2),
            "dribble_count": counts.get("dribble", 0),
            "dribble_total_time_s": round(dribble_total_time, 2),
            "flick_count": counts.get("flick", 0),
            "musty_flick_count": counts.get("musty_flick", 0),
            "ceiling_shot_count": counts.get("ceiling_shot", 0),
            "power_slide_count": counts.get("power_slide", 0),
            "power_slide_total_time_s": round(power_slide_total_time, 2),
            "ground_pinch_count": counts.get("ground_pinch", 0),
            "double_touch_count": counts.get("double_touch", 0),
            "redirect_count": counts.get("redirect", 0),
            "stall_count": counts.get("stall", 0),
            "total_mechanics": sum(counts.values()),
        }

    # Sort events by timestamp
    all_events.sort(key=lambda e: e["timestamp"])

    return {
        "per_player": per_player,
        "events": all_events,
        # Existing totals
        "total_jumps": sum(p.get("jump_count", 0) for p in per_player.values()),
        "total_flips": sum(p.get("flip_count", 0) for p in per_player.values()),
        "total_aerials": sum(p.get("aerial_count", 0) for p in per_player.values()),
        "total_wavedashes": sum(
            p.get("wavedash_count", 0) for p in per_player.values()
        ),
        "total_halfflips": sum(p.get("halfflip_count", 0) for p in per_player.values()),
        "total_speedflips": sum(
            p.get("speedflip_count", 0) for p in per_player.values()
        ),
        # New totals
        "total_fast_aerials": sum(
            p.get("fast_aerial_count", 0) for p in per_player.values()
        ),
        "total_flip_resets": sum(
            p.get("flip_reset_count", 0) for p in per_player.values()
        ),
        "total_dribbles": sum(p.get("dribble_count", 0) for p in per_player.values()),
        "total_flicks": sum(p.get("flick_count", 0) for p in per_player.values()),
        "total_ceiling_shots": sum(
            p.get("ceiling_shot_count", 0) for p in per_player.values()
        ),
    }
