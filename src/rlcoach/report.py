"""Report generator orchestrating the full analysis pipeline.

Builds a schema-conformant JSON report from a replay file using:
ingest → parser adapter → normalization → events → analyzers.

Provides header-only fallback via the null adapter and returns
deterministic success or error payloads. Includes helpers for
atomic file writes and schema validation.
"""

from __future__ import annotations

import datetime as _dt
import json
import os
from pathlib import Path
from typing import Any

from .analysis import aggregate_analysis
from .events import (
    build_timeline,
    detect_boost_pickups,
    detect_challenge_events,
    detect_demos,
    detect_goals,
    detect_kickoffs,
    detect_touches,
)
from .ingest import ingest_replay
from .normalize import build_timeline as build_normalized_frames
from .normalize import measure_frame_rate
from .parser import get_adapter
from .parser.types import NetworkFrames as NFType
from .schema import validate_report
from .utils.identity import build_player_identities
from .version import get_schema_version

_ALLOWED_PLAYLISTS = {
    "DUEL",
    "DOUBLES",
    "STANDARD",
    "CHAOS",
    "PRIVATE",
    "EXTRA_MODE",
    "UNKNOWN",
}

# Rocket League numeric playlist ID mappings
# Reference: https://wiki.rlbot.org/botmaking/useful-game-values/#playlist-ids
_PLAYLIST_ID_MAP = {
    # Numeric playlist IDs
    "1": "DUEL",
    "2": "DOUBLES",
    "3": "STANDARD",
    "4": "CHAOS",
    "10": "DUEL",  # Ranked Solo Duel
    "11": "DOUBLES",  # Ranked Doubles
    "13": "STANDARD",  # Ranked Standard
    "6": "PRIVATE",  # Private Match
    "22": "EXTRA_MODE",  # Dropshot
    "23": "EXTRA_MODE",  # Hoops
    "24": "EXTRA_MODE",  # Snow Day
    "27": "EXTRA_MODE",  # Rumble
    # Inferred from MatchType + TeamSize (when PlaylistID missing)
    "inferred_1": "DUEL",
    "inferred_2": "DOUBLES",
    "inferred_3": "STANDARD",
    "inferred_4": "CHAOS",
    "tournament": "STANDARD",  # Tournament matches (treat as competitive)
    "private": "PRIVATE",
}


def _utc_now_iso() -> str:
    return (
        _dt.datetime.now(_dt.timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _normalize_playlist_id(raw_value: Any) -> tuple[str, list[str]]:
    """Normalize playlist identifiers to schema enum, collect warnings."""
    if raw_value is None:
        return "UNKNOWN", []

    playlist_str = str(raw_value).strip()
    if not playlist_str or playlist_str == "unknown":
        return "UNKNOWN", []

    # Check numeric ID mapping first
    if playlist_str in _PLAYLIST_ID_MAP:
        return _PLAYLIST_ID_MAP[playlist_str], []

    # Try string normalization
    normalized = playlist_str.upper().replace("-", "_").replace(" ", "_")
    if normalized in _ALLOWED_PLAYLISTS:
        return normalized, []

    warning = f"unrecognized_playlist_value:{playlist_str}"
    return "UNKNOWN", [warning]


def _serialize_value(obj: Any) -> Any:
    if hasattr(obj, "__dict__"):
        d = {k: v for k, v in obj.__dict__.items() if not k.startswith("_")}
        for kk, vv in list(d.items()):
            if hasattr(vv, "_asdict"):
                d[kk] = vv._asdict()
        return d
    if hasattr(obj, "_asdict"):
        return {k: _serialize_value(v) for k, v in obj._asdict().items()}
    return obj


def _timeline_event_to_dict(ev: Any) -> dict[str, Any]:
    entry: dict[str, Any] = {}
    for key in ("t", "type", "frame", "player_id", "team", "data"):
        if not hasattr(ev, key):
            continue
        value = getattr(ev, key)
        if value is None and key not in {"t", "type"}:
            continue
        entry[key] = _serialize_value(value)
    return entry


def generate_report(
    replay_path: Path, header_only: bool = False, adapter_name: str = "rust"
) -> dict[str, Any]:
    """Generate a schema-conformant replay report.

    On failure to read/parse the replay, returns the error contract:
    { "error": "unreadable_replay_file", "details": str(e) }
    """
    try:
        # Ingest for file metadata and validation
        ingest_info = ingest_replay(replay_path)

        # Parse header via adapter. Prefer rust adapter when available for richer header data,
        # but fall back to null adapter if anything goes wrong.
        try:
            adapter = get_adapter(adapter_name)
            header = adapter.parse_header(replay_path)
        except Exception:
            adapter = get_adapter("null")
            header = adapter.parse_header(replay_path)

        # Network frames optional (null adapter returns None)
        raw_frames = None
        if not header_only and adapter.supports_network_parsing:
            raw_frames = adapter.parse_network(replay_path)

        # Normalize timeline
        # Normalize timeline; accept either a list of frames or a NetworkFrames wrapper
        frames_input = []
        if raw_frames is None:
            frames_input = []
        elif isinstance(raw_frames, NFType):
            frames_input = raw_frames.frames
        else:
            frames_input = raw_frames

        normalized_frames = build_normalized_frames(header, frames_input)
        network_data_available = bool(frames_input)

        # Events detection (can be empty in header-only)
        touches = detect_touches(normalized_frames)
        goals = detect_goals(normalized_frames, header)
        demos = detect_demos(normalized_frames)
        kickoffs = detect_kickoffs(normalized_frames, header)
        pickups = detect_boost_pickups(normalized_frames)
        challenges = detect_challenge_events(normalized_frames, touches)
        events_dict: dict[str, list[Any]] = {
            "goals": goals,
            "demos": demos,
            "kickoffs": kickoffs,
            "boost_pickups": pickups,
            "touches": touches,
            "challenges": challenges,
        }
        timeline = build_timeline(events_dict)

        # Aggregate analysis
        analysis_out = aggregate_analysis(normalized_frames, events_dict, header)

        # Build top-level fields
        replay_id = ingest_info.get("sha256", "unknown")
        schema_version = get_schema_version()

        # Metadata
        recorded_hz = measure_frame_rate(normalized_frames)
        playlist_value, playlist_warnings = _normalize_playlist_id(
            getattr(header, "playlist_id", None)
            if hasattr(header, "playlist_id")
            else None
        )

        match_duration = float(
            normalized_frames[-1].timestamp if normalized_frames else 0.0
        )

        metadata = {
            "engine_build": getattr(header, "engine_build", None) or "unknown",
            "playlist": playlist_value,
            "map": header.map_name or "unknown",
            "team_size": max(1, int(header.team_size or 1)),
            "overtime": bool(getattr(header, "overtime", False) or False),
            "mutators": getattr(header, "mutators", {}) or {},
            "match_guid": getattr(header, "match_guid", None) or "unknown",
            "started_at_utc": _utc_now_iso(),
            "duration_seconds": match_duration,
            "recorded_frame_hz": float(recorded_hz),
            "total_frames": max(1, len(normalized_frames)),
            "coordinate_reference": {
                "side_wall_x": 4096,
                "back_wall_y": 5120,
                "ceiling_z": 2044,
            },
        }

        # Quality
        crc_info = ingest_info.get("crc_check", {})
        crc_msg = str(crc_info.get("message", ""))
        crc_passed = bool(crc_info.get("passed", False))
        # Until real CRC is implemented, do not claim it was checked
        crc_checked_flag = (
            False if "not yet implemented" in crc_msg.lower() else crc_passed
        )

        quality = {
            "parser": {
                "name": adapter.name,
                "version": "0.1.0",
                "parsed_header": True,
                "parsed_network_data": network_data_available,
                "crc_checked": crc_checked_flag,
            },
            "warnings": (
                header.quality_warnings if hasattr(header, "quality_warnings") else []
            ),
        }
        if playlist_warnings:
            quality["warnings"] = list(quality["warnings"]) + playlist_warnings
        if not crc_checked_flag:
            quality["warnings"] = list(quality["warnings"]) + [
                "CRC not verified (stubbed)"
            ]
        if adapter.supports_network_parsing and not network_data_available:
            quality["warnings"] = list(quality["warnings"]) + [
                "network_data_unavailable_fell_back_to_header_only"
            ]
        # Incorporate analysis warnings if present
        if isinstance(analysis_out, dict) and analysis_out.get("warnings"):
            quality["warnings"] = list(quality["warnings"]) + list(analysis_out["warnings"])  # type: ignore[index]

        # Teams block
        # Construct minimal players array based on header
        team_players: dict[str, list[str]] = {"BLUE": [], "ORANGE": []}
        players_block: list[dict[str, Any]] = []

        identities = build_player_identities(getattr(header, "players", []))
        if identities:
            for identity in identities:
                player_info = header.players[identity.header_index]
                implied_team_index = (
                    player_info.team if player_info.team is not None else 0
                )
                team_name = (
                    identity.team
                    if identity.team in {"BLUE", "ORANGE"}
                    else ("BLUE" if implied_team_index == 0 else "ORANGE")
                )
                team_players.setdefault(team_name, [])
                team_players[team_name].append(identity.canonical_id)

                platform_ids = dict(identity.platform_ids)
                camera_payload = getattr(player_info, "camera_settings", None) or {}
                loadout_payload = getattr(player_info, "loadout", None) or {}

                players_block.append(
                    {
                        "player_id": identity.canonical_id,
                        "display_name": identity.display_name,
                        "team": team_name,
                        "platform_ids": platform_ids,
                        "camera": camera_payload,
                        "loadout": loadout_payload,
                    }
                )

        if not players_block:
            # Ensure at least one dummy player per schema requirement
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

        # Events block (serialize dataclasses to dicts)
        goal_dicts: list[dict[str, Any]] = []
        for g in goals:
            data = {k: _serialize_value(getattr(g, k)) for k in g.__dataclass_fields__.keys()}  # type: ignore[attr-defined]
            if data.get("scorer") is None:
                data["scorer"] = "UNKNOWN"
            goal_dicts.append(data)

        events_block = {
            "timeline": [_timeline_event_to_dict(ev) for ev in timeline],
            "goals": goal_dicts,
            "demos": [{k: _serialize_value(getattr(d, k)) for k in d.__dataclass_fields__.keys()} for d in demos],  # type: ignore[attr-defined]
            "kickoffs": [
                {k: _serialize_value(getattr(kf, k)) for k in kf.__dataclass_fields__.keys()} for kf in kickoffs  # type: ignore[attr-defined]
            ],
            "boost_pickups": [
                {k: _serialize_value(getattr(bp, k)) for k in bp.__dataclass_fields__.keys()} for bp in pickups  # type: ignore[attr-defined]
            ],
            "touches": [
                {
                    "t": t.t,
                    "frame": t.frame,
                    "player_id": t.player_id,
                    "location": _serialize_value(t.location),
                    "ball_speed_kph": t.ball_speed_kph,
                    "outcome": t.outcome,
                    "is_save": t.is_save,
                    "touch_context": (
                        t.touch_context.value
                        if hasattr(t.touch_context, "value")
                        else str(t.touch_context)
                    ),
                    "car_height": t.car_height,
                    "is_first_touch": t.is_first_touch,
                }
                for t in touches
            ],
            "challenges": [
                {k: _serialize_value(getattr(ch, k)) for k in ch.__dataclass_fields__.keys()} for ch in challenges  # type: ignore[attr-defined]
            ],
        }

        # Analysis block: adapt per_player list -> mapping keyed by player_id
        per_team = analysis_out.get("per_team", {"blue": {}, "orange": {}})
        per_player_list = analysis_out.get("per_player", [])
        per_player_map: dict[str, Any] = {}
        for p in per_player_list:
            pid = p.get("player_id", None)
            if pid is None:
                continue
            per_player_map[str(pid)] = dict(p)

        analysis_block = {
            "per_team": per_team,
            "per_player": per_player_map,
            "coaching_insights": analysis_out.get("coaching_insights", []),
        }
        report = {
            "replay_id": replay_id,
            "source_file": str(replay_path),
            "schema_version": schema_version,
            "generated_at_utc": _utc_now_iso(),
            "metadata": metadata,
            "quality": quality,
            "teams": teams_block,
            "players": players_block,
            "events": events_block,
            "analysis": analysis_block,
        }

        # Validate before returning
        validate_report(report)
        return report

    except Exception as e:  # Catch any failure and map to error contract
        return {"error": "unreadable_replay_file", "details": str(e)}


def write_report_atomically(
    report: dict[str, Any], out_path: Path, pretty: bool = False
) -> None:
    """Write JSON file atomically to avoid partial writes."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = out_path.with_suffix(out_path.suffix + ".tmp")
    try:
        with open(temp_path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2 if pretty else None)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp_path, out_path)
    finally:
        if temp_path.exists():
            try:
                temp_path.unlink()
            except OSError:
                pass
