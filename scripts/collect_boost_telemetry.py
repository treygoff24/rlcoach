#!/usr/bin/env python3
"""Collect boost pad telemetry for the first N frames of a replay.

Outputs a JSON payload that mirrors the debug_first_frames boost events while
adding lightweight aggregation for downstream parity analysis.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


def _canonical_state(event: Mapping[str, Any]) -> str | None:
    state = event.get("state")
    if state is None:
        return None
    return str(state).upper()


def _event_kind(event: Mapping[str, Any]) -> str:
    return str(event.get("event", "unknown")).lower()


class RustModuleNotFoundError(ImportError):
    """Raised when rlreplay_rust module is not available."""


def _load_frames(replay_path: Path, max_frames: int) -> Sequence[Mapping[str, Any]]:
    try:
        import rlreplay_rust as rlreplay_rust
    except ModuleNotFoundError as exc:
        raise RustModuleNotFoundError(
            "rlreplay_rust module not available. Run `make rust-dev` first."
        ) from exc

    frames = rlreplay_rust.debug_first_frames(str(replay_path), int(max_frames))
    # Defensive copy to avoid surprises if the caller mutates
    return list(frames)


def _build_summary(flat_events: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    event_counts: Counter[str] = Counter()
    state_counts: Counter[str] = Counter()
    actor_counts: Counter[int] = Counter()

    for event in flat_events:
        kind = _event_kind(event)
        event_counts[kind] += 1
        state = _canonical_state(event)
        if state is not None:
            state_counts[f"{kind}:{state}"] += 1
        actor_id = event.get("actor_id")
        if isinstance(actor_id, int):
            actor_counts[actor_id] += 1

    return {
        "total_events": sum(event_counts.values()),
        "event_counts": dict(sorted(event_counts.items())),
        "state_counts": dict(sorted(state_counts.items())),
        "actor_event_counts": dict(sorted(actor_counts.items())),
    }


def collect_payload(
    replay_path: Path, max_frames: int, include_frames: bool
) -> dict[str, Any]:
    frames = _load_frames(replay_path, max_frames)
    condensed_frames = []
    flat_events = []

    for frame in frames:
        frame_index = int(frame.get("frame_index", -1))
        timestamp = float(frame.get("timestamp", 0.0))
        boost_events = [
            {**event, "frame_index": frame_index, "timestamp": event.get("timestamp", timestamp)}
            for event in frame.get("boost_events", []) or []
        ]
        flat_events.extend(boost_events)
        condensed_frames.append(
            {
                "frame_index": frame_index,
                "timestamp": timestamp,
                "boost_events": boost_events,
            }
        )

    payload: dict[str, Any] = {
        "replay_path": str(replay_path),
        "replay_name": replay_path.stem,
        "max_frames": max_frames,
        "captured_at_utc": datetime.now(timezone.utc).isoformat(),
        "flat_events": flat_events,
        "summary": _build_summary(flat_events),
    }
    if include_frames:
        payload["frames"] = condensed_frames
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("replay", type=Path, help="Path to the .replay file")
    parser.add_argument(
        "--max-frames",
        type=int,
        default=180,
        help="Number of frames to capture (default: 180)",
    )
    parser.add_argument(
        "--out",
        type=Path,
        help="Optional output file. Defaults to stdout when omitted.",
    )
    parser.add_argument(
        "--frames",
        action="store_true",
        help="Include per-frame boost_events in addition to the flattened view.",
    )
    parser.add_argument(
        "--pretty",
        action="store_true",
        help="Pretty-print JSON output (indent=2).",
    )
    args = parser.parse_args()

    payload = collect_payload(args.replay, args.max_frames, include_frames=args.frames)

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(
            json.dumps(payload, indent=2 if args.pretty else None),
            encoding="utf-8",
        )
    else:
        print(json.dumps(payload, indent=2 if args.pretty else None))


if __name__ == "__main__":
    main()
