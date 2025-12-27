# Log 2025-12-27 Boost/Movement Null Debug

## Action Plan
- Inspect report JSON, schema, analyzers, and metric catalog for mismatches.
- Validate whether DB fields are actually null after a single replay ingest.
- Write a bug report with root-cause analysis.

## What I Did
- Checked report JSON and found movement/boost values present under schema keys.
- Found naming mismatches between report schema/analyzers and the metric catalog.
- Re-ingested one replay post-DB wipe and verified DB columns are populated.
- Documented diagnosis in a bug report under codex/tickets.

## Commands Run
ls
rg -n "empressolive|empressolive" -S .
rg -n "excluded_names|exclude.*name|exclude.*account|account.*exclude|blacklist|blocklist|skip.*replay|skip.*account" -S src config docs
rg -n "display_names|excluded_names" -S .
rg --files -g "*.toml"
rg --files -g "*config*" -g "*.json" -g "*.yaml" -g "*.yml" -g "*.toml"
sed -n '200,280p' skills/rlcoach/SKILL.md
cat ~/.rlcoach/config.toml
sed -n '1,200p' src/rlcoach/pipeline.py
sed -n '1,200p' src/rlcoach/cli.py
sed -n '340,520p' src/rlcoach/cli.py
sed -n '520,760p' src/rlcoach/cli.py
rg -n "process" -n src/rlcoach/cli.py
rg -n "process_batch|process_replay_file|IngestionStatus" -S .
rg -n "process_batch|batch" -S scripts src tests
rg --files -g "*.replay" replays | head
source /Users/treygoff/Code/rlcoach/.venv/bin/activate && python - <<'PY'
from pathlib import Path
from rlcoach.config import get_default_config_path, load_config
from rlcoach.pipeline import process_replay_file

config_path = get_default_config_path()
config = load_config(config_path)
config.validate()

replay_path = Path("replays/83A1E3D248AED504C9AD4EAA88A490DA.replay")
result = process_replay_file(replay_path, config)
print(result)
print(f"status={result.status}")
print(f"replay_id={result.replay_id}")
print(f"file_hash={result.file_hash}")
PY
source /Users/treygoff/Code/rlcoach/.venv/bin/activate && python - <<'PY'
from pathlib import Path
from rlcoach.config import get_default_config_path, load_config
from rlcoach.pipeline import process_replay_file, IngestionStatus

config = load_config(get_default_config_path())
config.validate()

replay_paths = sorted(Path("replays").glob("*.replay"))

for path in replay_paths:
    result = process_replay_file(path, config)
    print(f"{path.name}: {result.status}")
    if result.status == IngestionStatus.SUCCESS:
        print(f"SUCCESS replay_id={result.replay_id}")
        break
PY
rg --files -g "cf034f13a7c37007d6b04d1c19cb9235e0e1c06af461516e7e85a634cbdc27f9.json" ~/.rlcoach/reports
jq 'keys' /Users/treygoff/.rlcoach/reports/2025-12-27/cf034f13a7c37007d6b04d1c19cb9235e0e1c06af461516e7e85a634cbdc27f9.json
jq '{metadata: .metadata, teams: .teams}' /Users/treygoff/.rlcoach/reports/2025-12-27/cf034f13a7c37007d6b04d1c19cb9235e0e1c06af461516e7e85a634cbdc27f9.json
jq '.players | map({player_id, display_name, platform})' /Users/treygoff/.rlcoach/reports/2025-12-27/cf034f13a7c37007d6b04d1c19cb9235e0e1c06af461516e7e85a634cbdc27f9.json
jq '.analysis.fundamentals.per_player["epic:c47120f06bc1406a9fdc60b3c905be7b"] | {goals, assists, saves, shots, shot_accuracy, demos, demoed}' /Users/treygoff/.rlcoach/reports/2025-12-27/cf034f13a7c37007d6b04d1c19cb9235e0e1c06af461516e7e85a634cbdc27f9.json
jq '.quality' /Users/treygoff/.rlcoach/reports/2025-12-27/cf034f13a7c37007d6b04d1c19cb9235e0e1c06af461516e7e85a634cbdc27f9.json
jq '.analysis.fundamentals.per_team' /Users/treygoff/.rlcoach/reports/2025-12-27/cf034f13a7c37007d6b04d1c19cb9235e0e1c06af461516e7e85a634cbdc27f9.json
jq '.analysis | keys' /Users/treygoff/.rlcoach/reports/2025-12-27/cf034f13a7c37007d6b04d1c19cb9235e0e1c06af461516e7e85a634cbdc27f9.json
jq '.analysis.per_player["epic:c47120f06bc1406a9fdc60b3c905be7b"] | keys' /Users/treygoff/.rlcoach/reports/2025-12-27/cf034f13a7c37007d6b04d1c19cb9235e0e1c06af461516e7e85a634cbdc27f9.json
jq '.analysis.per_player["epic:c47120f06bc1406a9fdc60b3c905be7b"].fundamentals' /Users/treygoff/.rlcoach/reports/2025-12-27/cf034f13a7c37007d6b04d1c19cb9235e0e1c06af461516e7e85a634cbdc27f9.json
jq '.analysis.per_player["epic:c47120f06bc1406a9fdc60b3c905be7b"].movement | {avg_speed_kph, max_speed_kph, distance_km, supersonic_time_s}' /Users/treygoff/.rlcoach/reports/2025-12-27/cf034f13a7c37007d6b04d1c19cb9235e0e1c06af461516e7e85a634cbdc27f9.json
jq '.analysis.per_team | keys' /Users/treygoff/.rlcoach/reports/2025-12-27/cf034f13a7c37007d6b04d1c19cb9235e0e1c06af461516e7e85a634cbdc27f9.json
jq '.analysis.per_team.blue.fundamentals' /Users/treygoff/.rlcoach/reports/2025-12-27/cf034f13a7c37007d6b04d1c19cb9235e0e1c06af461516e7e85a634cbdc27f9.json
jq '.events | length' /Users/treygoff/.rlcoach/reports/2025-12-27/cf034f13a7c37007d6b04d1c19cb9235e0e1c06af461516e7e85a634cbdc27f9.json
jq '.events | map(.event_type) | unique' /Users/treygoff/.rlcoach/reports/2025-12-27/cf034f13a7c37007d6b04d1c19cb9235e0e1c06af461516e7e85a634cbdc27f9.json
jq '.events[0]' /Users/treygoff/.rlcoach/reports/2025-12-27/cf034f13a7c37007d6b04d1c19cb9235e0e1c06af461516e7e85a634cbdc27f9.json
jq '.events | type' /Users/treygoff/.rlcoach/reports/2025-12-27/cf034f13a7c37007d6b04d1c19cb9235e0e1c06af461516e7e85a634cbdc27f9.json
jq '.events | keys' /Users/treygoff/.rlcoach/reports/2025-12-27/cf034f13a7c37007d6b04d1c19cb9235e0e1c06af461516e7e85a634cbdc27f9.json
jq '{goals: (.events.goals|length), touches: (.events.touches|length), boost_pickups: (.events.boost_pickups|length), demos: (.events.demos|length)}' /Users/treygoff/.rlcoach/reports/2025-12-27/cf034f13a7c37007d6b04d1c19cb9235e0e1c06af461516e7e85a634cbdc27f9.json
jq '.analysis.per_player["epic:c47120f06bc1406a9fdc60b3c905be7b"].boost | {avg_boost, boost_collected, big_pads, small_pads, boost_efficiency}' /Users/treygoff/.rlcoach/reports/2025-12-27/cf034f13a7c37007d6b04d1c19cb9235e0e1c06af461516e7e85a634cbdc27f9.json
jq '.analysis.per_player["epic:c47120f06bc1406a9fdc60b3c905be7b"].movement' /Users/treygoff/.rlcoach/reports/2025-12-27/cf034f13a7c37007d6b04d1c19cb9235e0e1c06af461516e7e85a634cbdc27f9.json
jq '.analysis.fundamentals' /Users/treygoff/.rlcoach/reports/2025-12-27/cf034f13a7c37007d6b04d1c19cb9235e0e1c06af461516e7e85a634cbdc27f9.json
rg -n "max_speed_kph|distance_km|boost_collected|boost_efficiency|avg_speed_kph" -S src
sed -n '1,220p' src/rlcoach/analysis/movement.py
sed -n '220,520p' src/rlcoach/analysis/movement.py
rg -n "distance_km|max_speed_kph|supersonic_time_s" -S src
rg -n "movement" -n schemas/replay_report.schema.json
sed -n '380,480p' schemas/replay_report.schema.json
sed -n '1,260p' src/rlcoach/analysis/boost.py
sed -n '240,520p' src/rlcoach/analysis/boost.py
sed -n '520,760p' src/rlcoach/analysis/__init__.py
rg -n "METRIC_CATALOG|boost_collected|boost_stolen|time_full_boost_s|time_hundred_boost_s|shooting_pct" -S src
sed -n '1,260p' src/rlcoach/metrics.py
sed -n '260,520p' src/rlcoach/metrics.py
rg -n "boost_collected|amount_collected|time_full_boost|time_hundred_boost|distance_km|max_speed_kph|supersonic_time" -S gui docs
sed -n '80,140p' docs/BUG_AUDIT.md
sed -n '80,160p' src/rlcoach/db/models.py
sed -n '200,340p' src/rlcoach/db/writer.py
sed -n '1,220p' src/rlcoach/analysis/__init__.py
sed -n '1,260p' src/rlcoach/report.py
rg -n "analysis\.fundamentals|analysis\.boost|analysis\.movement" -S src gui
rg -n "distance_km|max_speed_kph|boost_efficiency|supersonic_time_s" -S src gui docs
jq '[.analysis.per_player[] | {player_id, movement: [.movement[] | select(. == null)] | length, boost: [.boost[] | select(. == null)] | length}]' /Users/treygoff/.rlcoach/reports/2025-12-27/cf034f13a7c37007d6b04d1c19cb9235e0e1c06af461516e7e85a634cbdc27f9.json
rm -f ~/.rlcoach/data/rlcoach.db ~/.rlcoach/data/rlcoach.db-wal ~/.rlcoach/data/rlcoach.db-shm
date +%Y-%m-%d
source /Users/treygoff/Code/rlcoach/.venv/bin/activate && python - <<'PY'
from pathlib import Path
from rlcoach.config import get_default_config_path, load_config
from rlcoach.pipeline import process_replay_file

config = load_config(get_default_config_path())
config.validate()

replay_path = Path("replays/15E5AE4B4D3F73317D488FACC86F4A4D.replay")
result = process_replay_file(replay_path, config)
print(result)
PY
sqlite3 -header -column ~/.rlcoach/data/rlcoach.db "select player_id, avg_speed_kph, time_supersonic_s, boost_collected, boost_stolen, time_full_boost_s, avg_boost, time_zero_boost_s from player_game_stats limit 4;"

## Files Touched
- codex/tickets/2025-12-27-boost-movement-null-fields.md
- codex/logs/2025-12-27-boost-movement-null-debug.md

## Test & Check Results
- Lint: not run
- Unit/Integration: not run
- Manual checks: inspected report JSON, schema, analyzers, and DB query

## Next Steps / Follow-ups
- Align metric key names across schema, analysis outputs, metric catalog, and report consumers.
- Decide whether to add missing movement metrics (distance/max speed) or remove expectations.
