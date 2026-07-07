#!/usr/bin/env python3
"""Bucket replay corpus headers by Rocket League build identifiers."""

from __future__ import annotations

import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import rlreplay_rust

FIELDS = (
    "BuildVersion",
    "BuildID",
    "Changelist",
    "GameVersion",
    "ReplayVersion",
    "ReplayLastSaveVersion",
    "RecordFPS",
    "Date",
    "MapName",
)

COMPATIBILITY_NOTE = (
    "RocketSim v2.2.1 / rocketsim_rs 0.37.0: probable standard-physics match; "
    "segment V1 metrics by this bucket"
)


def _replay_paths(roots: list[str]) -> list[Path]:
    paths: list[Path] = []
    for root in roots:
        directory = Path(root)
        if directory.is_dir():
            paths.extend(directory.glob("*.replay"))
    return sorted(paths)


def _header_row(path: Path) -> dict[str, Any]:
    row: dict[str, Any] = {"path": str(path), "source": path.parts[0]}
    for field in FIELDS:
        row[field] = rlreplay_rust.header_property(str(path), field)
    return row


def _bucket_key(row: dict[str, Any]) -> tuple[Any, Any, Any, Any]:
    return (
        row["BuildVersion"],
        row["BuildID"],
        row["Changelist"],
        row["GameVersion"],
    )


def _fmt(value: object) -> str:
    if value is None:
        return "unknown"
    return str(value)


def main() -> int:
    roots = sys.argv[1:] or ["replays", "Replay_files"]
    paths = _replay_paths(roots)
    buckets: dict[tuple[Any, Any, Any, Any], list[dict[str, Any]]] = defaultdict(list)
    errors: list[tuple[str, str]] = []

    for path in paths:
        try:
            row = _header_row(path)
        except Exception as exc:  # noqa: BLE001 - scanner should report all bad files.
            errors.append((str(path), str(exc)))
            continue
        buckets[_bucket_key(row)].append(row)

    ok_count = sum(len(rows) for rows in buckets.values())
    print(
        f"Scanned {len(paths)} replay files: {ok_count} ok, " f"{len(errors)} errors."
    )
    print()
    header = (
        "| BuildVersion | BuildID | Changelist | GameVersion | Count | Sources | "
        "Date span | RecordFPS | Top maps | Compatibility |"
    )
    print(header)
    print("| --- | ---: | ---: | ---: | ---: | --- | --- | --- | --- | --- |")
    for key, rows in sorted(
        buckets.items(),
        key=lambda item: min(_fmt(row["Date"]) for row in item[1]),
    ):
        build_version, build_id, changelist, game_version = key
        dates = sorted(_fmt(row["Date"]) for row in rows if row["Date"] is not None)
        date_span = f"{dates[0]} -> {dates[-1]}" if dates else "unknown"
        fps = ", ".join(
            f"{value} x{count}"
            for value, count in Counter(
                _fmt(row["RecordFPS"]) for row in rows
            ).most_common()
        )
        sources = ", ".join(
            f"{value} x{count}"
            for value, count in Counter(row["source"] for row in rows).most_common()
        )
        maps = ", ".join(
            f"{value} x{count}"
            for value, count in Counter(
                _fmt(row["MapName"]) for row in rows
            ).most_common(3)
        )
        print(
            "| "
            f"{_fmt(build_version)} | {_fmt(build_id)} | "
            f"{_fmt(changelist)} | {_fmt(game_version)} | "
            f"{len(rows)} | {sources} | {date_span} | {fps} | {maps} | "
            f"{COMPATIBILITY_NOTE} |"
        )

    if errors:
        print()
        print("Errors:")
        for path, message in errors:
            print(f"- {path}: {message}")

    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
