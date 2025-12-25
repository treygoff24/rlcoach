"""Rust-based parser adapter shim (boxcars-backed).

This adapter attempts to import the compiled Rust extension module
(`rlreplay_rust`) built with pyo3. If available, it uses it to produce
real header information and a network frame iterator. If the Rust core
is not available, it degrades gracefully to a header-only path using the
ingest validator, with explicit quality warnings.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..ingest import ingest_replay
from .errors import HeaderParseError
from .interface import ParserAdapter
from .types import GoalHeader, Header, Highlight, NetworkFrames, PlayerInfo

try:  # best-effort import of Rust core
    import rlreplay_rust as _rust

    _RUST_AVAILABLE = True
except Exception:  # pragma: no cover - environment may not have the module
    _rust = None  # type: ignore
    _RUST_AVAILABLE = False


class RustAdapter(ParserAdapter):
    """Rust-backed adapter with graceful fallback."""

    @property
    def name(self) -> str:
        return "rust"

    @property
    def supports_network_parsing(self) -> bool:
        # Only claim support if the Rust core is importable
        return bool(_RUST_AVAILABLE)

    def _header_from_rust_dict(self, d: dict[str, Any]) -> Header:
        # Convert rust dict to Header dataclass
        players: list[PlayerInfo] = []
        for raw_player in d.get("players", []) or []:
            name = raw_player.get("name", "Unknown")
            team = raw_player.get("team")
            stats = raw_player.get("stats") or {}

            platform_id, platform_ids = self._extract_platform_ids(stats)
            camera_settings = self._extract_camera_settings(stats)
            loadout = self._extract_loadout(stats)
            score = (
                stats.get("Score")
                if isinstance(stats.get("Score"), (int, float))
                else 0
            )

            normalized_stats: dict[str, Any] = {}
            if isinstance(stats, dict):
                for key, value in stats.items():
                    if isinstance(value, dict) and "value" in value:
                        normalized_stats[key] = value.get("value")
                    else:
                        normalized_stats[key] = value

            players.append(
                PlayerInfo(
                    name=name,
                    team=team,
                    platform_id=platform_id,
                    score=int(score or 0),
                    platform_ids=platform_ids,
                    camera_settings=camera_settings,
                    loadout=loadout,
                    stats=normalized_stats,
                )
            )
        goals = []
        for g in d.get("goals", []) or []:
            goals.append(
                GoalHeader(
                    frame=int(g.get("frame")) if g.get("frame") is not None else None,
                    player_name=g.get("player_name"),
                    player_team=(
                        int(g.get("player_team"))
                        if g.get("player_team") is not None
                        else None
                    ),
                )
            )
        highlights = []
        for h in d.get("highlights", []) or []:
            highlights.append(
                Highlight(
                    frame=int(h.get("frame")) if h.get("frame") is not None else None,
                    ball_name=h.get("ball_name"),
                    car_name=h.get("car_name"),
                )
            )
        # Use warnings as provided by Rust core; avoid adding any *_stub markers
        warnings = list(d.get("quality_warnings", []))
        return Header(
            playlist_id=d.get("playlist_id"),
            map_name=d.get("map_name"),
            team_size=int(d.get("team_size", 0) or 0),
            team0_score=int(d.get("team0_score", 0) or 0),
            team1_score=int(d.get("team1_score", 0) or 0),
            match_length=float(d.get("match_length", 0.0) or 0.0),
            engine_build=d.get("engine_build"),
            match_guid=d.get("match_guid"),
            overtime=d.get("overtime"),
            mutators=d.get("mutators", {}),
            players=players,
            goals=goals,
            highlights=highlights,
            quality_warnings=warnings,
        )

    @staticmethod
    def _extract_platform_ids(
        stats: dict[str, Any],
    ) -> tuple[str | None, dict[str, str]]:
        platform_map = {
            "OnlinePlatform_Steam": "steam",
            "OnlinePlatform_Epic": "epic",
            "OnlinePlatform_Psn": "psn",
            "OnlinePlatform_Xbox": "xbox",
            "OnlinePlatform_Switch": "switch",
            "OnlinePlatform_WeGame": "wegame",
        }

        platform_ids: dict[str, str] = {}
        primary_platform_id: str | None = None

        # Extract platform type from Platform struct
        platform_struct = stats.get("Platform")
        primary_platform_key = None
        if isinstance(platform_struct, dict):
            raw_value = platform_struct.get("value") or platform_struct.get("Platform")
            if isinstance(raw_value, str):
                primary_platform_key = platform_map.get(raw_value, raw_value.lower())

        # Try PlayerID struct first (newer format), then UniqueId (boxcars format)
        player_id_struct = stats.get("PlayerID") or stats.get("UniqueId")
        if isinstance(player_id_struct, dict):
            # Steam UID - only use if non-zero (0 means missing/placeholder)
            uid = player_id_struct.get("Uid")
            if uid is not None and int(uid) != 0:
                platform_ids.setdefault("steam", str(uid))
                if primary_platform_key == "steam":
                    primary_platform_id = str(uid)

            # Epic Account ID
            epic_id = player_id_struct.get("EpicAccountId")
            if epic_id:
                platform_ids["epic"] = str(epic_id)
                if primary_platform_key == "epic":
                    primary_platform_id = str(epic_id)

            # PSN ID (nested structure)
            npid = player_id_struct.get("NpId")
            if isinstance(npid, dict):
                handle = npid.get("Handle")
                if isinstance(handle, dict):
                    data = handle.get("Data")
                    if data:
                        platform_ids["psn"] = str(data)
                        if primary_platform_key == "psn":
                            primary_platform_id = str(data)

            # Remote ID (another format used by boxcars)
            remote_id = player_id_struct.get("Remote")
            if isinstance(remote_id, dict):
                for rid_key, rid_val in remote_id.items():
                    if isinstance(rid_val, dict):
                        # Handle nested Remote structs like Steam(123456)
                        for _inner_k, inner_v in rid_val.items():
                            if inner_v and str(inner_v) != "0":
                                platform = rid_key.lower()
                                platform_ids.setdefault(platform, str(inner_v))
                                if primary_platform_id is None:
                                    primary_platform_id = str(inner_v)
                                    primary_platform_key = platform
                    elif rid_val and str(rid_val) != "0":
                        platform = rid_key.lower()
                        platform_ids.setdefault(platform, str(rid_val))
                        if primary_platform_id is None:
                            primary_platform_id = str(rid_val)
                            primary_platform_key = platform

        # Fallback: OnlineID (older replays)
        online_id = stats.get("OnlineID")
        if (
            primary_platform_id is None
            and online_id is not None
            and str(online_id) != "0"
        ):
            primary_platform_id = str(online_id)
            if primary_platform_key and primary_platform_key not in platform_ids:
                platform_ids[primary_platform_key] = primary_platform_id

        return primary_platform_id, platform_ids

    @staticmethod
    def _extract_camera_settings(stats: dict[str, Any]) -> dict[str, float] | None:
        camera_struct = stats.get("CameraSettings")
        if not isinstance(camera_struct, dict):
            return None

        result: dict[str, float] = {}
        for key, value in camera_struct.items():
            if key.startswith("_"):
                continue
            if isinstance(value, (int, float)):
                normalized_key = (
                    key.replace("Camera", "").replace("Settings", "").strip("_")
                )
                normalized_key = normalized_key or key
                result[normalized_key.lower()] = float(value)
        return result or None

    @staticmethod
    def _extract_loadout(stats: dict[str, Any]) -> dict[str, Any]:
        for key in ("Loadout", "PlayerLoadout", "LoadoutPaint", "LoadoutPaints"):
            loadout_struct = stats.get(key)
            if isinstance(loadout_struct, dict):
                loadout = {}
                for lk, lv in loadout_struct.items():
                    if lk.startswith("_"):
                        continue
                    loadout[lk.lower()] = lv
                if loadout:
                    return loadout
        return {}

    def parse_header(self, path: Path) -> Header:
        try:
            if _RUST_AVAILABLE and _rust is not None:
                # Use Rust implementation
                d = _rust.parse_header(str(path))  # returns dict-like
                if not isinstance(d, dict):  # defensive check
                    raise HeaderParseError(
                        str(path), "Rust core returned non-dict header"
                    )
                header = self._header_from_rust_dict(d)
                return header

            # Fallback path: reuse ingest for validation and build minimal header
            ingest_result = ingest_replay(path)
            quality_warnings = [
                "rust_core_unavailable_fallback_header_only",
                "network_data_unparsed_fallback_header_only",
            ]
            if ingest_result.get("warnings"):
                quality_warnings.extend(ingest_result["warnings"])  # type: ignore[index]

            players = [
                PlayerInfo(name="Unknown Player 1", team=0),
                PlayerInfo(name="Unknown Player 2", team=1),
            ]
            return Header(
                playlist_id="unknown",
                map_name="unknown",
                team_size=1,
                team0_score=0,
                team1_score=0,
                match_length=0.0,
                players=players,
                quality_warnings=quality_warnings,
            )
        except Exception as e:  # normalize to HeaderParseError
            raise HeaderParseError(str(path), f"Rust adapter failed: {e}") from e

    def parse_network(self, path: Path) -> NetworkFrames | None:
        if not _RUST_AVAILABLE or _rust is None:
            return None
        try:
            frames = _rust.iter_frames(str(path))  # Expect list of dict frames
            if not isinstance(frames, list):
                # Convert iterator/generator to list if needed
                try:
                    frames = list(frames)
                except Exception:
                    frames = []
            # Deduplicate per-frame player entries keyed by player_id to guard
            # against duplicate car component actors leaking through the bridge.
            for frame in frames:
                players = frame.get("players") if isinstance(frame, dict) else None
                if not isinstance(players, list):
                    continue
                unique_by_key: dict[str, Any] = {}
                order: list[str] = []
                anonymous_index = 0
                for player in players:
                    key: str
                    if isinstance(player, dict) and isinstance(
                        player.get("player_id"), str
                    ):
                        key = player["player_id"]  # keep stable key per player id
                    else:
                        key = f"__anon_{anonymous_index}"
                        anonymous_index += 1
                    if key not in unique_by_key:
                        order.append(key)
                    unique_by_key[key] = player
                frame["players"] = [unique_by_key[k] for k in order]
            # Measure sample rate from timestamps if available
            try:
                from ..normalize import measure_frame_rate

                hz = float(measure_frame_rate(frames))
            except Exception:
                hz = 30.0
            return NetworkFrames(frame_count=len(frames), sample_rate=hz, frames=frames)
        except Exception:
            # Degrade gracefully to header-only when network parsing fails
            # (e.g., malformed or synthetic test file)
            return None
