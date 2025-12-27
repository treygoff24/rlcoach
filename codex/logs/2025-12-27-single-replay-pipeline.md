# Log 2025-12-27-single-replay-pipeline
## Action Plan
- Run pipeline on one replay.
- Inspect report + DB output for anomalies.
- Record findings.

## What I Did
- Ran process_replay_file on one replay in `replays/`.
- Reviewed report JSON (metadata, events, analysis nulls) and DB row counts.

## Commands Run
rg -n "report-md|pipeline|ingest|process" src/rlcoach/cli.py src/rlcoach/pipeline.py README.md -S
ls -la replays
source .venv/bin/activate && python - <<'PY'
from pathlib import Path
from rlcoach.config import load_config, get_default_config_path
from rlcoach.pipeline import process_replay_file

config = load_config(get_default_config_path())
config.validate()
replay_path = Path("replays/2530D230422CCE1CA847DD8B412B1144.replay")
result = process_replay_file(replay_path, config)
print(result)
print({"status": result.status.value, "replay_id": result.replay_id, "file_hash": result.file_hash, "error": result.error})
PY
rg -a -l "EmpressOlive" replays/*.replay
rg -a -l "Pinochetwasright" replays/*.replay
source .venv/bin/activate && python - <<'PY'
from pathlib import Path
from rlcoach.config import load_config, get_default_config_path
from rlcoach.pipeline import process_replay_file

config = load_config(get_default_config_path())
config.validate()
replay_path = Path("replays/09F94D67433B9C5E066F1CB67D084086.replay")
result = process_replay_file(replay_path, config)
print(result)
print({"status": result.status.value, "replay_id": result.replay_id, "file_hash": result.file_hash, "error": result.error})
PY
rg --files ~/.rlcoach/reports
jq '{replay_id, metadata: {playlist, arena, duration_s, started_at_utc, ended_at_utc, score_blue, score_orange, overtime}, quality}' /Users/treygoff/.rlcoach/reports/2025-12-27/e45a4626b1551cbc3a17ee9756b23316cb7bfb86de3304734c6e11da35b466ce.json
jq '.metadata' /Users/treygoff/.rlcoach/reports/2025-12-27/e45a4626b1551cbc3a17ee9756b23316cb7bfb86de3304734c6e11da35b466ce.json
jq '{players: (.players | length), teams: (.teams | keys)}' /Users/treygoff/.rlcoach/reports/2025-12-27/e45a4626b1551cbc3a17ee9756b23316cb7bfb86de3304734c6e11da35b466ce.json
jq '.analysis.per_player | to_entries | map({player_id: .key, movement_nulls: ([.value.movement | to_entries[] | select(.value==null)] | length), boost_nulls: ([.value.boost | to_entries[] | select(.value==null)] | length)})' /Users/treygoff/.rlcoach/reports/2025-12-27/e45a4626b1551cbc3a17ee9756b23316cb7bfb86de3304734c6e11da35b466ce.json
jq 'has("error")' /Users/treygoff/.rlcoach/reports/2025-12-27/e45a4626b1551cbc3a17ee9756b23316cb7bfb86de3304734c6e11da35b466ce.json
jq '.events | type' /Users/treygoff/.rlcoach/reports/2025-12-27/e45a4626b1551cbc3a17ee9756b23316cb7bfb86de3304734c6e11da35b466ce.json
jq '.events | to_entries | map({event: .key, count: (.value | length)})' /Users/treygoff/.rlcoach/reports/2025-12-27/e45a4626b1551cbc3a17ee9756b23316cb7bfb86de3304734c6e11da35b466ce.json
jq '.analysis | keys' /Users/treygoff/.rlcoach/reports/2025-12-27/e45a4626b1551cbc3a17ee9756b23316cb7bfb86de3304734c6e11da35b466ce.json
jq '.analysis.per_player | to_entries[0].value | keys' /Users/treygoff/.rlcoach/reports/2025-12-27/e45a4626b1551cbc3a17ee9756b23316cb7bfb86de3304734c6e11da35b466ce.json
jq '[.players[] | {player_id, is_me}]' /Users/treygoff/.rlcoach/reports/2025-12-27/e45a4626b1551cbc3a17ee9756b23316cb7bfb86de3304734c6e11da35b466ce.json
jq '.analysis.per_player | to_entries | map({player_id: .key, goals: .value.fundamentals.goals, shots: .value.fundamentals.shots, saves: .value.fundamentals.saves, assists: .value.fundamentals.assists})' /Users/treygoff/.rlcoach/reports/2025-12-27/e45a4626b1551cbc3a17ee9756b23316cb7bfb86de3304734c6e11da35b466ce.json
jq '.teams' /Users/treygoff/.rlcoach/reports/2025-12-27/e45a4626b1551cbc3a17ee9756b23316cb7bfb86de3304734c6e11da35b466ce.json
jq '.source_file' /Users/treygoff/.rlcoach/reports/2025-12-27/e45a4626b1551cbc3a17ee9756b23316cb7bfb86de3304734c6e11da35b466ce.json
sqlite3 ~/.rlcoach/data/rlcoach.db "select 'replays' as table_name, count(*) from replays union all select 'players', count(*) from players union all select 'player_game_stats', count(*) from player_game_stats union all select 'daily_stats', count(*) from daily_stats;"
sqlite3 ~/.rlcoach/data/rlcoach.db "select player_id, display_name, is_me from players;"

## Files Touched
- codex/logs/2025-12-27-single-replay-pipeline.md

## Test & Check Results
- Lint: not run (not requested)
- Unit/Integration: not run (not requested)
- Manual checks: report JSON + DB row counts

## Next Steps / Follow-ups
- None
