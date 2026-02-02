"""Simple offline CLI viewer for replay reports.

Usage:
    python -m rlcoach.ui view examples/replay_report.success.json

This pretty-prints teams, players, and a few key metrics. It performs
no network calls and reads local JSON only.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def _print(s: str) -> None:
    # Isolate for easy testing/capture
    print(s)


def summarize_report(data: dict[str, Any], focus_player: str | None = None) -> str:
    lines: list[str] = []
    meta = data.get("metadata", {})
    teams = data.get("teams", {})
    players = data.get("players", [])
    analysis = data.get("analysis", {})

    # Header
    lines.append("Replay Summary")
    lines.append("-")
    lines.append(
        f"Playlist: {meta.get('playlist', 'UNKNOWN')} | "
        f"Map: {meta.get('map', 'UNKNOWN')} | "
        f"Team Size: {meta.get('team_size', '?')}"
    )
    lines.append(
        f"Duration: {meta.get('duration_seconds', '?')}s | "
        f"Frames: {meta.get('total_frames', '?')} @ "
        f"{meta.get('recorded_frame_hz', '?')} Hz"
    )

    # Teams
    blue = teams.get("blue", {})
    orange = teams.get("orange", {})
    lines.append("")
    lines.append("Teams")
    lines.append("-")
    lines.append(
        f"BLUE: {blue.get('score', '?')} — Players: "
        f"{', '.join(blue.get('players', []))}"
    )
    lines.append(
        f"ORANGE: {orange.get('score', '?')} — Players: "
        f"{', '.join(orange.get('players', []))}"
    )

    # Players
    lines.append("")
    lines.append("Players")
    lines.append("-")
    for p in players:
        name = p.get("display_name", p.get("player_id", "?"))
        team = p.get("team", "?")
        if not focus_player or focus_player.lower() in str(name).lower():
            lines.append(f"- {name} [{team}]")

    # Key metrics per team (subset)
    per_team = analysis.get("per_team", {})
    lines.append("")
    lines.append("Key Metrics")
    lines.append("-")
    for team_key in ("blue", "orange"):
        t = per_team.get(team_key, {})
        fund = t.get("fundamentals", {})
        boost = t.get("boost", {})
        move = t.get("movement", {})
        lines.append(
            f"{team_key.upper()}: goals {fund.get('goals','?')}, "
            f"shots {fund.get('shots','?')}, saves {fund.get('saves','?')} | "
            f"avg_speed_kph {move.get('avg_speed_kph','?')} | "
            f"avg_boost {boost.get('avg_boost','?')}"
        )

    # Optional per-player section
    if focus_player:
        per_player = data.get("analysis", {}).get("per_player", {})
        # Find player id by display name match
        target_id = None
        for p in players:
            if focus_player.lower() in str(p.get("display_name", "")).lower():
                target_id = p.get("player_id")
                break
        if target_id and target_id in per_player:
            lines.append("")
            lines.append(f"Player Focus — {focus_player}")
            lines.append("-")
            pf = per_player[target_id]
            for section in (
                "fundamentals",
                "boost",
                "movement",
                "positioning",
                "passing",
                "challenges",
                "kickoffs",
            ):
                if section in pf:
                    lines.append(f"{section}: {pf[section]}")

    return "\n".join(lines)


def cmd_view(path: Path, focus_player: str | None = None) -> int:
    try:
        data = json.loads(Path(path).read_text())
    except FileNotFoundError:
        _print(f"Error: file not found: {path}")
        return 2
    except json.JSONDecodeError as e:
        _print(f"Error: invalid JSON in {path}: {e}")
        return 2

    summary = summarize_report(data, focus_player=focus_player)
    _print(summary)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Offline viewer for RLCoach JSON reports"
    )
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_view = sub.add_parser("view", help="Pretty-print a JSON report")
    p_view.add_argument("json_path", type=str, help="Path to report JSON")
    p_view.add_argument(
        "--player",
        type=str,
        default=None,
        help="Filter and show per-player details by display name",
    )

    args = parser.parse_args(argv)
    if args.cmd == "view":
        return cmd_view(Path(args.json_path), focus_player=args.player)

    parser.print_help()
    return 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
