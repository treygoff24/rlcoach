#!/usr/bin/env python3
"""Summarise boost pad telemetry dumps for parity analysis."""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable, Mapping


def _load_payload(path: Path) -> Mapping[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path} does not contain a JSON object payload")
    return data


def _event_kind(event: Mapping[str, Any]) -> str:
    return str(event.get("event", "unknown")).lower()


def _state_key(event: Mapping[str, Any]) -> str | None:
    state = event.get("state")
    if state is None:
        return None
    return f"{_event_kind(event)}:{str(state).upper()}"


def _expects_instigator(event: Mapping[str, Any]) -> bool:
    kind = _event_kind(event)
    if kind in {"pickup_state", "pickup_new"}:
        state = event.get("state")
        if state is None:
            return False
        return str(state).upper() == "COLLECTED"
    return False


def _summarise_events(events: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    events = list(events)
    event_counts: Counter[str] = Counter()
    state_counts: Counter[str] = Counter()
    actor_counts: defaultdict[int, Counter[str]] = defaultdict(Counter)
    resolved = 0
    unresolved = 0
    missing_instigator = 0
    unresolved_examples: list[tuple[int, str]] = []

    for event in events:
        kind = _event_kind(event)
        event_counts[kind] += 1

        state_key = _state_key(event)
        if state_key is not None:
            state_counts[state_key] += 1

        actor_id = event.get("actor_id")
        if isinstance(actor_id, int):
            actor_counts[actor_id][kind] += 1

        instigator = event.get("instigator_actor_id")
        resolved_actor = event.get("resolved_actor_id")
        if _expects_instigator(event):
            if instigator is None:
                missing_instigator += 1
            elif resolved_actor is not None:
                resolved += 1
            else:
                unresolved += 1
                if len(unresolved_examples) < 5:
                    frame_idx = event.get("frame_index", "?")
                    state_repr = state_key or kind
                    unresolved_examples.append((frame_idx, state_repr))

    actor_rollups = {
        actor_id: dict(sorted(counter.items()))
        for actor_id, counter in sorted(actor_counts.items())
    }

    return {
        "total_events": len(events),
        "event_counts": dict(sorted(event_counts.items())),
        "state_counts": dict(sorted(state_counts.items())),
        "resolved_events": resolved,
        "unresolved_events": unresolved,
        "missing_instigator": missing_instigator,
        "unresolved_examples": unresolved_examples,
        "actor_event_counts": actor_rollups,
    }


def render_summary(path: Path) -> str:
    payload = _load_payload(path)
    replay_path = payload.get("replay_path", path.stem)
    captured_at = payload.get("captured_at_utc", "unknown")
    max_frames = payload.get("max_frames", "n/a")
    flat_events = payload.get("flat_events") or []
    if not isinstance(flat_events, list):
        raise ValueError(f"{path} missing flat_events array")

    summary = _summarise_events(flat_events)
    unique_actors = sorted(summary["actor_event_counts"])

    lines = [
        f"Replay: {replay_path}",
        f"Captured: {captured_at}",
        f"Frames scanned: {max_frames}",
        f"Total boost events: {summary['total_events']}",
        f"Unique boost actors: {len(unique_actors)}",
    ]

    if summary["event_counts"]:
        lines.append("Events by type:")
        for kind, count in summary["event_counts"].items():
            lines.append(f"  - {kind}: {count}")

    if summary["state_counts"]:
        lines.append("States by outcome:")
        for state, count in summary["state_counts"].items():
            lines.append(f"  - {state}: {count}")

    resolved = summary["resolved_events"]
    unresolved = summary["unresolved_events"]
    total_with_instigator = resolved + unresolved
    if total_with_instigator > 0:
        pct = (resolved / total_with_instigator) * 100.0
        lines.append(
            f"Instigator resolution: {resolved}/{total_with_instigator} ({pct:.1f}%)"
        )
    if summary["missing_instigator"]:
        lines.append(f"Missing instigator_actor_id events: {summary['missing_instigator']}")
    if summary["unresolved_examples"]:
        example_str = ", ".join(
            f"frame {frame} ({state})" for frame, state in summary["unresolved_examples"]
        )
        lines.append(f"Sample unresolved events: {example_str}")

    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "telemetry",
        nargs="+",
        type=Path,
        help="Path(s) to telemetry JSON produced by collect_boost_telemetry.py",
    )
    args = parser.parse_args()

    for idx, path in enumerate(args.telemetry):
        if idx > 0:
            print()
        print(render_summary(path))


if __name__ == "__main__":
    main()
