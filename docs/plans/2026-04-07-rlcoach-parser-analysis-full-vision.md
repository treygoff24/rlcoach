# RLCoach Parser And Analysis Full Vision Implementation Plan

**Goal:** Take RLCoach from its current state to the full intended parser, normalization, events, analysis, reporting, and verification vision so the system is authoritative where possible, exhaustive where needed, and reliably tested on both synthetic and real replay corpora.

**Architecture:** Keep the current Rust `boxcars` plus Python adapter pipeline, but evolve it from a reliable frame-telemetry bridge into a richer parser contract with explicit authoritative metadata and event streams, then make normalization, events, mechanics, reports, and corpus health consume that contract end-to-end. Preserve the existing diagnostics-first posture: every degraded path must stay machine-readable, every authoritative-vs-derived decision must be explicit, and every new capability must land with both targeted tests and corpus-level verification.

**Tech Stack:** Rust (`boxcars`, `pyo3`), Python (`pytest`, dataclasses, jsonschema), existing RLCoach parser/normalize/events/analysis/report stack.

---

## Current-State Summary

- The Rust parser already emits useful frame telemetry: ball state, player kinematics, boost amount, on-ground/demolished booleans, parser meta, and boost pad events.
- The parser diagnostics contract is already strong: `parse_network_with_diagnostics`, degraded/unavailable states, attempted backends, parser scorecard, and debug harnesses are live.
- The downstream Python analysis stack is ahead of the Rust parser in ambition: advanced mechanics detection already exists for most of the planned mechanic set.
- The main gaps are:
  - incomplete parser header metadata coverage,
  - incomplete authoritative component-state semantics,
  - no first-class parser-native touch/demo/tickmark streams in the normal output contract,
  - incomplete rollup/report parity for all advanced mechanics,
  - insufficient real-replay and corpus-level verification for the full advanced surface.

## End-State Acceptance Criteria

The work in this plan is complete only when all of the following are true:

1. The Rust parser emits a stable typed contract for:
   - complete header metadata needed by the report contract,
   - authoritative frame state for ball and players,
   - authoritative component-state flags with clear `True` / `False` / `None` semantics,
   - parser-native event streams wherever replay data supports them directly,
   - machine-readable diagnostics and provenance for both success and degraded paths.
2. Normalization preserves the full parser contract without silently dropping authoritative data.
3. Event detectors prefer parser-native event streams when present and fall back to derived heuristics only when required.
4. Mechanics analysis reaches the full planned scope, including rollups and report parity for every implemented mechanic.
5. Report JSON schema, markdown, and scorecard quality surfaces accurately reflect the richer parser and analysis contract.
6. Targeted tests, end-to-end replay tests, and corpus health/performance gates all pass using the project venv.

---

### Task 1: Freeze The End-State Acceptance Corpus And Gate Surface

**Parallel:** no  
**Blocked by:** none  
**Owned files:** `tests/parser/test_rust_adapter_smoke.py`, `tests/test_report_end_to_end.py`, `tests/test_benchmarks.py`, `tests/test_cli_benchmarks.py`, `scripts/parser_corpus_health.py`  
**Invariants:** Keep existing smoke coverage green while broadening acceptance checks; do not weaken current diagnostics expectations.  
**Out of scope:** Parser implementation changes beyond minimal fixture plumbing needed to express the failing gates.

**Files:**
- Modify: `tests/parser/test_rust_adapter_smoke.py`
- Modify: `tests/test_report_end_to_end.py`
- Modify: `tests/test_benchmarks.py`
- Modify: `tests/test_cli_benchmarks.py`
- Modify: `scripts/parser_corpus_health.py`

**Step 1: Write the failing test**
```python
def test_real_replay_report_meets_full_parser_contract():
    report = generate_report(Path("testing_replay.replay"), adapter_name="rust")
    parser = report["quality"]["parser"]
    assert parser["network_diagnostics"]["status"] == "ok"
    assert parser["scorecard"]["usable_network_parse"] is True
    assert report["metadata"]["recorded_frame_hz"] >= 20.0
    assert report["events"]["timeline"]
```

**Step 2: Run test to verify it fails**  
Run: `source .venv/bin/activate && PYTHONPATH=src pytest tests/test_report_end_to_end.py::test_real_replay_report_meets_full_parser_contract -q`  
Expected: FAIL on one or more missing full-contract expectations.

**Step 3: Write minimal implementation**
```python
# tests/test_benchmarks.py
def test_parser_corpus_health_full_contract_fields(tmp_path):
    result = run_parser_corpus_health_json(tmp_path)
    assert "network_success_rate" in result
    assert "top_error_codes" in result
    assert "playlist_buckets" in result
```

**Step 4: Run test to verify it passes**  
Run: `source .venv/bin/activate && PYTHONPATH=src pytest tests/parser/test_rust_adapter_smoke.py tests/test_report_end_to_end.py tests/test_benchmarks.py tests/test_cli_benchmarks.py -q`  
Expected: PASS for the new gate definitions.

**Verification plan:**
- Primary command: `source .venv/bin/activate && PYTHONPATH=src pytest tests/parser/test_rust_adapter_smoke.py tests/test_report_end_to_end.py tests/test_benchmarks.py tests/test_cli_benchmarks.py -q`
- Secondary checks: `source .venv/bin/activate && PYTHONPATH=src python scripts/parser_corpus_health.py --roots replays,Replay_files --json`

---

### Task 2: Lock The Full Parser Contract In Types, Schema, And Report Plumbing

**Parallel:** no  
**Blocked by:** Task 1  
**Owned files:** `src/rlcoach/parser/types.py`, `schemas/replay_report.schema.json`, `src/rlcoach/report.py`, `tests/test_parser_interface.py`, `tests/test_schema_validation.py`, `tests/test_schema_validation_hardening.py`  
**Invariants:** Preserve backward compatibility for currently valid reports; all new parser/event fields must be optional or degradable until producing code lands.  
**Out of scope:** Rust extraction details.

**Files:**
- Modify: `src/rlcoach/parser/types.py`
- Modify: `schemas/replay_report.schema.json`
- Modify: `src/rlcoach/report.py`
- Modify: `tests/test_parser_interface.py`
- Modify: `tests/test_schema_validation.py`
- Modify: `tests/test_schema_validation_hardening.py`

**Step 1: Write the failing test**
```python
def test_network_frames_supports_authoritative_event_streams():
    fields = getattr(NetworkFrames, "__dataclass_fields__", {})
    assert "touch_events" in fields
    assert "demo_events" in fields
    assert "tickmarks" in fields
```

**Step 2: Run test to verify it fails**  
Run: `source .venv/bin/activate && PYTHONPATH=src pytest tests/test_parser_interface.py::test_network_frames_supports_authoritative_event_streams -q`  
Expected: FAIL because the dataclass fields do not exist yet.

**Step 3: Write minimal implementation**
```python
@dataclass(frozen=True)
class NetworkFrames:
    frame_count: int = 0
    sample_rate: float = 30.0
    frames: list = field(default_factory=list)
    touch_events: list = field(default_factory=list)
    demo_events: list = field(default_factory=list)
    tickmarks: list = field(default_factory=list)
    diagnostics: NetworkDiagnostics | None = None
```

**Step 4: Run test to verify it passes**  
Run: `source .venv/bin/activate && PYTHONPATH=src pytest tests/test_parser_interface.py::test_network_frames_supports_authoritative_event_streams tests/test_schema_validation.py tests/test_schema_validation_hardening.py -q`  
Expected: PASS with schema updated to accept the richer parser/report contract.

**Verification plan:**
- Primary command: `source .venv/bin/activate && PYTHONPATH=src pytest tests/test_parser_interface.py tests/test_schema_validation.py tests/test_schema_validation_hardening.py -q`
- Secondary checks: `source .venv/bin/activate && PYTHONPATH=src pytest tests/test_report_end_to_end.py::test_real_replay_report_meets_full_parser_contract -q`

---

### Task 3: Complete Rust Header Metadata Extraction

**Parallel:** no  
**Blocked by:** Task 2  
**Owned files:** `parsers/rlreplay_rust/src/lib.rs`, `src/rlcoach/parser/rust_adapter.py`, `tests/test_rust_adapter.py`, `tests/test_report_metadata.py`  
**Invariants:** Keep current header parse success rate and existing player/goals/highlights extraction intact.  
**Out of scope:** Network frame parsing.

**Files:**
- Modify: `parsers/rlreplay_rust/src/lib.rs`
- Modify: `src/rlcoach/parser/rust_adapter.py`
- Modify: `tests/test_rust_adapter.py`
- Modify: `tests/test_report_metadata.py`

**Step 1: Write the failing test**
```python
def test_rust_header_maps_match_guid_overtime_and_mutators():
    adapter = get_adapter("rust")
    header = adapter.parse_header(Path("testing_replay.replay"))
    assert header.match_guid is not None
    assert header.overtime is not None
    assert isinstance(header.mutators, dict)
```

**Step 2: Run test to verify it fails**  
Run: `source .venv/bin/activate && PYTHONPATH=src pytest tests/test_rust_adapter.py::test_rust_header_maps_match_guid_overtime_and_mutators -q`  
Expected: FAIL on one or more missing metadata fields.

**Step 3: Write minimal implementation**
```rust
if let Some(p) = find_prop(&properties, "MatchGUID").and_then(|p| p.as_string()) {
    header.set_item("match_guid", p)?;
}
if let Some(p) = find_prop(&properties, "bOverTime").and_then(|p| p.as_bool()) {
    header.set_item("overtime", p)?;
}
header.set_item("mutators", extract_mutators(&properties, py)?)?;
```

**Step 4: Run test to verify it passes**  
Run: `source .venv/bin/activate && PYTHONPATH=src pytest tests/test_rust_adapter.py tests/test_report_metadata.py -q`  
Expected: PASS with report metadata now fully sourced from Rust header data when available.

**Verification plan:**
- Primary command: `source .venv/bin/activate && PYTHONPATH=src pytest tests/test_rust_adapter.py tests/test_report_metadata.py -q`
- Secondary checks: `source .venv/bin/activate && PYTHONPATH=src python -m rlcoach.cli analyze testing_replay.replay --adapter rust --out /tmp/rlcoach-full-header`

---

### Task 4: Make Authoritative Component-State Semantics Explicit And Durable

**Parallel:** no  
**Blocked by:** Task 2  
**Owned files:** `parsers/rlreplay_rust/src/lib.rs`, `src/rlcoach/normalize.py`, `tests/test_normalize.py`, `tests/parser/test_rust_adapter_smoke.py`, `tests/test_analysis_new_modules.py`  
**Invariants:** Keep mechanics preferring authority when present; never silently collapse explicit `False` to “missing.”  
**Out of scope:** New event streams.

**Files:**
- Modify: `parsers/rlreplay_rust/src/lib.rs`
- Modify: `src/rlcoach/normalize.py`
- Modify: `tests/test_normalize.py`
- Modify: `tests/parser/test_rust_adapter_smoke.py`
- Modify: `tests/test_analysis_new_modules.py`

**Step 1: Write the failing test**
```python
def test_normalize_preserves_explicit_false_component_flags():
    raw = [{
        "timestamp": 0.0,
        "ball": {"position": {"x": 0, "y": 0, "z": 93.15}, "velocity": {"x": 0, "y": 0, "z": 0}, "angular_velocity": {"x": 0, "y": 0, "z": 0}},
        "players": [{
            "player_id": "player_0",
            "team": 0,
            "position": {"x": 0, "y": 0, "z": 17},
            "velocity": {"x": 0, "y": 0, "z": 0},
            "rotation": {"pitch": 0, "yaw": 0, "roll": 0},
            "boost_amount": 33,
            "is_jumping": False,
            "is_dodging": False,
            "is_double_jumping": False,
        }],
    }]
    frames = build_timeline(Header(players=[]), raw)
    assert frames[0].players[0].is_jumping is False
```

**Step 2: Run test to verify it fails**  
Run: `source .venv/bin/activate && PYTHONPATH=src pytest tests/test_normalize.py::test_normalize_preserves_explicit_false_component_flags -q`  
Expected: FAIL because the full explicit-false path is not enforced yet.

**Step 3: Write minimal implementation**
```rust
if component_observed {
    p.set_item("is_jumping", observed_jump_bool)?;
} else {
    p.set_item("is_jumping", py.None())?;
}
```

**Step 4: Run test to verify it passes**  
Run: `source .venv/bin/activate && PYTHONPATH=src pytest tests/test_normalize.py tests/test_analysis_new_modules.py::test_authoritative_component_flags_drive_mechanics_detection -q`  
Expected: PASS, with mechanics preserving parser authority for both positive and negative states.

**Verification plan:**
- Primary command: `source .venv/bin/activate && PYTHONPATH=src pytest tests/test_normalize.py tests/test_analysis_new_modules.py -q`
- Secondary checks: `source .venv/bin/activate && PYTHONPATH=src pytest tests/parser/test_rust_adapter_smoke.py -q`

---

### Task 5: Add Parser-Native Touch Stream And Tickmark/Kickoff Metadata

**Parallel:** no  
**Blocked by:** Tasks 2, 4  
**Owned files:** `parsers/rlreplay_rust/src/lib.rs`, `src/rlcoach/parser/types.py`, `src/rlcoach/parser/rust_adapter.py`, `src/rlcoach/normalize.py`, `src/rlcoach/events/touches.py`, `src/rlcoach/events/kickoffs.py`, `tests/test_events.py`, `tests/test_events_calibration_synthetic.py`, `tests/test_parser_interface.py`  
**Invariants:** Keep derived touch detection as fallback until parser-native touch events are proven reliable.  
**Out of scope:** Demo event extraction.

**Files:**
- Modify: `parsers/rlreplay_rust/src/lib.rs`
- Modify: `src/rlcoach/parser/types.py`
- Modify: `src/rlcoach/parser/rust_adapter.py`
- Modify: `src/rlcoach/normalize.py`
- Modify: `src/rlcoach/events/touches.py`
- Modify: `src/rlcoach/events/kickoffs.py`
- Modify: `tests/test_events.py`
- Modify: `tests/test_events_calibration_synthetic.py`
- Modify: `tests/test_parser_interface.py`

**Step 1: Write the failing test**
```python
def test_detect_touches_prefers_parser_native_touch_events():
    frames, touch_events = make_network_frames_with_touch_stream()
    detected = detect_touches(frames, parser_touch_events=touch_events)
    assert detected[0].player_id == "player_0"
    assert detected[0].frame == 0
```

**Step 2: Run test to verify it fails**  
Run: `source .venv/bin/activate && PYTHONPATH=src pytest tests/test_events.py::test_detect_touches_prefers_parser_native_touch_events -q`  
Expected: FAIL because parser-native touch streams are not threaded through yet.

**Step 3: Write minimal implementation**
```python
def detect_touches(frames: list[Frame], parser_touch_events: list[Any] | None = None):
    if parser_touch_events:
        return _normalize_parser_touch_events(parser_touch_events)
    return _detect_touches_derived(frames)
```

**Step 4: Run test to verify it passes**  
Run: `source .venv/bin/activate && PYTHONPATH=src pytest tests/test_events.py tests/test_events_calibration_synthetic.py tests/test_parser_interface.py -q`  
Expected: PASS with parser-native touches and kickoff metadata preferred when present.

**Verification plan:**
- Primary command: `source .venv/bin/activate && PYTHONPATH=src pytest tests/test_events.py tests/test_events_calibration_synthetic.py tests/test_parser_interface.py -q`
- Secondary checks: `source .venv/bin/activate && PYTHONPATH=src python -m rlcoach.cli analyze testing_replay.replay --adapter rust --out /tmp/rlcoach-touch-stream`

---

### Task 6: Add Parser-Native Demolish/Explosion Stream

**Parallel:** no  
**Blocked by:** Tasks 2, 4  
**Owned files:** `parsers/rlreplay_rust/src/lib.rs`, `src/rlcoach/parser/types.py`, `src/rlcoach/normalize.py`, `src/rlcoach/events/demos.py`, `tests/test_events.py`, `tests/test_report_end_to_end.py`  
**Invariants:** Keep current state-transition-based demo inference as fallback until parser-native demo events are proven reliable.  
**Out of scope:** Touches and mechanics.

**Files:**
- Modify: `parsers/rlreplay_rust/src/lib.rs`
- Modify: `src/rlcoach/parser/types.py`
- Modify: `src/rlcoach/normalize.py`
- Modify: `src/rlcoach/events/demos.py`
- Modify: `tests/test_events.py`
- Modify: `tests/test_report_end_to_end.py`

**Step 1: Write the failing test**
```python
def test_detect_demos_prefers_parser_native_demo_events():
    frames, demo_events = make_network_frames_with_demo_stream()
    demos = detect_demos(frames, parser_demo_events=demo_events)
    assert demos[0].attacker == "player_1"
    assert demos[0].victim == "player_0"
```

**Step 2: Run test to verify it fails**  
Run: `source .venv/bin/activate && PYTHONPATH=src pytest tests/test_events.py::test_detect_demos_prefers_parser_native_demo_events -q`  
Expected: FAIL because parser-native demo streams are not supported yet.

**Step 3: Write minimal implementation**
```python
def detect_demos(frames: list[Frame], parser_demo_events: list[Any] | None = None):
    if parser_demo_events:
        return _normalize_parser_demo_events(parser_demo_events)
    return _detect_demo_state_transitions(frames)
```

**Step 4: Run test to verify it passes**  
Run: `source .venv/bin/activate && PYTHONPATH=src pytest tests/test_events.py tests/test_report_end_to_end.py -q`  
Expected: PASS with parser-native demo events preferred and fallback retained.

**Verification plan:**
- Primary command: `source .venv/bin/activate && PYTHONPATH=src pytest tests/test_events.py tests/test_report_end_to_end.py -q`
- Secondary checks: `source .venv/bin/activate && PYTHONPATH=src python -m rlcoach.cli analyze testing_replay.replay --adapter rust --out /tmp/rlcoach-demo-stream`

---

### Task 7: Normalize And Report The Expanded Parser Contract End-To-End

**Parallel:** no  
**Blocked by:** Tasks 3, 4, 5, 6  
**Owned files:** `src/rlcoach/normalize.py`, `src/rlcoach/report.py`, `tests/test_report_end_to_end.py`, `tests/test_report_metadata.py`, `tests/test_schema_validation.py`  
**Invariants:** Report generation must stay successful on header-only and degraded parses.  
**Out of scope:** Mechanics algorithm changes.

**Files:**
- Modify: `src/rlcoach/normalize.py`
- Modify: `src/rlcoach/report.py`
- Modify: `tests/test_report_end_to_end.py`
- Modify: `tests/test_report_metadata.py`
- Modify: `tests/test_schema_validation.py`

**Step 1: Write the failing test**
```python
def test_generate_report_threads_parser_native_streams_into_events_and_quality():
    report = generate_report(Path("testing_replay.replay"), adapter_name="rust")
    assert "network_diagnostics" in report["quality"]["parser"]
    assert "scorecard" in report["quality"]["parser"]
    assert report["events"]["touches"] or report["events"]["demos"]
```

**Step 2: Run test to verify it fails**  
Run: `source .venv/bin/activate && PYTHONPATH=src pytest tests/test_report_end_to_end.py::test_generate_report_threads_parser_native_streams_into_events_and_quality -q`  
Expected: FAIL until the richer parser contract is carried through end-to-end.

**Step 3: Write minimal implementation**
```python
events_dict = {
    "goals": goals,
    "demos": detect_demos(normalized_frames, parser_demo_events=raw_demo_events),
    "kickoffs": detect_kickoffs(normalized_frames, header, parser_tickmarks=raw_tickmarks),
    "boost_pickups": pickups,
    "touches": detect_touches(normalized_frames, parser_touch_events=raw_touch_events),
    "challenges": challenges,
}
```

**Step 4: Run test to verify it passes**  
Run: `source .venv/bin/activate && PYTHONPATH=src pytest tests/test_report_end_to_end.py tests/test_report_metadata.py tests/test_schema_validation.py -q`  
Expected: PASS with the richer parser contract flowing into report JSON.

**Verification plan:**
- Primary command: `source .venv/bin/activate && PYTHONPATH=src pytest tests/test_report_end_to_end.py tests/test_report_metadata.py tests/test_schema_validation.py -q`
- Secondary checks: `source .venv/bin/activate && PYTHONPATH=src python -m rlcoach.cli report-md testing_replay.replay --out /tmp/rlcoach-report-md --pretty`

---

### Task 8: Close Mechanics Full-Vision Parity And Rollup Gaps

**Parallel:** no  
**Blocked by:** Tasks 4, 5, 7  
**Owned files:** `src/rlcoach/analysis/mechanics.py`, `src/rlcoach/analysis/__init__.py`, `schemas/replay_report.schema.json`, `tests/test_analysis_new_modules.py`, `tests/test_report_end_to_end.py`  
**Invariants:** Keep currently passing mechanics coverage intact while adding missing rollups and parser-authority preference.  
**Out of scope:** Non-mechanics analysis modules.

**Files:**
- Modify: `src/rlcoach/analysis/mechanics.py`
- Modify: `src/rlcoach/analysis/__init__.py`
- Modify: `schemas/replay_report.schema.json`
- Modify: `tests/test_analysis_new_modules.py`
- Modify: `tests/test_report_end_to_end.py`

**Step 1: Write the failing test**
```python
def test_mechanics_rollup_includes_skim_and_psycho_counts():
    result = analyze_mechanics(make_psycho_and_skim_fixture())
    player = result["per_player"]["player_0"]
    assert player["skim_count"] >= 1
    assert player["psycho_count"] >= 1
```

**Step 2: Run test to verify it fails**  
Run: `source .venv/bin/activate && PYTHONPATH=src pytest tests/test_analysis_new_modules.py::test_mechanics_rollup_includes_skim_and_psycho_counts -q`  
Expected: FAIL because rollups do not currently expose those counts.

**Step 3: Write minimal implementation**
```python
per_player[player_id]["skim_count"] = counts.get("skim", 0)
per_player[player_id]["psycho_count"] = counts.get("psycho", 0)
```

**Step 4: Run test to verify it passes**  
Run: `source .venv/bin/activate && PYTHONPATH=src pytest tests/test_analysis_new_modules.py tests/test_report_end_to_end.py -q`  
Expected: PASS with all implemented advanced mechanics represented in the report surface.

**Verification plan:**
- Primary command: `source .venv/bin/activate && PYTHONPATH=src pytest tests/test_analysis_new_modules.py tests/test_report_end_to_end.py -q`
- Secondary checks: `source .venv/bin/activate && PYTHONPATH=src pytest tests/test_analysis_kickoffs.py tests/test_analysis_passing.py tests/test_analysis_positioning.py -q`

---

### Task 9: Close Remaining Analysis Parity Across All Modules

**Parallel:** no  
**Blocked by:** Tasks 5, 6, 7, 8  
**Owned files:** `src/rlcoach/analysis/fundamentals.py`, `src/rlcoach/analysis/boost.py`, `src/rlcoach/analysis/movement.py`, `src/rlcoach/analysis/positioning.py`, `src/rlcoach/analysis/passing.py`, `src/rlcoach/analysis/challenges.py`, `src/rlcoach/analysis/kickoffs.py`, `src/rlcoach/analysis/defense.py`, `src/rlcoach/analysis/recovery.py`, `src/rlcoach/analysis/xg.py`, `src/rlcoach/analysis/ball_prediction.py`, `src/rlcoach/analysis/insights.py`, `src/rlcoach/analysis/weaknesses.py`, `tests/test_analysis_fundamentals.py`, `tests/test_analysis_boost.py`, `tests/test_analysis_movement.py`, `tests/test_analysis_positioning.py`, `tests/test_analysis_passing.py`, `tests/test_analysis_challenges.py`, `tests/test_analysis_kickoffs.py`, `tests/analysis/test_patterns.py`, `tests/analysis/test_tendencies.py`, `tests/analysis/test_weaknesses.py`  
**Invariants:** Keep module boundaries and aggregator caching pattern in place.  
**Out of scope:** Parser implementation details.

**Files:**
- Modify: `src/rlcoach/analysis/fundamentals.py`
- Modify: `src/rlcoach/analysis/boost.py`
- Modify: `src/rlcoach/analysis/movement.py`
- Modify: `src/rlcoach/analysis/positioning.py`
- Modify: `src/rlcoach/analysis/passing.py`
- Modify: `src/rlcoach/analysis/challenges.py`
- Modify: `src/rlcoach/analysis/kickoffs.py`
- Modify: `src/rlcoach/analysis/defense.py`
- Modify: `src/rlcoach/analysis/recovery.py`
- Modify: `src/rlcoach/analysis/xg.py`
- Modify: `src/rlcoach/analysis/ball_prediction.py`
- Modify: `src/rlcoach/analysis/insights.py`
- Modify: `src/rlcoach/analysis/weaknesses.py`
- Modify: the matching tests listed above

**Step 1: Write the failing test**
```python
def test_full_analysis_stack_returns_non_empty_player_blocks_for_real_replay():
    report = generate_report(Path("testing_replay.replay"), adapter_name="rust")
    player_blocks = report["analysis"]["per_player"]
    assert player_blocks
    for player_id, block in player_blocks.items():
        assert "mechanics" in block
        assert "boost" in block
        assert "positioning" in block
```

**Step 2: Run test to verify it fails**  
Run: `source .venv/bin/activate && PYTHONPATH=src pytest tests/test_report_end_to_end.py::test_full_analysis_stack_returns_non_empty_player_blocks_for_real_replay -q`  
Expected: FAIL on one or more incomplete module contracts.

**Step 3: Write minimal implementation**
```python
return {
    "fundamentals": fundamentals,
    "boost": boost,
    "movement": movement,
    "positioning": positioning,
    "passing": passing,
    "challenges": challenges,
    "kickoffs": kickoffs,
    "defense": defense,
    "mechanics": mechanics,
}
```

**Step 4: Run test to verify it passes**  
Run: `source .venv/bin/activate && PYTHONPATH=src pytest tests/test_analysis_fundamentals.py tests/test_analysis_boost.py tests/test_analysis_movement.py tests/test_analysis_positioning.py tests/test_analysis_passing.py tests/test_analysis_challenges.py tests/test_analysis_kickoffs.py tests/analysis/test_patterns.py tests/analysis/test_tendencies.py tests/analysis/test_weaknesses.py -q`  
Expected: PASS across the analysis stack.

**Verification plan:**
- Primary command: `source .venv/bin/activate && PYTHONPATH=src pytest tests/test_analysis_fundamentals.py tests/test_analysis_boost.py tests/test_analysis_movement.py tests/test_analysis_positioning.py tests/test_analysis_passing.py tests/test_analysis_challenges.py tests/test_analysis_kickoffs.py tests/analysis/test_patterns.py tests/analysis/test_tendencies.py tests/analysis/test_weaknesses.py -q`
- Secondary checks: `source .venv/bin/activate && PYTHONPATH=src pytest tests/api/test_analysis.py -q`

---

### Task 10: Bring Markdown And JSON Report Surfaces To Full Fidelity

**Parallel:** no  
**Blocked by:** Tasks 7, 8, 9  
**Owned files:** `src/rlcoach/report.py`, `src/rlcoach/report_markdown.py`, `codex/docs/json-report-markdown-mapping.md`, `tests/test_report_markdown.py`, `tests/test_report_metadata.py`, `tests/test_schema_validation.py`  
**Invariants:** The report contract remains machine-readable and markdown remains derivable from the same JSON.  
**Out of scope:** UI, API, SaaS surfaces.

**Files:**
- Modify: `src/rlcoach/report.py`
- Modify: `src/rlcoach/report_markdown.py`
- Modify: `codex/docs/json-report-markdown-mapping.md`
- Modify: `tests/test_report_markdown.py`
- Modify: `tests/test_report_metadata.py`
- Modify: `tests/test_schema_validation.py`

**Step 1: Write the failing test**
```python
def test_markdown_report_includes_full_advanced_mechanics_table():
    report = generate_report(Path("testing_replay.replay"), adapter_name="rust")
    markdown = compose_markdown_report(report)
    assert "Fast Aerials" in markdown
    assert "Flip Resets" in markdown
    assert "Skims" in markdown
    assert "Psychos" in markdown
```

**Step 2: Run test to verify it fails**  
Run: `source .venv/bin/activate && PYTHONPATH=src pytest tests/test_report_markdown.py::test_markdown_report_includes_full_advanced_mechanics_table -q`  
Expected: FAIL until markdown and JSON surfaces are aligned.

**Step 3: Write minimal implementation**
```python
mechanic_rows = [
    ("Fast Aerials", mechanics.get("fast_aerial_count", 0)),
    ("Flip Resets", mechanics.get("flip_reset_count", 0)),
    ("Skims", mechanics.get("skim_count", 0)),
    ("Psychos", mechanics.get("psycho_count", 0)),
]
```

**Step 4: Run test to verify it passes**  
Run: `source .venv/bin/activate && PYTHONPATH=src pytest tests/test_report_markdown.py tests/test_report_metadata.py tests/test_schema_validation.py -q`  
Expected: PASS with JSON and markdown in sync.

**Verification plan:**
- Primary command: `source .venv/bin/activate && PYTHONPATH=src pytest tests/test_report_markdown.py tests/test_report_metadata.py tests/test_schema_validation.py -q`
- Secondary checks: `source .venv/bin/activate && PYTHONPATH=src python -m rlcoach.cli report-md testing_replay.replay --out /tmp/rlcoach-full-report --pretty`

---

### Task 11: Add Real-Replay, Corpus-Health, And Performance Closure Gates

**Parallel:** no  
**Blocked by:** Tasks 1 through 10  
**Owned files:** `scripts/parser_corpus_health.py`, `src/rlcoach/benchmarks.py`, `tests/test_benchmarks.py`, `tests/test_data_benchmarks.py`, `tests/test_cli_benchmarks.py`, `tests/test_report_end_to_end.py`, `codex/docs/network-frames-integration-issue-report.md`  
**Invariants:** Preserve the diagnostics-first go/no-go policy for secondary backends; do not regress current `boxcars` success criteria.  
**Out of scope:** Shipping a second backend.

**Files:**
- Modify: `scripts/parser_corpus_health.py`
- Modify: `src/rlcoach/benchmarks.py`
- Modify: `tests/test_benchmarks.py`
- Modify: `tests/test_data_benchmarks.py`
- Modify: `tests/test_cli_benchmarks.py`
- Modify: `tests/test_report_end_to_end.py`
- Modify: `codex/docs/network-frames-integration-issue-report.md`

**Step 1: Write the failing test**
```python
def test_parser_corpus_health_enforces_full_contract_thresholds(tmp_path):
    result = run_parser_corpus_health_json(tmp_path)
    assert result["header_success_rate"] == 1.0
    assert result["network_success_rate"] >= 0.995
    assert result["usable_network_parse_rate"] >= 0.99
```

**Step 2: Run test to verify it fails**  
Run: `source .venv/bin/activate && PYTHONPATH=src pytest tests/test_benchmarks.py::test_parser_corpus_health_enforces_full_contract_thresholds -q`  
Expected: FAIL until the corpus-health script and scorecard expose the new thresholds.

**Step 3: Write minimal implementation**
```python
summary["usable_network_parse_rate"] = usable_network_count / max(total, 1)
summary["full_contract_replay_count"] = full_contract_count
```

**Step 4: Run test to verify it passes**  
Run: `source .venv/bin/activate && PYTHONPATH=src pytest tests/test_benchmarks.py tests/test_data_benchmarks.py tests/test_cli_benchmarks.py tests/test_report_end_to_end.py -q`  
Expected: PASS with corpus gates aligned to the full-contract definition.

**Verification plan:**
- Primary command: `source .venv/bin/activate && PYTHONPATH=src pytest tests/test_benchmarks.py tests/test_data_benchmarks.py tests/test_cli_benchmarks.py tests/test_report_end_to_end.py -q`
- Secondary checks: `source .venv/bin/activate && PYTHONPATH=src python scripts/parser_corpus_health.py --roots replays,Replay_files --json`

---

### Task 12: Restore Documentation And Operator Workflow Parity

**Parallel:** yes  
**Blocked by:** Tasks 3, 5, 6, 7, 10, 11  
**Owned files:** `docs/parser_adapter.md`, `README.md`, `docs/api.md`, `docs/user-guide.md`, `codex/docs/network-frames-integration-issue-report.md`  
**Invariants:** Documentation must describe the real shipped parser contract, not a future stub.  
**Out of scope:** Marketing copy, SaaS docs.

**Files:**
- Create: `docs/parser_adapter.md`
- Modify: `README.md`
- Modify: `docs/api.md`
- Modify: `docs/user-guide.md`
- Modify: `codex/docs/network-frames-integration-issue-report.md`

**Step 1: Write the failing test**
```python
def test_parser_adapter_docs_mention_parse_network_with_diagnostics():
    text = Path("docs/parser_adapter.md").read_text(encoding="utf-8")
    assert "parse_network_with_diagnostics" in text
    assert "debug_first_frames" in text
    assert "boost_pad_events" in text
```

**Step 2: Run test to verify it fails**  
Run: `source .venv/bin/activate && python - <<'PY'\nfrom pathlib import Path\nassert Path('docs/parser_adapter.md').exists()\nPY`  
Expected: FAIL because the file does not exist yet.

**Step 3: Write minimal implementation**
```md
## Rust Parser Contract
- `parse_header(path)`
- `parse_network_with_diagnostics(path)`
- `debug_first_frames(path, max_frames)`
```

**Step 4: Run test to verify it passes**  
Run: `source .venv/bin/activate && python - <<'PY'\nfrom pathlib import Path\ntext = Path('docs/parser_adapter.md').read_text(encoding='utf-8')\nassert 'parse_network_with_diagnostics' in text\nassert 'debug_first_frames' in text\nassert 'boost_pad_events' in text\nPY`  
Expected: PASS with docs matching the shipped system.

**Verification plan:**
- Primary command: `source .venv/bin/activate && python - <<'PY'\nfrom pathlib import Path\nfor path in ['docs/parser_adapter.md', 'README.md', 'docs/api.md', 'docs/user-guide.md']:\n    assert Path(path).exists(), path\nPY`
- Secondary checks: manually compare docs to the live parser contract before merge.

---

## Recommended Execution Order

1. Tasks 1 through 4
2. Tasks 5 and 6
3. Task 7
4. Task 8
5. Task 9
6. Task 10
7. Task 11
8. Task 12

## Real Gate Commands For This Repo

Use the venv for every Python command:

```bash
source .venv/bin/activate && PYTHONPATH=src pytest -q
source .venv/bin/activate && PYTHONPATH=src pytest tests/parser/test_rust_adapter_smoke.py tests/test_parser_interface.py tests/test_normalize.py tests/test_analysis_new_modules.py -q
source .venv/bin/activate && PYTHONPATH=src pytest tests/test_events.py tests/test_events_calibration_synthetic.py tests/test_report_end_to_end.py tests/test_report_markdown.py tests/test_schema_validation.py tests/test_schema_validation_hardening.py -q
source .venv/bin/activate && PYTHONPATH=src python scripts/parser_corpus_health.py --roots replays,Replay_files --json
make lint
make test
```

## Parallelization Notes

- Only Task 12 is marked `Parallel: yes` in this plan.
- Keep Tasks 1 through 11 sequential because they intentionally evolve a shared parser contract.
- If you later split implementation into tickets, first convert Tasks 5 through 12 into smaller ticket-builder-safe slices and re-run owned-files validation.

## Owned Files Validation

Run after any edits to this plan and before parallel ticket creation:

```bash
rg '\*\*Owned files:\*\*' docs/plans/2026-04-07-rlcoach-parser-analysis-full-vision.md \
  | sed 's/.*\*\*Owned files:\*\* *//' \
  | tr ',' '\n' \
  | sed 's/`//g' \
  | sed 's/^[[:space:]]*//;s/[[:space:]]*$//' \
  | rg -v '^$' \
  | sort \
  | uniq -d
```

## Execution Handoff

After reviewing this plan, the clean execution options are:

1. Execute sequentially in this session.
2. Split the plan into worktree-backed tickets after re-checking owned-file boundaries.
3. Start with Tasks 1 through 4 only and treat them as the contract-hardening tranche before opening parallel lanes.
