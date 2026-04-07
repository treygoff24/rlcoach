#!/usr/bin/env python3
"""Corpus health harness for parser reliability diagnostics."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

from rlcoach.parser import get_adapter
from rlcoach.parser.types import Header, NetworkFrames


def _parse_roots(raw_roots: str) -> list[Path]:
    roots: list[Path] = []
    for item in raw_roots.split(","):
        candidate = item.strip()
        if candidate:
            roots.append(Path(candidate))
    return roots


def _discover_replays(roots: list[Path]) -> list[Path]:
    files: list[Path] = []
    for root in roots:
        if root.is_file() and root.suffix.lower() == ".replay":
            files.append(root)
            continue
        if not root.exists() or not root.is_dir():
            continue
        files.extend(p for p in root.rglob("*.replay") if p.is_file())
    return sorted(set(files))


def _match_type_bucket(team_size: int | None) -> str:
    if not isinstance(team_size, int) or team_size <= 0:
        return "unknown"
    return f"{team_size}v{team_size}"


def _header_buckets(header: Header | None) -> tuple[str, str, str]:
    if header is None:
        return ("unknown", "unknown", "unknown")
    playlist = (header.playlist_id or "unknown").strip() or "unknown"
    return (
        playlist,
        _match_type_bucket(header.team_size),
        (header.engine_build or "unknown").strip() or "unknown",
    )


def _evaluate_replay(path: Path, adapter_name: str) -> dict[str, Any]:
    adapter = get_adapter(adapter_name)
    header: Header | None = None
    header_ok = False
    network_ok = False
    network_status = "unavailable"
    error_code: str | None = None
    non_empty_player_frame_coverage = 0.0
    player_identity_coverage = 0.0
    usable_network_parse = False
    non_empty_player_frames = 0
    network_frame_count = 0
    players_with_identity = 0
    expected_players = 0

    try:
        header = adapter.parse_header(path)
        header_ok = True
    except Exception:
        error_code = "header_parse_error"

    if header_ok and adapter.supports_network_parsing:
        try:
            network = adapter.parse_network(path)
        except Exception:
            network = None
            error_code = "network_parse_exception"

        if isinstance(network, NetworkFrames):
            diagnostics = network.diagnostics
            network_frame_count = len(network.frames)
            non_empty_player_frames = sum(
                1
                for frame in network.frames
                if isinstance(frame, dict) and isinstance(frame.get("players"), list) and frame["players"]
            )
            unique_player_ids = {
                str(player.get("player_id"))
                for frame in network.frames
                if isinstance(frame, dict)
                for player in (frame.get("players") or [])
                if isinstance(player, dict) and player.get("player_id")
            }
            players_with_identity = len(unique_player_ids)
            declared_players = len(header.players) if header is not None else 0
            expected_players = max(declared_players, players_with_identity)
            non_empty_player_frame_coverage = (
                non_empty_player_frames / network_frame_count if network_frame_count else 0.0
            )
            player_identity_coverage = (
                min(1.0, players_with_identity / expected_players)
                if expected_players
                else 0.0
            )
            if diagnostics is None:
                network_ok = bool(network.frames)
                network_status = "ok" if network_ok else "degraded"
                if not network_ok and error_code is None:
                    error_code = "network_frames_empty"
            else:
                network_status = diagnostics.status
                network_ok = diagnostics.status == "ok"
                if diagnostics.error_code:
                    error_code = diagnostics.error_code
                elif diagnostics.status == "degraded" and error_code is None:
                    error_code = "network_degraded_unknown"
            usable_network_parse = (
                network_status == "ok"
                and network_frame_count > 0
                and non_empty_player_frame_coverage >= 0.5
                and player_identity_coverage >= 0.5
            )
        elif network is None:
            network_status = "unavailable"
            if error_code is None:
                error_code = "network_data_unavailable"
        else:
            network_status = "degraded"
            if error_code is None:
                error_code = "network_payload_invalid"
    elif header_ok:
        network_status = "unavailable"
        if error_code is None:
            error_code = "network_parsing_not_supported"

    playlist, match_type, engine_build = _header_buckets(header)
    return {
        "path": str(path),
        "header_ok": header_ok,
        "network_ok": network_ok,
        "network_status": network_status,
        "usable_network_parse": usable_network_parse,
        "error_code": error_code,
        "playlist": playlist,
        "match_type": match_type,
        "engine_build": engine_build,
        "non_empty_player_frame_coverage": non_empty_player_frame_coverage,
        "player_identity_coverage": player_identity_coverage,
        "network_frame_count": network_frame_count,
        "non_empty_player_frames": non_empty_player_frames,
        "players_with_identity": players_with_identity,
        "expected_players": expected_players,
    }


def _build_summary(records: list[dict[str, Any]], top_n: int = 5) -> dict[str, Any]:
    total = len(records)
    header_success = sum(1 for record in records if record["header_ok"])
    network_success = sum(1 for record in records if record["network_ok"])
    degraded_count = sum(
        1 for record in records if record["network_status"] == "degraded"
    )
    usable_network_parse_count = sum(
        1 for record in records if record["usable_network_parse"]
    )

    error_counter = Counter(
        record["error_code"] for record in records if record["error_code"]
    )
    playlist_counter = Counter(record["playlist"] for record in records)
    match_type_counter = Counter(record["match_type"] for record in records)
    engine_build_counter = Counter(record["engine_build"] for record in records)

    avg_non_empty_player_frame_coverage = (
        sum(record["non_empty_player_frame_coverage"] for record in records) / total
        if total
        else 0.0
    )
    avg_player_identity_coverage = (
        sum(record["player_identity_coverage"] for record in records) / total
        if total
        else 0.0
    )

    return {
        "total": total,
        "header_success_rate": (header_success / total) if total else 0.0,
        "network_success_rate": (network_success / total) if total else 0.0,
        "usable_network_parse_rate": (
            usable_network_parse_count / total if total else 0.0
        ),
        "degraded_count": degraded_count,
        "avg_non_empty_player_frame_coverage": avg_non_empty_player_frame_coverage,
        "avg_player_identity_coverage": avg_player_identity_coverage,
        "top_error_codes": [
            {"error_code": code, "count": count}
            for code, count in error_counter.most_common(top_n)
        ],
        "corpus_metadata": {
            "playlist_buckets": dict(sorted(playlist_counter.items())),
            "match_type_buckets": dict(sorted(match_type_counter.items())),
            "engine_build_buckets": dict(sorted(engine_build_counter.items())),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Measure replay parser corpus health and diagnostics rates."
    )
    parser.add_argument(
        "--roots",
        default="replays,Replay_files",
        help="Comma-separated replay roots/files (default: replays,Replay_files).",
    )
    parser.add_argument(
        "--adapter",
        default="rust",
        help="Parser adapter to use (default: rust).",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Optional limit on replay count.",
    )
    parser.add_argument(
        "--top-errors",
        type=int,
        default=5,
        help="How many error codes to include in top_error_codes.",
    )
    parser.add_argument(
        "--dry",
        action="store_true",
        help="Skip file scanning/parsing and emit an empty summary schema.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit JSON summary.",
    )
    args = parser.parse_args()

    records: list[dict[str, Any]]
    if args.dry:
        records = []
    else:
        roots = _parse_roots(args.roots)
        files = _discover_replays(roots)
        if args.limit is not None and args.limit >= 0:
            files = files[: args.limit]
        records = [_evaluate_replay(path, args.adapter) for path in files]

    summary = _build_summary(records, top_n=max(1, args.top_errors))
    if args.json:
        print(json.dumps(summary, indent=2, sort_keys=True))
    else:
        print(
            "total={total} header_success_rate={header:.3f} "
            "network_success_rate={network:.3f} usable_network_parse_rate={usable:.3f} "
            "avg_non_empty_player_frame_coverage={frame_cov:.3f} "
            "avg_player_identity_coverage={identity_cov:.3f} degraded_count={degraded}".format(
                total=summary["total"],
                header=summary["header_success_rate"],
                network=summary["network_success_rate"],
                usable=summary["usable_network_parse_rate"],
                frame_cov=summary["avg_non_empty_player_frame_coverage"],
                identity_cov=summary["avg_player_identity_coverage"],
                degraded=summary["degraded_count"],
            )
        )
        print(json.dumps(summary["corpus_metadata"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
