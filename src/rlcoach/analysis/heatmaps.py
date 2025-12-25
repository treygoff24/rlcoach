"""Heatmap generation for player positioning and activity data."""

from __future__ import annotations

from typing import Any

from ..field_constants import FieldConstants
from ..parser.types import Frame, PlayerFrame, Vec3


def generate_heatmaps(
    frames: list[Frame], player_id: str, events: dict[str, list[Any]]
) -> dict[str, Any]:
    """Generate position, touch, and boost pickup heatmaps for a player.

    Args:
        frames: Timeline of normalized frame data
        player_id: Player to generate heatmaps for
        events: Event data containing touches and boost pickups

    Returns:
        Dictionary with position_occupancy_grid, touch_density_grid, boost_pickup_grid
    """
    # Use field constants for grid extent
    extent = {
        "xmin": -FieldConstants.SIDE_WALL_X,
        "xmax": FieldConstants.SIDE_WALL_X,
        "ymin": -FieldConstants.BACK_WALL_Y,
        "ymax": FieldConstants.BACK_WALL_Y,
    }

    # Grid dimensions (balance detail vs data sparsity)
    x_bins = 24
    y_bins = 16

    # Generate each heatmap
    position_grid = _generate_position_heatmap(
        frames, player_id, x_bins, y_bins, extent
    )
    touch_grid = _generate_touch_heatmap(
        events.get("touches", []), player_id, x_bins, y_bins, extent
    )
    boost_grid = _generate_boost_pickup_heatmap(
        events.get("boost_pickups", []), player_id, x_bins, y_bins, extent
    )

    return {
        "position_occupancy_grid": position_grid,
        "touch_density_grid": touch_grid,
        "boost_pickup_grid": boost_grid,
    }


def _generate_position_heatmap(
    frames: list[Frame],
    player_id: str,
    x_bins: int,
    y_bins: int,
    extent: dict[str, float],
) -> dict[str, Any]:
    """Generate position occupancy heatmap from frame data."""

    # Initialize grid
    grid = [[0.0 for _ in range(x_bins)] for _ in range(y_bins)]
    total_frames = 0

    # Collect player positions
    for frame in frames:
        player_frame = _get_player_frame(frame, player_id)
        if not player_frame:
            continue

        # Convert position to grid coordinates
        x_idx, y_idx = _position_to_grid_coords(
            player_frame.position, x_bins, y_bins, extent
        )

        if 0 <= x_idx < x_bins and 0 <= y_idx < y_bins:
            grid[y_idx][x_idx] += 1.0
            total_frames += 1

    # Normalize to [0, 1] range
    if total_frames > 0:
        for y in range(y_bins):
            for x in range(x_bins):
                grid[y][x] = grid[y][x] / total_frames

    return {"x_bins": x_bins, "y_bins": y_bins, "extent": extent, "values": grid}


def _generate_touch_heatmap(
    touch_events: list[Any],
    player_id: str,
    x_bins: int,
    y_bins: int,
    extent: dict[str, float],
) -> dict[str, Any]:
    """Generate touch density heatmap from touch events."""

    # Initialize grid
    grid = [[0.0 for _ in range(x_bins)] for _ in range(y_bins)]
    total_touches = 0

    # Process touch events
    for touch in touch_events:
        # Support both dataclass TouchEvent and dict representation
        t_pid = None
        t_loc = None
        if hasattr(touch, "player_id"):
            t_pid = touch.player_id
            t_loc = getattr(touch, "location", None)
        elif isinstance(touch, dict):
            t_pid = touch.get("player_id")
            t_loc = touch.get("location")

        if t_pid != player_id or t_loc is None:
            continue

        # Convert to Vec3 for consistency (supports dict or any x/y/z object)
        if isinstance(t_loc, dict):
            pos = Vec3(t_loc.get("x", 0.0), t_loc.get("y", 0.0), t_loc.get("z", 0.0))
        elif hasattr(t_loc, "x") and hasattr(t_loc, "y") and hasattr(t_loc, "z"):
            pos = Vec3(t_loc.x, t_loc.y, t_loc.z)
        else:
            pos = Vec3(0.0, 0.0, 0.0)

        # Convert to grid coordinates
        x_idx, y_idx = _position_to_grid_coords(pos, x_bins, y_bins, extent)

        if 0 <= x_idx < x_bins and 0 <= y_idx < y_bins:
            grid[y_idx][x_idx] += 1.0
            total_touches += 1

    # Normalize to [0, 1] range
    if total_touches > 0:
        max_touches = max(max(row) for row in grid)
        if max_touches > 0:
            for y in range(y_bins):
                for x in range(x_bins):
                    grid[y][x] = grid[y][x] / max_touches

    return {"x_bins": x_bins, "y_bins": y_bins, "extent": extent, "values": grid}


def _generate_boost_pickup_heatmap(
    boost_events: list[Any],
    player_id: str,
    x_bins: int,
    y_bins: int,
    extent: dict[str, float],
) -> dict[str, Any]:
    """Generate boost pickup heatmap from boost pickup events."""

    # Initialize grid
    grid = [[0.0 for _ in range(x_bins)] for _ in range(y_bins)]
    total_pickups = 0

    # Process boost pickup events
    for pickup in boost_events:
        # Support both dataclass BoostPickupEvent and dict representation
        p_pid = None
        p_loc = None
        p_pad_type = None
        if hasattr(pickup, "player_id"):
            p_pid = pickup.player_id
            p_loc = getattr(pickup, "location", None)
            p_pad_type = getattr(pickup, "pad_type", None)
        elif isinstance(pickup, dict):
            p_pid = pickup.get("player_id")
            p_loc = pickup.get("location")
            p_pad_type = pickup.get("pad_type")

        if p_pid != player_id or p_loc is None:
            continue

        # Convert to Vec3 for consistency (supports dict or any x/y/z object)
        if isinstance(p_loc, dict):
            pos = Vec3(p_loc.get("x", 0.0), p_loc.get("y", 0.0), p_loc.get("z", 0.0))
        elif hasattr(p_loc, "x") and hasattr(p_loc, "y") and hasattr(p_loc, "z"):
            pos = Vec3(p_loc.x, p_loc.y, p_loc.z)
        else:
            pos = Vec3(0.0, 0.0, 0.0)

        # Convert to grid coordinates
        x_idx, y_idx = _position_to_grid_coords(pos, x_bins, y_bins, extent)

        if 0 <= x_idx < x_bins and 0 <= y_idx < y_bins:
            # Weight big pads more heavily
            weight = 2.0 if p_pad_type == "BIG" else 1.0
            grid[y_idx][x_idx] += weight
            total_pickups += weight

    # Normalize to [0, 1] range
    if total_pickups > 0:
        max_pickups = max(max(row) for row in grid)
        if max_pickups > 0:
            for y in range(y_bins):
                for x in range(x_bins):
                    grid[y][x] = grid[y][x] / max_pickups

    return {"x_bins": x_bins, "y_bins": y_bins, "extent": extent, "values": grid}


def _position_to_grid_coords(
    pos: Vec3, x_bins: int, y_bins: int, extent: dict[str, float]
) -> tuple[int, int]:
    """Convert world position to grid coordinates."""

    # Normalize position to [0, 1] within extent
    x_norm = (pos.x - extent["xmin"]) / (extent["xmax"] - extent["xmin"])
    y_norm = (pos.y - extent["ymin"]) / (extent["ymax"] - extent["ymin"])

    # Convert to grid indices
    x_idx = int(x_norm * x_bins)
    y_idx = int(y_norm * y_bins)

    # Clamp to valid range
    x_idx = max(0, min(x_bins - 1, x_idx))
    y_idx = max(0, min(y_bins - 1, y_idx))

    return x_idx, y_idx


def _get_player_frame(frame: Frame, player_id: str) -> PlayerFrame | None:
    """Extract player frame from frame data."""
    if hasattr(frame, "players") and frame.players:
        for p in frame.players:
            if getattr(p, "player_id", None) == player_id:
                return p
    return None
