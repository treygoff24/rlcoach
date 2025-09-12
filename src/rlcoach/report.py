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
    detect_boost_pickups,
    detect_demos,
    detect_goals,
    detect_kickoffs,
    detect_touches,
    build_timeline,
)
from .ingest import ingest_replay
from .normalize import build_timeline as build_normalized_frames, measure_frame_rate
from .parser.types import NetworkFrames as NFType
from .parser import get_adapter
from .schema import validate_report
from .version import get_schema_version


def _utc_now_iso() -> str:
    return _dt.datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def generate_report(replay_path: Path, header_only: bool = False, adapter_name: str = "rust") -> dict[str, Any]:
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

        # Events detection (can be empty in header-only)
        goals = detect_goals(normalized_frames, header)
        demos = detect_demos(normalized_frames)
        kickoffs = detect_kickoffs(normalized_frames, header)
        pickups = detect_boost_pickups(normalized_frames)
        touches = detect_touches(normalized_frames)
        events_dict: dict[str, list[Any]] = {
            "goals": goals,
            "demos": demos,
            "kickoffs": kickoffs,
            "boost_pickups": pickups,
            "touches": touches,
        }
        timeline = build_timeline(events_dict)

        # Aggregate analysis
        analysis_out = aggregate_analysis(normalized_frames, events_dict, header)

        # Build top-level fields
        replay_id = ingest_info.get("sha256", "unknown")
        schema_version = get_schema_version()

        # Metadata
        recorded_hz = measure_frame_rate(normalized_frames)
        metadata = {
            "engine_build": getattr(header, "engine_build", None) or "unknown",
            "playlist": "UNKNOWN",
            "map": header.map_name or "unknown",
            "team_size": max(1, int(header.team_size or 1)),
            "overtime": bool(getattr(header, "overtime", False) or False),
            "mutators": getattr(header, "mutators", {}) or {},
            "match_guid": "unknown",
            "started_at_utc": _utc_now_iso(),
            "duration_seconds": float(header.match_length or 0.0),
            "recorded_frame_hz": float(recorded_hz),
            "total_frames": max(1, len(normalized_frames)),
            "coordinate_reference": {
                "side_wall_x": 4096,
                "back_wall_y": 5120,
                "ceiling_z": 2044,
            },
        }

        # Quality
        quality = {
            "parser": {
                "name": adapter.name,
                "version": "0.1.0",
                "parsed_header": True,
                "parsed_network_data": bool(frames_input),
                "crc_checked": ingest_info.get("crc_check", {}).get("passed", False),
            },
            "warnings": (header.quality_warnings if hasattr(header, "quality_warnings") else []),
        }
        # Incorporate analysis warnings if present
        if isinstance(analysis_out, dict) and analysis_out.get("warnings"):
            quality["warnings"] = list(quality["warnings"]) + list(analysis_out["warnings"])  # type: ignore[index]

        # Teams block
        # Construct minimal players array based on header
        team_players: dict[str, list[str]] = {"BLUE": [], "ORANGE": []}
        players_block = []
        for i, p in enumerate(header.players or []):
            pid = f"player_{i}"
            tname = "BLUE" if (p.team or 0) == 0 else "ORANGE"
            team_players[tname].append(pid)
            players_block.append(
                {
                    "player_id": pid,
                    "display_name": p.name or f"Player {i}",
                    "team": tname,
                    "platform_ids": {},
                    "camera": {},
                    "loadout": {},
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
            "blue": {"name": "BLUE", "score": int(header.team0_score or 0), "players": team_players["BLUE"]},
            "orange": {"name": "ORANGE", "score": int(header.team1_score or 0), "players": team_players["ORANGE"]},
        }

        # Events block (serialize dataclasses to dicts)
        def _asdict(obj: Any) -> Any:
            if hasattr(obj, "__dict__"):
                d = {k: v for k, v in obj.__dict__.items() if not k.startswith("_")}
                # Convert Vec3 NamedTuples to plain dicts
                for kk, vv in list(d.items()):
                    if hasattr(vv, "_asdict"):
                        d[kk] = vv._asdict()
                return d
            return obj

        events_block = {
            "timeline": [
                {k: _asdict(getattr(ev, k)) for k in ("t", "frame", "type", "player_id", "team", "data") if hasattr(ev, k)}
                for ev in timeline
            ],
            "goals": [{k: _asdict(getattr(g, k)) for k in g.__dataclass_fields__.keys()} for g in goals],  # type: ignore[attr-defined]
            "demos": [{k: _asdict(getattr(d, k)) for k in d.__dataclass_fields__.keys()} for d in demos],  # type: ignore[attr-defined]
            "kickoffs": [
                {k: _asdict(getattr(kf, k)) for k in kf.__dataclass_fields__.keys()} for kf in kickoffs  # type: ignore[attr-defined]
            ],
            "boost_pickups": [
                {k: _asdict(getattr(bp, k)) for k in bp.__dataclass_fields__.keys()} for bp in pickups  # type: ignore[attr-defined]
            ],
            "touches": [{k: _asdict(getattr(t, k)) for k in t.__dataclass_fields__.keys()} for t in touches],  # type: ignore[attr-defined]
        }

        # Analysis block: adapt per_player list -> mapping keyed by player_id
        per_team = analysis_out.get("per_team", {"blue": {}, "orange": {}})
        per_player_list = analysis_out.get("per_player", [])
        per_player_map: dict[str, Any] = {}
        for p in per_player_list:
            pid = p.get("player_id", None)
            if pid is None:
                continue
            pp = dict(p)
            pp.pop("player_id", None)
            per_player_map[str(pid)] = pp

        analysis_block = {
            "per_team": per_team,
            "per_player": per_player_map,
            "coaching_insights": analysis["coaching_insights"],
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


def write_report_atomically(report: dict[str, Any], out_path: Path, pretty: bool = False) -> None:
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
