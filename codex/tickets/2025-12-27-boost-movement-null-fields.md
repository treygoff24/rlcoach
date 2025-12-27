# Boost/Movement Fields Reported as Null

## Summary
Movement/boost metrics appear as `null` in some consumers because those consumers are querying keys that do not exist in the report schema. The report JSON uses `amount_collected`, `amount_stolen`, and `time_hundred_boost_s`, while the metric catalog (and some expectations) use `boost_collected`, `boost_stolen`, and `time_full_boost_s`. For movement, fields like `distance_km` and `max_speed_kph` are not part of the schema or analyzer output, so any consumer expecting them will see `null`.

## Observed Behavior
- Report consumers that read the JSON and query `boost_collected`, `boost_stolen`, or `time_full_boost_s` get `null`.
- Consumers expecting movement keys like `distance_km`, `max_speed_kph`, or `supersonic_time_s` get `null` because those keys are not emitted.
- The actual report contains valid movement/boost metrics under different key names (`amount_collected`, `amount_stolen`, `time_hundred_boost_s`) and does not emit distance/max-speed fields.

## Expected Behavior
- Report consumers should see populated values for boost/movement metrics without `null` values (except explicitly nullable fields like `third_man_pct`).
- Key names should be consistent across report schema, analysis output, metric catalog, and downstream consumers.

## Root Cause
Key-name mismatch and schema drift:
- Boost analysis + schema use `amount_collected`, `amount_stolen`, `time_hundred_boost_s`.
- Metric catalog uses `boost_collected`, `boost_stolen`, `time_full_boost_s`.
- Movement analyzer/schema do not define `distance_km`, `max_speed_kph`, or `supersonic_time_s`.

Any consumer that relies on the metric catalog (or legacy expectations) to query the report JSON will read non-existent keys and see `null`.

## Evidence
- Report schema defines boost keys as `amount_collected`, `amount_stolen`, `time_hundred_boost_s`:
  - `schemas/replay_report.schema.json`
- Boost analyzer emits `amount_collected`, `amount_stolen`, `time_hundred_boost_s`:
  - `src/rlcoach/analysis/boost.py`
- Metric catalog uses `boost_collected`, `boost_stolen`, `time_full_boost_s`:
  - `src/rlcoach/metrics.py`
- Movement analyzer/schema only define time buckets and `avg_speed_kph`:
  - `src/rlcoach/analysis/movement.py`
  - `schemas/replay_report.schema.json`
- DB writer maps report keys to DB columns, which masks the mismatch for DB-backed API consumers:
  - `src/rlcoach/db/writer.py`

## Repro (Report JSON)
1) Generate a report with `python -m rlcoach.cli analyze replays/<file>.replay --out out`.
2) Inspect JSON:
   - `analysis.per_player[].boost.amount_collected` is populated.
   - `analysis.per_player[].boost.boost_collected` is `null` (key missing).
3) Inspect movement:
   - `analysis.per_player[].movement.avg_speed_kph` populated.
   - `analysis.per_player[].movement.distance_km` is `null` (key missing).

## Impact
- Report consumers querying non-schema keys see `null` values and assume analysis failed.
- Metrics catalog is not aligned with report schema, increasing integration errors.

## Notes
A related drift is documented in `docs/BUG_AUDIT.md`, but the current DB writer already maps the report keys; the mismatch persists for report-JSON consumers and any tooling that expects metric catalog names.
