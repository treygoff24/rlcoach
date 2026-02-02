"""Golden tests for deterministic synthetic reports.

Build small synthetic inputs and compare normalized outputs to stored goldens.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from rlcoach.analysis import aggregate_analysis
from rlcoach.events import (
    build_timeline,
    detect_boost_pickups,
    detect_challenge_events,
    detect_demos,
    detect_goals,
    detect_kickoffs,
    detect_touches,
)
from rlcoach.field_constants import Vec3
from rlcoach.normalize import measure_frame_rate
from rlcoach.parser.types import BallFrame, Frame, Header, PlayerFrame, PlayerInfo
from rlcoach.schema import validate_report
from rlcoach.utils.identity import build_player_identities


def _normalize(obj: Any) -> Any:
    # Handle Enum values first
    if hasattr(obj, "value") and hasattr(obj, "name") and hasattr(obj, "_name_"):
        return obj.value
    # Convert NamedTuple (Vec3) to dict
    if hasattr(obj, "_asdict"):
        return obj._asdict()
    # Convert dataclass-like (but not Enum)
    if hasattr(obj, "__dict__") and hasattr(obj, "__dataclass_fields__"):
        d = {k: v for k, v in obj.__dict__.items() if not k.startswith("_")}
        return {k: _normalize(v) for k, v in d.items()}
    # Recurse into mappings and sequences
    if isinstance(obj, dict):
        return {k: _normalize(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_normalize(v) for v in obj]
    return obj


def build_synthetic_report(
    name: str, header: Header, frames: list[Frame]
) -> dict[str, Any]:
    # Events
    goals = detect_goals(frames, header)
    demos = detect_demos(frames)
    kickoffs = detect_kickoffs(frames, header)
    pickups = detect_boost_pickups(frames)
    touches = detect_touches(frames)
    challenges = detect_challenge_events(frames, touches)
    events_dict: dict[str, list[Any]] = {
        "goals": goals,
        "demos": demos,
        "kickoffs": kickoffs,
        "boost_pickups": pickups,
        "touches": touches,
        "challenges": challenges,
    }
    timeline = build_timeline(events_dict)

    # Analysis
    analysis_out = aggregate_analysis(frames, events_dict, header)

    # Players and teams from header (mirror report.py behavior)
    team_players: dict[str, list[str]] = {"BLUE": [], "ORANGE": []}
    players_block: list[dict[str, Any]] = []
    identities = build_player_identities(getattr(header, "players", []))

    if identities:
        for identity in identities:
            player_info = header.players[identity.header_index]
            team_name = (
                identity.team
                if identity.team in {"BLUE", "ORANGE"}
                else ("BLUE" if (player_info.team or 0) == 0 else "ORANGE")
            )
            team_players.setdefault(team_name, [])
            team_players[team_name].append(identity.canonical_id)
            players_block.append(
                {
                    "player_id": identity.canonical_id,
                    "display_name": identity.display_name,
                    "team": team_name,
                    "platform_ids": dict(identity.platform_ids),
                    "camera": getattr(player_info, "camera_settings", None) or {},
                    "loadout": getattr(player_info, "loadout", None) or {},
                }
            )

    if not players_block:
        players_block = [
            {
                "player_id": "player_0",
                "display_name": "Unknown",
                "team": "BLUE",
                "platform_ids": {},
                "camera": {},
                "loadout": {},
            }
        ]
        team_players["BLUE"].append("player_0")

    teams_block = {
        "blue": {
            "name": "BLUE",
            "score": int(header.team0_score or 0),
            "players": team_players["BLUE"],
        },
        "orange": {
            "name": "ORANGE",
            "score": int(header.team1_score or 0),
            "players": team_players["ORANGE"],
        },
    }

    # Events block
    def _timeline_entry(ev: Any) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for k in ("t", "frame", "type", "player_id", "team", "data"):
            if hasattr(ev, k):
                val = getattr(ev, k)
                if val is not None:
                    out[k] = _normalize(val)
        return out

    # Ensure nested Vec3 are converted for all event lists, especially touches
    def _event_dict_list(items: list[Any]) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for it in items:
            d = {
                k: _normalize(getattr(it, k))
                for k in getattr(it, "__dataclass_fields__").keys()
            }
            out.append(d)
        return out

    events_block = {
        "timeline": [_timeline_entry(ev) for ev in timeline],
        "goals": _event_dict_list(goals),
        "demos": _event_dict_list(demos),
        "kickoffs": _event_dict_list(kickoffs),
        "boost_pickups": _event_dict_list(pickups),
        "touches": _event_dict_list(touches),
        "challenges": _event_dict_list(challenges),
    }

    # Analysis per_player mapping
    per_team = analysis_out.get("per_team", {"blue": {}, "orange": {}})
    per_player_list = analysis_out.get("per_player", [])
    per_player_map: dict[str, Any] = {}
    for p in per_player_list:
        pid = p.get("player_id")
        if pid is None:
            continue
        per_player_map[str(pid)] = dict(p)

    # Downsample or normalize heatmaps to a minimal 4x4 grid for stable goldens
    def _min_grid() -> dict[str, Any]:
        return {
            "x_bins": 4,
            "y_bins": 4,
            "extent": {"xmin": -1.0, "xmax": 1.0, "ymin": -1.0, "ymax": 1.0},
            "values": [[0.0, 0.0, 0.0, 0.0] for _ in range(4)],
        }

    for pdata in per_player_map.values():
        hm = pdata.get("heatmaps")
        if isinstance(hm, dict):
            for key in (
                "position_occupancy_grid",
                "touch_density_grid",
                "boost_pickup_grid",
            ):
                grid = hm.get(key)
                if isinstance(grid, dict):
                    xb = int(grid.get("x_bins", 0) or 0)
                    yb = int(grid.get("y_bins", 0) or 0)
                    if xb != 4 or yb != 4:
                        hm[key] = _min_grid()
            # Some analyzers may emit 'boost_usage_grid'; normalize to schema-minimal
            if "boost_usage_grid" in hm and hm.get("boost_usage_grid") is not None:
                hm["boost_usage_grid"] = None
            # Ensure the key exists for fixture stability
            hm.setdefault("boost_usage_grid", None)
        # Normalize insights to empty for deterministic goldens
        if "insights" in pdata and isinstance(pdata["insights"], list):
            pdata["insights"] = []

    # Ensure heatmaps conform to schema for players (fill minimal grids)
    # Ensure required grids exist if analyzer omitted them
    for pdata in per_player_map.values():
        hm = pdata.get("heatmaps")
        if isinstance(hm, dict):
            hm.setdefault("position_occupancy_grid", _min_grid())
            hm.setdefault("touch_density_grid", _min_grid())
            hm.setdefault("boost_pickup_grid", _min_grid())

    # Metadata and quality
    recorded_hz = measure_frame_rate(frames)
    metadata = {
        "engine_build": "synthetic",
        "playlist": "UNKNOWN",
        "map": header.map_name or "unknown",
        "team_size": max(1, int(header.team_size or 1)),
        "overtime": False,
        "mutators": {},
        "match_guid": f"synthetic-{name}",
        "started_at_utc": "1970-01-01T00:00:00Z",
        "duration_seconds": float(header.match_length or 0.0),
        "recorded_frame_hz": float(recorded_hz),
        "total_frames": max(1, len(frames)),
        "coordinate_reference": {
            "side_wall_x": 4096,
            "back_wall_y": 5120,
            "ceiling_z": 2044,
        },
    }

    quality = {
        "parser": {
            "name": "synthetic",
            "version": "0.0.0",
            "parsed_header": True,
            "parsed_network_data": bool(frames),
            "crc_checked": False,
        },
        "warnings": list(getattr(header, "quality_warnings", []) or []),
    }

    report = {
        "replay_id": f"golden-{name}",
        "source_file": f"synthetic://{name}",
        "schema_version": "1.0.0",
        "generated_at_utc": "1970-01-01T00:00:00Z",
        "metadata": metadata,
        "quality": quality,
        "teams": teams_block,
        "players": players_block,
        "events": events_block,
        "analysis": {
            "per_team": per_team,
            "per_player": per_player_map,
            "coaching_insights": [],
        },
    }

    # Validate schema for safety
    validate_report(report)
    return report


def sanitize_for_golden(report: dict[str, Any]) -> dict[str, Any]:
    rpt = json.loads(json.dumps(report))  # deep copy
    rpt.pop("generated_at_utc", None)
    if "metadata" in rpt:
        rpt["metadata"].pop("started_at_utc", None)
    return rpt


def test_golden_header_only(tmp_path: Path):
    header = Header(
        playlist_id="unknown",
        map_name="unknown",
        team_size=1,
        team0_score=0,
        team1_score=0,
        match_length=0.0,
        players=[PlayerInfo(name="Alpha", team=0), PlayerInfo(name="Bravo", team=1)],
        quality_warnings=[],
    )

    frames: list[Frame] = []
    report = build_synthetic_report("header-only", header, frames)
    actual = sanitize_for_golden(report)

    golden_path = Path(__file__).parent / "goldens" / "header_only.json"
    with open(golden_path, "r", encoding="utf-8") as f:
        expected = json.load(f)

    assert actual == expected


def test_golden_synthetic_small(tmp_path: Path):
    header = Header(
        playlist_id="unknown",
        map_name="DFH Stadium",
        team_size=1,
        team0_score=0,
        team1_score=0,
        match_length=2.0,
        players=[PlayerInfo(name="Alpha", team=0), PlayerInfo(name="Bravo", team=1)],
        quality_warnings=[],
    )

    # Frames: kickoff at t=0.0 (ball at center, stationary), then ball moves
    frames = [
        Frame(
            timestamp=0.0,
            ball=BallFrame(
                position=Vec3(0.0, 0.0, 93.15),
                velocity=Vec3(0.0, 0.0, 0.0),
                angular_velocity=Vec3(0.0, 0.0, 0.0),
            ),
            players=[
                PlayerFrame(
                    "A",
                    0,
                    Vec3(0.0, -500.0, 17.0),
                    Vec3(0.0, 0.0, 0.0),
                    Vec3(0.0, 0.0, 0.0),
                    50,
                ),
                PlayerFrame(
                    "B",
                    1,
                    Vec3(0.0, 1000.0, 17.0),
                    Vec3(0.0, 0.0, 0.0),
                    Vec3(0.0, 0.0, 0.0),
                    50,
                ),
            ],
        ),
        Frame(
            timestamp=1.0,
            ball=BallFrame(
                position=Vec3(0.0, 120.0, 93.15),
                velocity=Vec3(0.0, 300.0, 0.0),
                angular_velocity=Vec3(0.0, 0.0, 0.0),
            ),
            players=[
                PlayerFrame(
                    "A",
                    0,
                    Vec3(0.0, -500.0, 17.0),
                    Vec3(0.0, 0.0, 0.0),
                    Vec3(0.0, 0.0, 0.0),
                    50,
                ),
                PlayerFrame(
                    "B",
                    1,
                    Vec3(0.0, 1000.0, 17.0),
                    Vec3(0.0, 0.0, 0.0),
                    Vec3(0.0, 0.0, 0.0),
                    50,
                ),
            ],
        ),
        Frame(
            timestamp=1.1,
            ball=BallFrame(
                position=Vec3(0.0, 150.0, 93.15),
                velocity=Vec3(0.0, 900.0, 0.0),
                angular_velocity=Vec3(0.0, 0.0, 0.0),
            ),
            players=[
                PlayerFrame(
                    "A",
                    0,
                    Vec3(0.0, 160.0, 17.0),
                    Vec3(0.0, 0.0, 0.0),
                    Vec3(0.0, 0.0, 0.0),
                    50,
                ),
                PlayerFrame(
                    "B",
                    1,
                    Vec3(0.0, 1000.0, 17.0),
                    Vec3(0.0, 0.0, 0.0),
                    Vec3(0.0, 0.0, 0.0),
                    50,
                ),
            ],
        ),
    ]

    report = build_synthetic_report("synthetic-small", header, frames)
    actual = sanitize_for_golden(report)

    golden_path = Path(__file__).parent / "goldens" / "synthetic_small.json"
    with open(golden_path, "r", encoding="utf-8") as f:
        expected = json.load(f)

    assert actual == expected
