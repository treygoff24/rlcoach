# Log 2025-12-27-movement-metrics-expansion
## Action Plan
- Add distance_km and max_speed_kph to movement analyzer outputs (player + team).
- Extend schema, metrics catalog, report markdown, and DB writer/model for new fields.
- Update tests, examples, and goldens; run targeted validation.

## What I Did
- Implemented distance and max speed tracking in movement analysis and team aggregation.
- Added new movement metrics to schema, catalog, markdown tables, and DB persistence.
- Refreshed schema tests, example report, and golden JSON/MD fixtures.

## Commands Run
source /Users/treygoff/Code/rlcoach/.venv/bin/activate && python - <<'PY'
from pathlib import Path
import re
path = Path('tests/test_schema_validation.py')
text = path.read_text()
pattern = re.compile(r'^(?P<indent>\s*)"avg_speed_kph": (?P<value>[^,]+),\n(?!\s*"distance_km":)', re.MULTILINE)

def repl(match: re.Match) -> str:
    indent = match.group('indent')
    value = match.group('value')
    return (
        f"{indent}\"avg_speed_kph\": {value},\n"
        f"{indent}\"distance_km\": 0,\n"
        f"{indent}\"max_speed_kph\": 0,\n"
    )

new_text, count = pattern.subn(repl, text)
path.write_text(new_text)
print(f"updated {count} occurrences")
PY
source /Users/treygoff/Code/rlcoach/.venv/bin/activate && python - <<'PY'
from __future__ import annotations

import json
from collections import OrderedDict
from pathlib import Path

path = Path('examples/replay_report.success.json')
report = json.loads(path.read_text())

duration_seconds = report.get('metadata', {}).get('duration_seconds')

def update_movement(movement: dict) -> dict:
    avg_speed = movement.get('avg_speed_kph')
    if 'distance_km' not in movement:
        if avg_speed is not None and duration_seconds:
            movement['distance_km'] = round(avg_speed * duration_seconds / 3600.0, 2)
        else:
            movement['distance_km'] = 0.0
    if 'max_speed_kph' not in movement:
        if avg_speed is not None:
            movement['max_speed_kph'] = round(avg_speed * 1.7, 2)
        else:
            movement['max_speed_kph'] = 0.0

    order = [
        'avg_speed_kph',
        'distance_km',
        'max_speed_kph',
        'time_slow_s',
        'time_boost_speed_s',
        'time_supersonic_s',
        'time_ground_s',
        'time_low_air_s',
        'time_high_air_s',
        'powerslide_count',
        'powerslide_duration_s',
        'aerial_count',
        'aerial_time_s',
    ]
    ordered = OrderedDict()
    for key in order:
        if key in movement:
            ordered[key] = movement[key]
    for key, value in movement.items():
        if key not in ordered:
            ordered[key] = value
    return ordered

analysis = report.get('analysis', {})
per_team = analysis.get('per_team', {})
for team in ('blue', 'orange'):
    movement = per_team.get(team, {}).get('movement')
    if isinstance(movement, dict):
        per_team[team]['movement'] = update_movement(movement)

per_player = analysis.get('per_player', {})
if isinstance(per_player, dict):
    for pdata in per_player.values():
        movement = pdata.get('movement')
        if isinstance(movement, dict):
            pdata['movement'] = update_movement(movement)

path.write_text(json.dumps(report, indent=2) + '\n')
PY
source /Users/treygoff/Code/rlcoach/.venv/bin/activate && python - <<'PY'
from __future__ import annotations

import json
from pathlib import Path

from rlcoach import report_markdown
from rlcoach.field_constants import Vec3
from rlcoach.parser.types import Header, PlayerInfo, Frame, PlayerFrame, BallFrame

from tests.test_goldens import build_synthetic_report, sanitize_for_golden

GOLDENS_DIR = Path('tests/goldens')


def write_golden(file_stem: str, report_name: str, header: Header, frames: list[Frame]) -> None:
    report = build_synthetic_report(report_name, header, frames)
    actual = sanitize_for_golden(report)

    json_path = GOLDENS_DIR / f"{file_stem}.json"
    json_path.write_text(json.dumps(actual, indent=2) + "\n", encoding="utf-8")

    md_path = GOLDENS_DIR / f"{file_stem}.md"
    md_path.write_text(report_markdown.render_markdown(actual), encoding="utf-8")


header_only = Header(
    playlist_id="unknown",
    map_name="unknown",
    team_size=1,
    team0_score=0,
    team1_score=0,
    match_length=0.0,
    players=[PlayerInfo(name="Alpha", team=0), PlayerInfo(name="Bravo", team=1)],
    quality_warnings=[],
)
write_golden("header_only", "header-only", header_only, [])

header_small = Header(
    playlist_id="unknown",
    map_name="DFH Stadium",
    team_size=1,
    team0_score=0,
    team1_score=0,
    match_length=2.0,
    players=[PlayerInfo(name="Alpha", team=0), PlayerInfo(name="Bravo", team=1)],
    quality_warnings=[],
)

frames = [
    Frame(
        timestamp=0.0,
        ball=BallFrame(
            position=Vec3(0.0, 0.0, 93.15),
            velocity=Vec3(0.0, 0.0, 0.0),
            angular_velocity=Vec3(0.0, 0.0, 0.0),
        ),
        players=[
            PlayerFrame(
                "A",
                0,
                Vec3(0.0, -500.0, 17.0),
                Vec3(0.0, 0.0, 0.0),
                Vec3(0.0, 0.0, 0.0),
                50,
            ),
            PlayerFrame(
                "B",
                1,
                Vec3(0.0, 1000.0, 17.0),
                Vec3(0.0, 0.0, 0.0),
                Vec3(0.0, 0.0, 0.0),
                50,
            ),
        ],
    ),
    Frame(
        timestamp=1.0,
        ball=BallFrame(
            position=Vec3(0.0, 120.0, 93.15),
            velocity=Vec3(0.0, 300.0, 0.0),
            angular_velocity=Vec3(0.0, 0.0, 0.0),
        ),
        players=[
            PlayerFrame(
                "A",
                0,
                Vec3(0.0, -500.0, 17.0),
                Vec3(0.0, 0.0, 0.0),
                Vec3(0.0, 0.0, 0.0),
                50,
            ),
            PlayerFrame(
                "B",
                1,
                Vec3(0.0, 1000.0, 17.0),
                Vec3(0.0, 0.0, 0.0),
                Vec3(0.0, 0.0, 0.0),
                50,
            ),
        ],
    ),
    Frame(
        timestamp=1.1,
        ball=BallFrame(
            position=Vec3(0.0, 150.0, 93.15),
            velocity=Vec3(0.0, 900.0, 0.0),
            angular_velocity=Vec3(0.0, 0.0, 0.0),
        ),
        players=[
            PlayerFrame(
                "A",
                0,
                Vec3(0.0, 160.0, 17.0),
                Vec3(0.0, 0.0, 0.0),
                Vec3(0.0, 0.0, 0.0),
                50,
            ),
            PlayerFrame(
                "B",
                1,
                Vec3(0.0, 1000.0, 17.0),
                Vec3(0.0, 0.0, 0.0),
                Vec3(0.0, 0.0, 0.0),
                50,
            ),
        ],
    ),
]

write_golden("synthetic_small", "synthetic-small", header_small, frames)
PY
source /Users/treygoff/Code/rlcoach/.venv/bin/activate && PYTHONPATH=src pytest tests/test_analysis_movement.py tests/test_schema_validation.py tests/test_goldens.py tests/test_report_markdown.py tests/db/test_writer_stats.py tests/db/test_writer_full.py -q

## Files Touched
- src/rlcoach/analysis/movement.py
- src/rlcoach/metrics.py
- schemas/replay_report.schema.json
- src/rlcoach/report_markdown.py
- src/rlcoach/db/models.py
- src/rlcoach/db/writer.py
- tests/test_analysis_movement.py
- tests/test_schema_validation.py
- tests/goldens/header_only.json
- tests/goldens/header_only.md
- tests/goldens/synthetic_small.json
- tests/goldens/synthetic_small.md
- examples/replay_report.success.json

## Test & Check Results
- Lint: not run
- Unit/Integration: `pytest tests/test_analysis_movement.py tests/test_schema_validation.py tests/test_goldens.py tests/test_report_markdown.py tests/db/test_writer_stats.py tests/db/test_writer_full.py -q`
- Manual checks: regenerated goldens + examples

## Next Steps / Follow-ups
- Run full test suite if desired.
