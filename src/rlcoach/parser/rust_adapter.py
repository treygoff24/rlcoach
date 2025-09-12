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
from ..normalize import measure_frame_rate
from .errors import HeaderParseError, NetworkParseError
from .interface import ParserAdapter
from .types import Header, NetworkFrames, PlayerInfo, GoalHeader

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
        players = [
            PlayerInfo(
                name=p.get("name", "Unknown"),
                platform_id=p.get("platform_id"),
                team=p.get("team"),
            )
            for p in d.get("players", [])
        ]
        goals = []
        for g in d.get("goals", []) or []:
            goals.append(
                GoalHeader(
                    frame=int(g.get("frame")) if g.get("frame") is not None else None,
                    player_name=g.get("player_name"),
                    player_team=(int(g.get("player_team")) if g.get("player_team") is not None else None),
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
            quality_warnings=warnings,
        )

    def parse_header(self, path: Path) -> Header:
        try:
            if _RUST_AVAILABLE and _rust is not None:
                # Use Rust implementation
                d = _rust.parse_header(str(path))  # returns dict-like
                if not isinstance(d, dict):  # defensive check
                    raise HeaderParseError(str(path), "Rust core returned non-dict header")
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
            # Measure sample rate from timestamps if available
            try:
                hz = float(measure_frame_rate(frames))
            except Exception:
                hz = 30.0
            return NetworkFrames(frame_count=len(frames), sample_rate=hz, frames=frames)
        except Exception as e:
            # Degrade gracefully to header-only when network parsing fails
            # (e.g., malformed or synthetic test file)
            return None
