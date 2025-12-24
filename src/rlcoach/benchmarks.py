# src/rlcoach/benchmarks.py
"""Benchmark data import and validation.

Uses the metric catalog as single source of truth for valid metrics.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from .db.session import create_session
from .db.models import Benchmark
from .metrics import is_valid_metric, VALID_RANKS, VALID_PLAYLISTS


class BenchmarkValidationError(Exception):
    """Benchmark validation error."""
    pass


def validate_benchmark_data(data: dict[str, Any]) -> list[str]:
    """Validate benchmark import data structure.

    Uses metric catalog for validation.

    Returns list of validation errors (empty if valid).
    """
    errors = []

    if "benchmarks" not in data:
        errors.append("Missing 'benchmarks' key")
        return errors

    for i, b in enumerate(data["benchmarks"]):
        prefix = f"benchmarks[{i}]"

        if "metric" not in b:
            errors.append(f"{prefix}: Missing 'metric'")
        elif not is_valid_metric(b["metric"]):
            errors.append(f"{prefix}: Invalid metric '{b['metric']}' (not in metric catalog)")

        if "playlist" not in b:
            errors.append(f"{prefix}: Missing 'playlist'")
        elif b["playlist"] not in VALID_PLAYLISTS:
            errors.append(f"{prefix}: Invalid playlist '{b['playlist']}'")

        if "rank_tier" not in b:
            errors.append(f"{prefix}: Missing 'rank_tier'")
        elif b["rank_tier"] not in VALID_RANKS:
            errors.append(f"{prefix}: Invalid rank_tier '{b['rank_tier']}'")

        if "median" not in b:
            errors.append(f"{prefix}: Missing 'median'")

    return errors


def import_benchmarks(file_path: Path, replace: bool = False) -> int:
    """Import benchmarks from JSON file.

    Args:
        file_path: Path to benchmark JSON file
        replace: If True, delete ALL existing benchmarks before import

    Returns:
        Number of benchmarks imported/updated
    """
    with open(file_path) as f:
        data = json.load(f)

    errors = validate_benchmark_data(data)
    if errors:
        raise BenchmarkValidationError(f"Validation errors:\n" + "\n".join(f"  - {e}" for e in errors))

    metadata = data.get("metadata", {})
    source = metadata.get("source", "unknown")
    source_date_str = metadata.get("collected_date")
    source_date = None
    if source_date_str:
        source_date = date.fromisoformat(source_date_str)
    notes = metadata.get("notes")

    session = create_session()
    try:
        if replace:
            session.query(Benchmark).delete()

        count = 0
        for b in data["benchmarks"]:
            # Check for existing (upsert)
            existing = session.query(Benchmark).filter_by(
                metric=b["metric"],
                playlist=b["playlist"],
                rank_tier=b["rank_tier"],
            ).first()

            if existing:
                existing.median_value = b["median"]
                existing.p25_value = b.get("p25")
                existing.p75_value = b.get("p75")
                existing.elite_threshold = b.get("elite")
                existing.source = source
                existing.source_date = source_date
                existing.notes = b.get("notes") or notes
                existing.imported_at = datetime.now(timezone.utc)
            else:
                benchmark = Benchmark(
                    metric=b["metric"],
                    playlist=b["playlist"],
                    rank_tier=b["rank_tier"],
                    median_value=b["median"],
                    p25_value=b.get("p25"),
                    p75_value=b.get("p75"),
                    elite_threshold=b.get("elite"),
                    source=source,
                    source_date=source_date,
                    notes=b.get("notes") or notes,
                )
                session.add(benchmark)

            count += 1

        session.commit()
        return count

    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
