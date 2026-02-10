#!/usr/bin/env python3
"""Check per-category coverage from pytest-cov JSON output."""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path


def _category_from_path(file_path: str) -> str | None:
    marker = "src/rlcoach/"
    normalized = file_path.replace("\\", "/")
    idx = normalized.find(marker)
    if idx == -1:
        return None
    rel = normalized[idx + len(marker) :]
    if not rel:
        return None
    return rel.split("/", 1)[0].replace(".py", "")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--json",
        default="coverage.json",
        help="Path to coverage JSON produced by pytest-cov",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=50.0,
        help="Minimum required percentage per category",
    )
    args = parser.parse_args()

    path = Path(args.json)
    if not path.exists():
        print(f"Coverage file not found: {path}", file=sys.stderr)
        return 2

    data = json.loads(path.read_text(encoding="utf-8"))
    files = data.get("files", {})

    category_totals: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for filename, details in files.items():
        category = _category_from_path(filename)
        if category is None:
            continue
        summary = details.get("summary", {})
        covered = int(summary.get("covered_lines", 0))
        statements = int(summary.get("num_statements", 0))
        category_totals[category][0] += covered
        category_totals[category][1] += statements

    if not category_totals:
        print("No rlcoach categories found in coverage JSON.", file=sys.stderr)
        return 2

    failures: list[str] = []
    print("Coverage by category:")
    for category in sorted(category_totals):
        covered, total = category_totals[category]
        percent = 100.0 if total == 0 else (covered / total) * 100.0
        print(f"- {category:16s} {percent:6.2f}% ({covered}/{total})")
        if percent < args.threshold:
            failures.append(category)

    if failures:
        print(
            f"\nFailed: {len(failures)} categories below {args.threshold:.1f}%: "
            + ", ".join(failures),
            file=sys.stderr,
        )
        return 1

    print(f"\nAll categories meet threshold >= {args.threshold:.1f}%")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
