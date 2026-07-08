#!/usr/bin/env python
"""V1 one-frame resimulation smoke/baseline harness.

Consumes the frozen S1 manifest. Prefer ``--series-dir`` with exported
ReplaySeries JSONs for local/dev-set runs; otherwise replay paths are exported
through the existing parser pipeline. If ``rlinput_py`` is not installed the
script exits 0 with a skipped report unless ``--require-wheel`` is set.
"""

from __future__ import annotations

import argparse
import bisect
import importlib
import json
import math
import statistics
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
GRAVITY_Z = -650.0
THROTTLE_AIR_ACCEL = 200.0 / 3.0
BOOST_ACCEL_AIR = 3175.0 / 3.0
AIR_DT = 1.0 / 120.0
CAR_MAX_SPEED = 2300.0


def main() -> int:
    args = parse_args()
    rlinput_py = optional_import("rlinput_py")
    if rlinput_py is None:
        return finish_skip(args, "rlinput_py wheel is not installed")

    entries = manifest_entries(args.manifest, args.committed_fixtures_only)
    if args.max_replays is not None:
        entries = entries[: args.max_replays]

    records: list[dict[str, Any]] = []
    skipped: list[dict[str, str]] = []
    for entry in entries:
        try:
            series = load_series(entry, args)
            output = rlinput_py.solve_timeline(
                flatten_for_py(series), solver_config(args)
            )
            records.extend(resim_records(entry, series, output))
        except SkipReplay as exc:
            skipped.append({"replay": entry["filename"], "reason": str(exc)})
            if args.require_wheel:
                raise

    report = aggregate_report(args, entries, records, skipped)
    if args.jsonl_dir:
        write_jsonl(args.jsonl_dir, records)
    if args.output_json:
        args.output_json.parent.mkdir(parents=True, exist_ok=True)
        args.output_json.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps(report, indent=2, sort_keys=True))

    if args.smoke and not report["skipped"]:
        assert_smoke(report)
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--manifest", type=Path, default=ROOT / "assets/s1_dev_set.json"
    )
    parser.add_argument("--series-dir", type=Path)
    parser.add_argument("--corpus-dir", type=Path, default=ROOT)
    parser.add_argument("--output-json", type=Path)
    parser.add_argument("--jsonl-dir", type=Path)
    parser.add_argument("--committed-fixtures-only", action="store_true")
    parser.add_argument("--require-wheel", action="store_true")
    parser.add_argument("--smoke", action="store_true")
    parser.add_argument("--max-replays", type=int)
    parser.add_argument(
        "--engine",
        choices=("portable", "reference"),
        default="portable",
        help="Reference falls back inside rlinput_py if the wheel lacks sim support.",
    )
    return parser.parse_args()


def optional_import(name: str) -> Any | None:
    try:
        return importlib.import_module(name)
    except ImportError:
        return None


def finish_skip(args: argparse.Namespace, reason: str) -> int:
    report = {
        "schema_version": 1,
        "generated_at": datetime.now(UTC).isoformat(),
        "status": "skipped",
        "reason": reason,
        "records": 0,
    }
    if args.require_wheel:
        raise SystemExit(reason)
    if args.output_json:
        args.output_json.parent.mkdir(parents=True, exist_ok=True)
        args.output_json.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


def manifest_entries(manifest: Path, committed_only: bool) -> list[dict[str, Any]]:
    data = json.loads(manifest.read_text())
    if "holdout" in data:
        return list(data["holdout"])
    entries = list(data["fixtures"])
    if not committed_only:
        entries.extend(data["seeded_draw"])
    return entries


class SkipReplay(RuntimeError):
    pass


def load_series(entry: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    if args.series_dir:
        path = args.series_dir / f"{Path(entry['filename']).stem}.json"
        if not path.exists():
            raise SkipReplay(f"missing exported series {path}")
        return json.loads(path.read_text())

    replay = args.corpus_dir / entry["filename"]
    if not replay.exists():
        raise SkipReplay(f"missing replay {replay}")
    sys.path.insert(0, str(ROOT / "scripts"))
    try:
        from export_series_json import export_series
    except Exception as exc:  # pragma: no cover - environment dependent
        raise SkipReplay(f"export pipeline unavailable: {exc}") from exc
    try:
        return export_series(replay)
    except Exception as exc:  # pragma: no cover - parser dependent
        raise SkipReplay(f"export failed: {exc}") from exc


def solver_config(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "mode": "unseeded",
        "engine": "reference" if args.engine == "reference" else "portable",
        "withhold": {
            "throttle": True,
            "steer": True,
            "handbrake": True,
            "boost_active": True,
            "boost_amount": True,
            "jump_edges": True,
            "component_events": True,
        },
    }


def flatten_for_py(series: dict[str, Any]) -> dict[str, Any]:
    out = json.loads(json.dumps(series))
    out["ball"]["pos"] = flatten(out["ball"]["pos"])
    out["ball"]["vel"] = flatten(out["ball"]["vel"])
    for player in out["players"]:
        frames = player["frames"]
        for key in ("pos", "vel", "ang_vel"):
            frames[key] = flatten(frames[key])
        frames["quat_xyzw"] = flatten(frames["quat_xyzw"])
        for event in player["component"]["events"]:
            if event.get("vector") is not None:
                event["vector"] = list(event["vector"])
    return out


def flatten(values: list[list[float]]) -> list[float]:
    return [float(item) for row in values for item in row]


def resim_records(
    entry: dict[str, Any], series: dict[str, Any], output: dict[str, Any]
) -> list[dict[str, Any]]:
    players = {player["player_id"]: player for player in series["players"]}
    times = frame_times(series)
    out: list[dict[str, Any]] = []
    for timeline in output["timelines"]:
        player = players.get(timeline["player_id"])
        if player is None:
            continue
        for sample in timeline["samples"]:
            start = start_frame(sample, times)
            end = int(sample["frame_index"])
            if start is None or end <= start:
                continue
            if not contact_free_air(player, start) or not contact_free_air(player, end):
                continue
            ticks = max(1, int(sample["tick_range"][1]) - int(sample["tick_range"][0]))
            solved_controls = {
                "throttle": float(sample["throttle"]["value"]),
                "boost": bool(sample["boost"]["value"]),
            }
            zero_controls = {"throttle": 0.0, "boost": False}
            observed = player["frames"]["pos"][end]
            solved = predict_pos(player, start, ticks, solved_controls)
            zero = predict_pos(player, start, ticks, zero_controls)
            e_solved = distance(solved, observed)
            e_zero = distance(zero, observed)
            if not (math.isfinite(e_solved) and math.isfinite(e_zero)):
                continue
            out.append(
                {
                    "replay": entry["filename"],
                    "build_bucket": entry.get(
                        "build_bucket", series.get("build_bucket")
                    ),
                    "player_id": timeline["player_id"],
                    "start_frame": start,
                    "end_frame": end,
                    "ticks": ticks,
                    "confidence": min(
                        float(sample[name]["confidence"])
                        for name in (
                            "throttle",
                            "steer",
                            "pitch",
                            "yaw",
                            "roll",
                            "boost",
                        )
                    ),
                    "flags": int(sample["throttle"]["flags"]),
                    "e_solved": e_solved,
                    "e_zero": e_zero,
                }
            )
    return out


def frame_times(series: dict[str, Any]) -> list[float]:
    frame_count = max(len(player["frames"]["pos"]) for player in series["players"])
    times = [0.0] * frame_count
    deltas = series["deltas"]
    for idx in range(1, frame_count):
        delta = deltas[idx] if idx < len(deltas) else deltas[idx - 1]
        times[idx] = times[idx - 1] + float(delta)
    return times


def start_frame(sample: dict[str, Any], times: list[float]) -> int | None:
    target = float(sample["time_range"][0])
    end = min(int(sample["frame_index"]), len(times) - 1)
    idx = bisect.bisect_left(times, target, 0, end + 1)
    candidates = [idx]
    if idx > 0:
        candidates.append(idx - 1)
    candidates = [item for item in candidates if 0 <= item <= end]
    if not candidates:
        return None
    return min(candidates, key=lambda item: abs(times[item] - target))


def contact_free_air(player: dict[str, Any], frame: int) -> bool:
    frames = player["frames"]
    if (
        frames["on_ground"][frame]
        or frames["sleeping"][frame]
        or frames["demolished"][frame]
    ):
        return False
    x, y, z = frames["pos"][frame]
    return not (
        z < 40.0
        or z > 2044.0 - 40.0
        or abs(x) > 4096.0 - 40.0
        or abs(y) > 5120.0 - 40.0
        or abs(x) + abs(y) > 8064.0 - 60.0
        or (z < 256.0 and (4096.0 - abs(x) < 256.0 or 5120.0 - abs(y) < 256.0))
    )


def predict_pos(
    player: dict[str, Any], start: int, ticks: int, controls: dict[str, Any]
) -> list[float]:
    frames = player["frames"]
    pos = [float(value) for value in frames["pos"][start]]
    vel = [float(value) for value in frames["vel"][start]]
    forward = quat_forward(frames["quat_xyzw"][start])
    for _ in range(ticks):
        accel = [0.0, 0.0, GRAVITY_Z]
        throttle = float(controls["throttle"])
        if throttle:
            add_scaled(accel, forward, throttle * THROTTLE_AIR_ACCEL)
        if controls["boost"]:
            add_scaled(accel, forward, BOOST_ACCEL_AIR)
        add_scaled(vel, accel, AIR_DT)
        clamp_norm_in_place(vel, CAR_MAX_SPEED)
        add_scaled(pos, vel, AIR_DT)
    return pos


def quat_forward(quat: list[float]) -> list[float]:
    x, y, z, w = [float(value) for value in quat]
    norm = math.sqrt(x * x + y * y + z * z + w * w) or 1.0
    x, y, z, w = x / norm, y / norm, z / norm, w / norm
    return [
        1.0 - 2.0 * (y * y + z * z),
        2.0 * (x * y + z * w),
        2.0 * (x * z - y * w),
    ]


def add_scaled(target: list[float], value: list[float], scale: float) -> None:
    target[0] += value[0] * scale
    target[1] += value[1] * scale
    target[2] += value[2] * scale


def clamp_norm_in_place(value: list[float], max_norm: float) -> None:
    norm = math.sqrt(sum(item * item for item in value))
    if norm > max_norm:
        scale = max_norm / norm
        value[0] *= scale
        value[1] *= scale
        value[2] *= scale


def distance(left: list[float], right: list[float]) -> float:
    return math.sqrt(sum((float(a) - float(b)) ** 2 for a, b in zip(left, right)))


def aggregate_report(
    args: argparse.Namespace,
    entries: list[dict[str, Any]],
    records: list[dict[str, Any]],
    skipped: list[dict[str, str]],
) -> dict[str, Any]:
    report = {
        "schema_version": 1,
        "generated_at": datetime.now(UTC).isoformat(),
        "manifest": str(args.manifest),
        "mode": manifest_mode(args.manifest, args.committed_fixtures_only),
        "requested_replays": len(entries),
        "processed_replays": len({record["replay"] for record in records}),
        "record_count": len(records),
        "skipped": skipped,
        "aggregate": aggregate_records(records),
        "by_replay": {},
        "by_build_bucket": {},
    }
    by_replay: dict[str, list[dict[str, Any]]] = {}
    by_bucket: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        by_replay.setdefault(str(record["replay"]), []).append(record)
        by_bucket.setdefault(str(record["build_bucket"]), []).append(record)
    report["by_replay"] = {
        replay: aggregate_records(replay_records)
        for replay, replay_records in sorted(by_replay.items())
    }
    report["by_build_bucket"] = {
        bucket: aggregate_records(bucket_records)
        for bucket, bucket_records in sorted(by_bucket.items())
    }
    return report


def manifest_mode(manifest: Path, committed_only: bool) -> str:
    data = json.loads(manifest.read_text())
    if "holdout" in data:
        return "holdout_set"
    return "committed_fixtures_only" if committed_only else "dev_set"


def aggregate_records(records: list[dict[str, Any]]) -> dict[str, Any]:
    solved = [record["e_solved"] for record in records]
    zero = [record["e_zero"] for record in records]
    solved_median = median(solved)
    zero_median = median(zero)
    solved_p95 = percentile(solved, 0.95)
    zero_p95 = percentile(zero, 0.95)
    return {
        "segments": len(records),
        "e_solved_median": solved_median,
        "e_zero_median": zero_median,
        "median_ratio_to_zero": ratio(solved_median, zero_median),
        "e_solved_p95": solved_p95,
        "e_zero_p95": zero_p95,
        "p95_ratio_to_zero": ratio(solved_p95, zero_p95),
    }


def median(values: list[float]) -> float | None:
    return statistics.median(values) if values else None


def percentile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    values = sorted(values)
    idx = min(len(values) - 1, max(0, round((len(values) - 1) * q)))
    return values[idx]


def ratio(num: float | None, den: float | None) -> float | None:
    if num is None or den is None or den == 0.0:
        return None
    return num / den


def write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    path.mkdir(parents=True, exist_ok=True)
    by_replay: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        by_replay.setdefault(Path(record["replay"]).stem, []).append(record)
    for replay, replay_records in by_replay.items():
        with (path / f"{replay}.jsonl").open("w") as handle:
            for record in replay_records:
                handle.write(json.dumps(record, sort_keys=True) + "\n")


def assert_smoke(report: dict[str, Any]) -> None:
    aggregate = report["aggregate"]
    if aggregate["segments"] <= 0:
        raise SystemExit("resim_smoke failed: no contact-free air records")
    for key in ("median_ratio_to_zero", "p95_ratio_to_zero"):
        value = aggregate[key]
        if value is None or not math.isfinite(value) or value > 10.0:
            raise SystemExit(f"resim_smoke failed: {key}={value}")


if __name__ == "__main__":
    raise SystemExit(main())
