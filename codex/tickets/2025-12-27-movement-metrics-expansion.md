# Movement Metrics Expansion

## Summary
Add `distance_km` and `max_speed_kph` to the movement analyzer output, schema, and metrics catalog. These are commonly expected metrics that don't currently exist in the system.

## Requested Metrics

| Metric | Description | Unit |
|--------|-------------|------|
| `distance_km` | Total distance traveled during the match | kilometers |
| `max_speed_kph` | Maximum speed reached during the match | km/h |

## Implementation Scope

### 1. Movement Analyzer (`src/rlcoach/analysis/movement.py`)
- Track cumulative distance traveled by summing frame-to-frame position deltas
- Track max speed by keeping the highest speed value seen across all frames
- Convert units: internal UU → kilometers for distance, UU/s → kph for speed
- Add both metrics to player and team output dicts
- Update `_empty_movement()` to include the new keys with 0.0 defaults

### 2. Schema (`schemas/replay_report.schema.json`)
- Add `distance_km` and `max_speed_kph` to the `movement` definition
- Both should be `type: number`

### 3. Metrics Catalog (`src/rlcoach/metrics.py`)
- Add `MetricDefinition` entries for both new metrics
- Category: "movement"
- Include appropriate descriptions and display formatting

### 4. DB Layer (`src/rlcoach/db/`)
- Add columns to `PlayerStats` model if we want to persist these
- Update writer to extract and store the new fields
- Update daily stats aggregation if applicable

### 5. Tests
- Update `tests/test_analysis_movement.py` with test cases for:
  - Distance accumulation across frames
  - Max speed tracking
  - Zero/empty frame handling
- Update golden files if movement output structure changes
- Update schema validation tests

### 6. Report Markdown (`src/rlcoach/report_markdown.py`)
- Add display mappings for the new metrics

## Unit Conversion Reference
From `src/rlcoach/analysis/movement.py`:
```python
def _uu_s_to_kph(uu_per_second: float) -> float:
    """Convert Unreal Units per second to km/h."""
    return uu_per_second * 0.036  # 1 UU/s ≈ 0.036 km/h
```

For distance: 1 UU ≈ 0.01 meters, so divide by 100000 to get km.

## Acceptance Criteria
- [ ] `distance_km` appears in per-player and per-team movement output
- [ ] `max_speed_kph` appears in per-player and per-team movement output
- [ ] Schema validates reports with new fields
- [ ] Metrics catalog includes both metrics with descriptions
- [ ] All existing tests pass
- [ ] New test coverage for the added metrics

## Notes
- Existing movement keys (`avg_speed_kph`, `time_supersonic_s`, etc.) are already consistent across analyzer/catalog/schema - no changes needed there
- This is additive, not a breaking change, so no schema version bump required
