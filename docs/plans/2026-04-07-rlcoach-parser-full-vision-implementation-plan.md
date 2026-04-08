# RLCoach Parser Full Vision Implementation Plan

**Goal:** Take RLCoach from its current diagnostics-first Rust telemetry bridge plus downstream inference stack to a fully authoritative parser-and-analysis pipeline that captures the planned replay signals, powers the full mechanics/coaching vision, and is built, tested, and working end to end.

**Architecture:** Keep the current Rust `boxcars` + Python adapter/normalize/report pipeline, but finish the missing authority layers in order: discovery harnesses, parser contracts, Rust emission, normalization, event preference, mechanics preference, reporting, and corpus validation. The plan assumes we preserve graceful degradation and backward compatibility while steadily moving semantic ownership from Python heuristics to parser-authoritative streams wherever the replay data supports it.

**Tech Stack:** Rust (`boxcars`, `pyo3`), Python (`dataclasses`, `pytest`, `pytest-cov`), existing RLCoach parser/normalize/events/analysis/report stack, schema validation, markdown report generation, corpus-health harness.

---

## End-State Definition

“Full vision built tested and working” means all of the following are true:

1. The Rust parser emits authoritative header metadata, rich per-frame player/ball state, parser provenance, boost pad events, and explicit authoritative event streams where replay data allows.
2. The normalization layer preserves every authoritative parser signal in typed dataclasses without collapsing them back into anonymous dicts.
3. Events prefer parser authority first and fall back to inference only when the parser did not emit a usable signal.
4. The mechanics analyzer prefers parser authority first, uses richer parser-emitted context, and still keeps derivative fallbacks for degraded cases.
5. Reports and markdown output surface the full implemented mechanics set, including advanced mechanics already present in code.
6. The test suite contains unit, integration, golden, and corpus-health coverage for the full parser/report contract.
7. All repo-native gates pass with the project virtual environment:
   - `source .venv/bin/activate && PYTHONPATH=src pytest -q`
   - `make lint`
   - `source .venv/bin/activate && PYTHONPATH=src python scripts/parser_corpus_health.py --roots replays,Replay_files --json`

## Global Invariants

- No cloud dependencies, no remote services, no replay upload requirements.
- Preserve header-only and degraded-network fallback behavior.
- Keep parser output deterministic and schema-safe.
- Keep existing public CLI/report surfaces backward compatible where possible.
- Prefer parser-authoritative data, but never regress current inferred behavior for replays that do not expose the richer signals.
- Every new contract change must ship with schema tests, adapter tests, normalization tests, and at least one downstream consumer test.

---

### Task 0: Freeze the Current Baseline and Discovery Harnesses

**Parallel:** no  
**Blocked by:** none  
**Owned files:** `tests/parser/test_rust_adapter_smoke.py`, `tests/test_rust_adapter.py`, `tests/test_parser_interface.py`, `tests/test_benchmarks.py`, `scripts/parser_corpus_health.py`, `codex/logs/2026-04-07-parser-full-vision-baseline.md`  
**Invariants:** Do not change parser semantics yet; this task is characterization only.  
**Out of scope:** Adding new parser fields or changing report schema.

**Files:**
- Modify: `tests/parser/test_rust_adapter_smoke.py`
- Modify: `tests/test_rust_adapter.py`
- Modify: `tests/test_parser_interface.py`
- Modify: `tests/test_benchmarks.py`
- Modify: `scripts/parser_corpus_health.py`
- Create: `codex/logs/2026-04-07-parser-full-vision-baseline.md`

**Step 1: Write the failing test**
```python
def test_rust_frame_contract_baseline_snapshot():
    adapter = get_adapter("rust")
    frames = adapter.parse_network(Path("testing_replay.replay"))
    assert frames is not None
    assert frames.frame_count > 0
    sample = frames.frames[0]
    assert "ball" in sample
    assert "players" in sample
    assert "_parser_meta" in sample
```

**Step 2: Run test to verify it fails or requires updates**
Run: `source .venv/bin/activate && PYTHONPATH=src pytest tests/parser/test_rust_adapter_smoke.py::test_rust_frame_contract_baseline_snapshot -q`  
Expected: PASS or reveal the current live frame shape that the rest of this plan must preserve.

**Step 3: Write minimal implementation**
```python
# tests/test_rust_adapter.py
def test_debug_first_frames_available_when_rust_core_present():
    import rlreplay_rust
    payload = rlreplay_rust.debug_first_frames("testing_replay.replay", 5)
    assert isinstance(payload, list)
```

**Step 4: Run tests and baseline commands**
Run: `source .venv/bin/activate && PYTHONPATH=src pytest tests/parser/test_rust_adapter_smoke.py tests/test_rust_adapter.py tests/test_parser_interface.py -q`  
Expected: PASS.

**Step 5: Capture baseline evidence**
Run: `source .venv/bin/activate && PYTHONPATH=src python scripts/parser_corpus_health.py --roots replays,Replay_files --json`  
Expected: JSON summary with current header/network success rates and top error codes.

**Verification plan:**
- Primary command: `source .venv/bin/activate && PYTHONPATH=src pytest tests/parser/test_rust_adapter_smoke.py tests/test_rust_adapter.py tests/test_parser_interface.py -q`
- Secondary checks: `source .venv/bin/activate && PYTHONPATH=src python scripts/parser_corpus_health.py --roots replays,Replay_files --json`

---

### Task 1: Define the Authoritative Parser Contracts End to End

**Parallel:** no  
**Blocked by:** Task 0  
**Owned files:** `src/rlcoach/parser/types.py`, `src/rlcoach/events/types.py`, `schemas/replay_report.schema.json`, `tests/test_parser_interface.py`, `tests/test_schema_validation.py`, `tests/test_schema_validation_hardening.py`  
**Invariants:** Additive contracts only; do not remove current fields.  
**Out of scope:** Rust implementation details.

**Files:**
- Modify: `src/rlcoach/parser/types.py`
- Modify: `src/rlcoach/events/types.py`
- Modify: `schemas/replay_report.schema.json`
- Modify: `tests/test_parser_interface.py`
- Modify: `tests/test_schema_validation.py`
- Modify: `tests/test_schema_validation_hardening.py`

**Step 1: Write the failing test**
```python
def test_frame_supports_authoritative_parser_event_streams():
    from rlcoach.parser.types import Frame
    fields = Frame.__dataclass_fields__
    assert "touch_events" in fields
    assert "demo_events" in fields
    assert "kickoff_markers" in fields
    assert "tickmarks" in fields
```

**Step 2: Run test to verify it fails**
Run: `source .venv/bin/activate && PYTHONPATH=src pytest tests/test_parser_interface.py::test_frame_supports_authoritative_parser_event_streams -q`  
Expected: FAIL because the typed frame contract does not yet include those streams.

**Step 3: Write minimal implementation**
```python
@dataclass(frozen=True)
class ParserTouchEventFrame:
    t: float
    player_id: str | None = None
    actor_id: int | None = None
    location: Vec3 | None = None
    source: str = "parser"

@dataclass(frozen=True)
class ParserDemoEventFrame:
    t: float
    victim_id: str | None = None
    attacker_id: str | None = None
    source: str = "parser"

@dataclass(frozen=True)
class Frame:
    timestamp: float
    ball: BallFrame
    players: list[PlayerFrame] = field(default_factory=list)
    boost_pad_events: list[BoostPadEventFrame] = field(default_factory=list)
    touch_events: list[ParserTouchEventFrame] = field(default_factory=list)
    demo_events: list[ParserDemoEventFrame] = field(default_factory=list)
    kickoff_markers: list[dict[str, Any]] = field(default_factory=list)
    tickmarks: list[dict[str, Any]] = field(default_factory=list)
```

**Step 4: Extend schema tests**
Run: `source .venv/bin/activate && PYTHONPATH=src pytest tests/test_parser_interface.py tests/test_schema_validation.py tests/test_schema_validation_hardening.py -q`  
Expected: PASS after schema additions for richer parser/report metadata.

**Verification plan:**
- Primary command: `source .venv/bin/activate && PYTHONPATH=src pytest tests/test_parser_interface.py tests/test_schema_validation.py tests/test_schema_validation_hardening.py -q`
- Secondary checks: `source .venv/bin/activate && PYTHONPATH=src pytest tests/test_report_end_to_end.py -q`

---

### Task 2: Complete Rust Header Extraction to Match the Planned Header Vision

**Parallel:** no  
**Blocked by:** Task 1  
**Owned files:** `parsers/rlreplay_rust/src/lib.rs`, `src/rlcoach/parser/rust_adapter.py`, `tests/test_rust_adapter.py`, `tests/test_report_end_to_end.py`  
**Invariants:** Keep current `parse_header` return shape backward compatible.  
**Out of scope:** Network frame emission.

**Files:**
- Modify: `parsers/rlreplay_rust/src/lib.rs`
- Modify: `src/rlcoach/parser/rust_adapter.py`
- Modify: `tests/test_rust_adapter.py`
- Modify: `tests/test_report_end_to_end.py`

**Step 1: Write the failing test**
```python
def test_parse_header_exposes_extended_match_metadata():
    adapter = get_adapter("rust")
    header = adapter.parse_header(Path("testing_replay.replay"))
    assert hasattr(header, "engine_build")
    assert hasattr(header, "match_guid")
    assert hasattr(header, "overtime")
    assert hasattr(header, "mutators")
```

**Step 2: Run test to verify current gaps**
Run: `source .venv/bin/activate && PYTHONPATH=src pytest tests/test_rust_adapter.py::test_parse_header_exposes_extended_match_metadata -q`  
Expected: FAIL or reveal which fields are still missing/defaulted.

**Step 3: Write minimal implementation**
```rust
if let Some(p) = find_prop(&properties, "MatchGuid") {
    if let Some(s) = p.as_string() {
        header.set_item("match_guid", s)?;
    }
}
if let Some(p) = find_prop(&properties, "bMatchEndedInOvertime") {
    if let Some(v) = p.as_bool() {
        header.set_item("overtime", v)?;
    }
}
```

```python
return Header(
    ...,
    engine_build=d.get("engine_build"),
    match_guid=d.get("match_guid"),
    overtime=d.get("overtime"),
    mutators=d.get("mutators", {}),
)
```

**Step 4: Run tests to verify pass**
Run: `source .venv/bin/activate && PYTHONPATH=src pytest tests/test_rust_adapter.py tests/test_report_end_to_end.py -q`  
Expected: PASS.

**Verification plan:**
- Primary command: `source .venv/bin/activate && PYTHONPATH=src pytest tests/test_rust_adapter.py tests/test_report_end_to_end.py -q`
- Secondary checks: `source .venv/bin/activate && PYTHONPATH=src python -m rlcoach.cli report-md testing_replay.replay --out /tmp/rlcoach-plan-check --pretty`

---

### Task 3: Make Player Frame Authority Complete, Not Pulse-Only

**Parallel:** no  
**Blocked by:** Task 1  
**Owned files:** `parsers/rlreplay_rust/src/lib.rs`, `src/rlcoach/parser/types.py`, `src/rlcoach/normalize.py`, `tests/test_rust_adapter.py`, `tests/test_normalize.py`, `tests/test_analysis_new_modules.py`  
**Invariants:** Preserve existing derivative fallback when parser authority is absent.  
**Out of scope:** Touch/demo event streams.

**Files:**
- Modify: `parsers/rlreplay_rust/src/lib.rs`
- Modify: `src/rlcoach/parser/types.py`
- Modify: `src/rlcoach/normalize.py`
- Modify: `tests/test_rust_adapter.py`
- Modify: `tests/test_normalize.py`
- Modify: `tests/test_analysis_new_modules.py`

**Step 1: Write the failing test**
```python
def test_authoritative_component_flags_preserve_false_not_none():
    raw = [{
        "timestamp": 0.0,
        "ball": {"position": {"x": 0, "y": 0, "z": 93}, "velocity": {}, "angular_velocity": {}},
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
    frames = build_normalized_frames(make_header(), raw)
    player = frames[0].players[0]
    assert player.is_jumping is False
```

**Step 2: Run test to verify it fails**
Run: `source .venv/bin/activate && PYTHONPATH=src pytest tests/test_normalize.py::test_authoritative_component_flags_preserve_false_not_none -q`  
Expected: FAIL if the parser/normalize path still collapses inactive flags to `None`.

**Step 3: Write minimal implementation**
```rust
p.set_item("is_jumping", frame_jumping_actors.contains(&aid))?;
p.set_item("is_dodging", frame_dodging_actors.contains(&aid))?;
p.set_item("is_double_jumping", frame_double_jumping_actors.contains(&aid))?;
```

**Step 4: Run parser + mechanics authority tests**
Run: `source .venv/bin/activate && PYTHONPATH=src pytest tests/test_rust_adapter.py tests/test_normalize.py tests/test_analysis_new_modules.py -q`  
Expected: PASS.

**Verification plan:**
- Primary command: `source .venv/bin/activate && PYTHONPATH=src pytest tests/test_rust_adapter.py tests/test_normalize.py tests/test_analysis_new_modules.py -q`
- Secondary checks: `source .venv/bin/activate && PYTHONPATH=src pytest tests/parser/test_rust_adapter_smoke.py -q`

---

### Task 4: Emit an Authoritative Touch Stream from Rust

**Parallel:** no  
**Blocked by:** Tasks 0, 1, 3  
**Owned files:** `parsers/rlreplay_rust/src/lib.rs`, `src/rlcoach/parser/types.py`, `src/rlcoach/normalize.py`, `tests/parser/test_rust_adapter_smoke.py`, `tests/test_normalize.py`, `tests/test_events.py`  
**Invariants:** Preserve current inferred touch detection until authoritative touches are proven complete.  
**Out of scope:** Replacing Python touch classification logic in the same task.

**Files:**
- Modify: `parsers/rlreplay_rust/src/lib.rs`
- Modify: `src/rlcoach/parser/types.py`
- Modify: `src/rlcoach/normalize.py`
- Modify: `tests/parser/test_rust_adapter_smoke.py`
- Modify: `tests/test_normalize.py`
- Modify: `tests/test_events.py`

**Step 1: Write the failing test**
```python
def test_normalized_frame_preserves_parser_touch_events():
    raw = [{
        "timestamp": 0.0,
        "ball": {"position": {"x": 0, "y": 0, "z": 93}, "velocity": {}, "angular_velocity": {}},
        "players": [],
        "touch_events": [{"t": 0.0, "player_id": "player_0", "source": "parser"}],
    }]
    frames = build_normalized_frames(make_header(), raw)
    assert len(frames[0].touch_events) == 1
```

**Step 2: Run test to verify it fails**
Run: `source .venv/bin/activate && PYTHONPATH=src pytest tests/test_normalize.py::test_normalized_frame_preserves_parser_touch_events -q`  
Expected: FAIL because `Frame` does not yet carry typed touch events end to end.

**Step 3: Write minimal implementation**
```rust
let touch_list = PyList::empty(py);
// append parser-derived touch dicts with timestamp/player_id/location/source
f.set_item("touch_events", touch_list)?;
```

```python
touch_events = [
    ParserTouchEventFrame(
        t=float(raw["t"]),
        player_id=raw.get("player_id"),
        location=to_field_coords(raw.get("location")) if raw.get("location") else None,
        source="parser",
    )
    for raw in raw_touch_events
]
```

**Step 4: Run touch-focused tests**
Run: `source .venv/bin/activate && PYTHONPATH=src pytest tests/parser/test_rust_adapter_smoke.py tests/test_normalize.py tests/test_events.py -q`  
Expected: PASS.

**Verification plan:**
- Primary command: `source .venv/bin/activate && PYTHONPATH=src pytest tests/parser/test_rust_adapter_smoke.py tests/test_normalize.py tests/test_events.py -q`
- Secondary checks: `source .venv/bin/activate && PYTHONPATH=src python -m rlcoach.cli analyze testing_replay.replay --adapter rust --out /tmp/rlcoach-touch-check`

---

### Task 5: Emit Authoritative Demo, Kickoff, and Tickmark Streams from Rust

**Parallel:** no  
**Blocked by:** Tasks 0 and 1  
**Owned files:** `parsers/rlreplay_rust/src/lib.rs`, `src/rlcoach/parser/types.py`, `src/rlcoach/normalize.py`, `tests/parser/test_rust_adapter_smoke.py`, `tests/test_events.py`, `tests/test_report_end_to_end.py`  
**Invariants:** If parser event attribution is incomplete, preserve the Python fallback inference path.  
**Out of scope:** Rewriting challenge logic in the same task.

**Files:**
- Modify: `parsers/rlreplay_rust/src/lib.rs`
- Modify: `src/rlcoach/parser/types.py`
- Modify: `src/rlcoach/normalize.py`
- Modify: `tests/parser/test_rust_adapter_smoke.py`
- Modify: `tests/test_events.py`
- Modify: `tests/test_report_end_to_end.py`

**Step 1: Write the failing test**
```python
def test_frame_supports_authoritative_demo_and_tickmark_streams():
    frame = build_normalized_frames(make_header(), [{
        "timestamp": 0.0,
        "ball": {"position": {"x": 0, "y": 0, "z": 93}, "velocity": {}, "angular_velocity": {}},
        "players": [],
        "demo_events": [{"t": 0.0, "victim_id": "player_1", "source": "parser"}],
        "tickmarks": [{"frame": 123, "label": "Goal"}],
    }])[0]
    assert len(frame.demo_events) == 1
    assert len(frame.tickmarks) == 1
```

**Step 2: Run test to verify it fails**
Run: `source .venv/bin/activate && PYTHONPATH=src pytest tests/test_normalize.py::test_frame_supports_authoritative_demo_and_tickmark_streams -q`  
Expected: FAIL until the frame contract and normalization path are extended.

**Step 3: Write minimal implementation**
```rust
let demo_list = PyList::empty(py);
let tickmark_list = PyList::empty(py);
f.set_item("demo_events", demo_list)?;
f.set_item("tickmarks", tickmark_list)?;
```

**Step 4: Run event/report tests**
Run: `source .venv/bin/activate && PYTHONPATH=src pytest tests/parser/test_rust_adapter_smoke.py tests/test_events.py tests/test_report_end_to_end.py -q`  
Expected: PASS.

**Verification plan:**
- Primary command: `source .venv/bin/activate && PYTHONPATH=src pytest tests/parser/test_rust_adapter_smoke.py tests/test_events.py tests/test_report_end_to_end.py -q`
- Secondary checks: `source .venv/bin/activate && PYTHONPATH=src pytest tests/test_schema_validation.py tests/test_schema_validation_hardening.py -q`

---

### Task 6: Normalize and Preserve Every New Parser-Authoritative Stream

**Parallel:** no  
**Blocked by:** Tasks 4 and 5  
**Owned files:** `src/rlcoach/normalize.py`, `src/rlcoach/parser/types.py`, `tests/test_normalize.py`, `tests/test_parser_interface.py`  
**Invariants:** `build_normalized_frames(...)` must remain resilient to partial raw payloads and malformed frames.  
**Out of scope:** Event consumer preference logic.

**Files:**
- Modify: `src/rlcoach/normalize.py`
- Modify: `src/rlcoach/parser/types.py`
- Modify: `tests/test_normalize.py`
- Modify: `tests/test_parser_interface.py`

**Step 1: Write the failing test**
```python
def test_build_timeline_keeps_authoritative_parser_streams_typed():
    frames = build_normalized_frames(make_header(), [make_raw_frame_with_parser_streams()])
    frame = frames[0]
    assert isinstance(frame.touch_events, list)
    assert isinstance(frame.demo_events, list)
    assert isinstance(frame.kickoff_markers, list)
    assert isinstance(frame.tickmarks, list)
```

**Step 2: Run test to verify it fails**
Run: `source .venv/bin/activate && PYTHONPATH=src pytest tests/test_normalize.py::test_build_timeline_keeps_authoritative_parser_streams_typed -q`  
Expected: FAIL until normalization carries all new fields through.

**Step 3: Write minimal implementation**
```python
normalized_frame = Frame(
    timestamp=timestamp,
    ball=ball_frame,
    players=list(player_frames_map.values()),
    boost_pad_events=pad_events,
    touch_events=touch_events,
    demo_events=demo_events,
    kickoff_markers=kickoff_markers,
    tickmarks=tickmarks,
)
```

**Step 4: Run normalization/interface tests**
Run: `source .venv/bin/activate && PYTHONPATH=src pytest tests/test_normalize.py tests/test_parser_interface.py -q`  
Expected: PASS.

**Verification plan:**
- Primary command: `source .venv/bin/activate && PYTHONPATH=src pytest tests/test_normalize.py tests/test_parser_interface.py -q`
- Secondary checks: `source .venv/bin/activate && PYTHONPATH=src pytest tests/test_schema_validation.py -q`

---

### Task 7: Make Events Prefer Authoritative Parser Streams with Safe Fallbacks

**Parallel:** no  
**Blocked by:** Tasks 4, 5, 6  
**Owned files:** `src/rlcoach/events/touches.py`, `src/rlcoach/events/demos.py`, `src/rlcoach/events/kickoffs.py`, `src/rlcoach/events/timeline.py`, `tests/test_events.py`, `tests/test_events_calibration_synthetic.py`, `tests/test_report_end_to_end.py`  
**Invariants:** If parser streams are absent or degraded, current inference behavior must remain intact.  
**Out of scope:** Mechanics analyzer changes.

**Files:**
- Modify: `src/rlcoach/events/touches.py`
- Modify: `src/rlcoach/events/demos.py`
- Modify: `src/rlcoach/events/kickoffs.py`
- Modify: `src/rlcoach/events/timeline.py`
- Modify: `tests/test_events.py`
- Modify: `tests/test_events_calibration_synthetic.py`
- Modify: `tests/test_report_end_to_end.py`

**Step 1: Write the failing test**
```python
def test_detect_touches_prefers_parser_touch_events():
    frames = [make_frame_with_authoritative_touch()]
    touches = detect_touches(frames)
    assert len(touches) == 1
    assert touches[0].player_id == "player_0"
```

**Step 2: Run test to verify it fails**
Run: `source .venv/bin/activate && PYTHONPATH=src pytest tests/test_events.py::test_detect_touches_prefers_parser_touch_events -q`  
Expected: FAIL because `detect_touches` only uses inferred proximity today.

**Step 3: Write minimal implementation**
```python
def detect_touches(frames: list[Frame]) -> list[TouchEvent]:
    parser_events = _touches_from_parser_stream(frames)
    if parser_events:
        return parser_events
    return _detect_touches_legacy(frames)
```

**Step 4: Run event suite**
Run: `source .venv/bin/activate && PYTHONPATH=src pytest tests/test_events.py tests/test_events_calibration_synthetic.py tests/test_report_end_to_end.py -q`  
Expected: PASS.

**Verification plan:**
- Primary command: `source .venv/bin/activate && PYTHONPATH=src pytest tests/test_events.py tests/test_events_calibration_synthetic.py tests/test_report_end_to_end.py -q`
- Secondary checks: `source .venv/bin/activate && PYTHONPATH=src pytest tests/test_analysis_fundamentals.py tests/test_analysis_challenges.py -q`

---

### Task 8: Upgrade Mechanics to Consume Parser Authority Before Heuristics

**Parallel:** no  
**Blocked by:** Tasks 3, 4, 6, 7  
**Owned files:** `src/rlcoach/analysis/mechanics.py`, `src/rlcoach/events/touches.py`, `tests/test_analysis_new_modules.py`, `tests/test_report_end_to_end.py`  
**Invariants:** Do not regress current advanced mechanics detections on replays where authority is absent.  
**Out of scope:** Team/report rollups.

**Files:**
- Modify: `src/rlcoach/analysis/mechanics.py`
- Modify: `src/rlcoach/events/touches.py`
- Modify: `tests/test_analysis_new_modules.py`
- Modify: `tests/test_report_end_to_end.py`

**Step 1: Write the failing test**
```python
def test_flip_reset_prefers_authoritative_touch_context_when_present():
    frames = make_frames_with_authoritative_reset_touch()
    result = analyze_mechanics(frames)
    player = result["per_player"]["player_0"]
    assert player["flip_reset_count"] == 1
```

**Step 2: Run test to verify it fails**
Run: `source .venv/bin/activate && PYTHONPATH=src pytest tests/test_analysis_new_modules.py::test_flip_reset_prefers_authoritative_touch_context_when_present -q`  
Expected: FAIL until mechanics consumes richer parser/touch authority.

**Step 3: Write minimal implementation**
```python
authoritative_touches = _index_parser_touch_events(frames, player_id)
if authoritative_touches:
    # Prefer parser-emitted contact timing/context before proximity fallback
    ...
else:
    # existing derivative fallback
    ...
```

**Step 4: Run mechanics/report tests**
Run: `source .venv/bin/activate && PYTHONPATH=src pytest tests/test_analysis_new_modules.py tests/test_report_end_to_end.py -q`  
Expected: PASS.

**Verification plan:**
- Primary command: `source .venv/bin/activate && PYTHONPATH=src pytest tests/test_analysis_new_modules.py tests/test_report_end_to_end.py -q`
- Secondary checks: `source .venv/bin/activate && PYTHONPATH=src pytest tests/test_events.py tests/test_normalize.py -q`

---

### Task 9: Finish Report and Markdown Surfaces for the Full Mechanics Model

**Parallel:** no  
**Blocked by:** Task 8  
**Owned files:** `src/rlcoach/analysis/__init__.py`, `src/rlcoach/analysis/mechanics.py`, `src/rlcoach/report.py`, `src/rlcoach/report_markdown.py`, `schemas/replay_report.schema.json`, `tests/test_report_end_to_end.py`, `tests/test_report_markdown.py`, `tests/test_schema_validation.py`  
**Invariants:** Output must stay schema-valid and markdown generation must remain atomic.  
**Out of scope:** Parser implementation.

**Files:**
- Modify: `src/rlcoach/analysis/__init__.py`
- Modify: `src/rlcoach/analysis/mechanics.py`
- Modify: `src/rlcoach/report.py`
- Modify: `src/rlcoach/report_markdown.py`
- Modify: `schemas/replay_report.schema.json`
- Modify: `tests/test_report_end_to_end.py`
- Modify: `tests/test_report_markdown.py`
- Modify: `tests/test_schema_validation.py`

**Step 1: Write the failing test**
```python
def test_report_surfaces_skim_and_psycho_counts():
    report = generate_report(Path("testing_replay.replay"), adapter_name="rust")
    player = next(iter(report["analysis"]["per_player"].values()))
    assert "skim_count" in player["mechanics"]
    assert "psycho_count" in player["mechanics"]
```

**Step 2: Run test to verify it fails**
Run: `source .venv/bin/activate && PYTHONPATH=src pytest tests/test_report_end_to_end.py::test_report_surfaces_skim_and_psycho_counts -q`  
Expected: FAIL because the schema allows those fields but the rollup does not emit them today.

**Step 3: Write minimal implementation**
```python
"skim_count": counts.get("skim", 0),
"psycho_count": counts.get("psycho", 0),
```

```python
return {
    "total_wavedashes": total_wavedashes,
    "total_halfflips": total_halfflips,
    "total_speedflips": total_speedflips,
    "total_aerials": total_aerials,
    "total_flips": total_flips,
    "total_flip_cancels": total_flip_cancels,
    "total_flip_resets": total_flip_resets,
    "total_dribbles": total_dribbles,
    "total_redirects": total_redirects,
}
```

**Step 4: Run report/schema tests**
Run: `source .venv/bin/activate && PYTHONPATH=src pytest tests/test_report_end_to_end.py tests/test_report_markdown.py tests/test_schema_validation.py -q`  
Expected: PASS.

**Verification plan:**
- Primary command: `source .venv/bin/activate && PYTHONPATH=src pytest tests/test_report_end_to_end.py tests/test_report_markdown.py tests/test_schema_validation.py -q`
- Secondary checks: `source .venv/bin/activate && PYTHONPATH=src python -m rlcoach.cli report-md testing_replay.replay --out /tmp/rlcoach-report-plan --pretty`

---

### Task 10: Add the Missing Goldens, Mechanics Fixtures, and Corpus Gates

**Parallel:** no  
**Blocked by:** Tasks 4 through 9  
**Owned files:** `tests/fixtures/builders.py`, `tests/test_analysis_new_modules.py`, `tests/test_events.py`, `tests/test_report_end_to_end.py`, `tests/test_report_markdown.py`, `tests/goldens/*.md`, `tests/test_benchmarks.py`, `scripts/parser_corpus_health.py`  
**Invariants:** New tests must be deterministic and runnable locally with the project venv.  
**Out of scope:** Product/UI work.

**Files:**
- Modify: `tests/fixtures/builders.py`
- Modify: `tests/test_analysis_new_modules.py`
- Modify: `tests/test_events.py`
- Modify: `tests/test_report_end_to_end.py`
- Modify: `tests/test_report_markdown.py`
- Modify: `tests/test_benchmarks.py`
- Modify: `scripts/parser_corpus_health.py`
- Create: `tests/goldens/advanced_mechanics.md`
- Create: `tests/goldens/parser_authoritative_events.md`

**Step 1: Write the failing test**
```python
def test_parser_corpus_health_reports_authoritative_touch_and_demo_coverage(tmp_path):
    payload = run_corpus_health_json(tmp_path)
    assert "usable_network_parse_rate" in payload
    assert "top_error_codes" in payload
```

**Step 2: Run test to verify it fails or needs expansion**
Run: `source .venv/bin/activate && PYTHONPATH=src pytest tests/test_benchmarks.py::test_parser_corpus_health_reports_authoritative_touch_and_demo_coverage -q`  
Expected: FAIL until the harness is extended for the new authority metrics.

**Step 3: Write minimal implementation**
```python
summary["authoritative_touch_coverage_rate"] = ...
summary["authoritative_demo_coverage_rate"] = ...
summary["header_metadata_completeness_rate"] = ...
```

**Step 4: Run focused regression set**
Run: `source .venv/bin/activate && PYTHONPATH=src pytest tests/test_analysis_new_modules.py tests/test_events.py tests/test_report_end_to_end.py tests/test_report_markdown.py tests/test_benchmarks.py -q`  
Expected: PASS.

**Verification plan:**
- Primary command: `source .venv/bin/activate && PYTHONPATH=src pytest tests/test_analysis_new_modules.py tests/test_events.py tests/test_report_end_to_end.py tests/test_report_markdown.py tests/test_benchmarks.py -q`
- Secondary checks: `source .venv/bin/activate && PYTHONPATH=src python scripts/parser_corpus_health.py --roots replays,Replay_files --json`

---

### Task 11: Close the Loop with Full-Gate Verification and Documentation

**Parallel:** no  
**Blocked by:** Tasks 0 through 10  
**Owned files:** `README.md`, `docs/cli-agents-reference.md`, `codex/docs/master_status.md`, `codex/logs/2026-04-07-parser-full-vision-baseline.md`, `docs/plans/2026-04-07-rlcoach-parser-full-vision-implementation-plan.md`  
**Invariants:** Documentation must reflect the real implementation, not aspirational behavior.  
**Out of scope:** New product features outside parser/analysis/report scope.

**Files:**
- Modify: `README.md`
- Modify: `docs/cli-agents-reference.md`
- Modify: `codex/docs/master_status.md`
- Modify: `codex/logs/2026-04-07-parser-full-vision-baseline.md`

**Step 1: Write the failing test**
```python
def test_report_contract_docs_match_schema_version():
    assert get_schema_version().startswith("1.0.")
```

**Step 2: Run full gates**
Run: `source .venv/bin/activate && PYTHONPATH=src pytest -q`  
Expected: PASS.

**Step 3: Run repo-native quality checks**
Run: `make lint`  
Expected: PASS.

**Step 4: Run corpus-health verification**
Run: `source .venv/bin/activate && PYTHONPATH=src python scripts/parser_corpus_health.py --roots replays,Replay_files --json`  
Expected: Healthy summary with diagnostics, usable-network rates, and no unexplained regressions.

**Step 5: Update docs only after gates are green**
```markdown
- Parser emits authoritative frame telemetry and parser event streams.
- Events/mechanics prefer parser authority first and degrade safely.
- Report/markdown surfaces match the implemented schema.
```

**Verification plan:**
- Primary command: `source .venv/bin/activate && PYTHONPATH=src pytest -q`
- Secondary checks: `make lint`
- Tertiary checks: `source .venv/bin/activate && PYTHONPATH=src python scripts/parser_corpus_health.py --roots replays,Replay_files --json`

---

## Dependency Graph

- Task 0 first.
- Task 1 before any new parser event emission.
- Task 2 can start after Task 1.
- Task 3 can start after Task 1.
- Task 4 depends on Tasks 0, 1, 3.
- Task 5 depends on Tasks 0 and 1.
- Task 6 depends on Tasks 4 and 5.
- Task 7 depends on Tasks 4, 5, 6.
- Task 8 depends on Tasks 3, 4, 6, 7.
- Task 9 depends on Task 8.
- Task 10 depends on Tasks 4 through 9.
- Task 11 depends on everything.

## Parallelization Notes

- Safe early parallelism is limited because `parsers/rlreplay_rust/src/lib.rs`, `src/rlcoach/parser/types.py`, `src/rlcoach/normalize.py`, `src/rlcoach/events/*`, and `src/rlcoach/analysis/mechanics.py` are central chokepoints.
- If you later want ticketized execution, the best split is:
  - lane A: header completeness and parser contracts
  - lane B: authoritative touch/demo/tickmark emission
  - lane C: reporting/markdown/schema finish work after parser contracts stabilize

## Owned Files Validation

This baseline plan is intentionally sequential. If you later extract a parallel subset into separate tickets, run the validation command against only the tasks marked `Parallel: yes` in that derived ticket set, not against this entire document:

```bash
rg '\*\*Owned files:\*\*' docs/plans/2026-04-07-rlcoach-parser-full-vision-implementation-plan.md \
  | sed 's/.*\*\*Owned files:\*\* *//' \
  | tr ',' '\n' \
  | sed 's/`//g' \
  | sed 's/^[[:space:]]*//;s/[[:space:]]*$//' \
  | rg -v '^$' \
  | sort \
  | uniq -d
```

## Final Acceptance Checklist

- [ ] Rust parser emits authoritative header metadata expected by the broad architecture plan.
- [ ] Rust parser emits authoritative frame telemetry plus touch/demo/kickoff/tickmark streams where replay data supports it.
- [ ] Normalization preserves every authoritative parser stream in typed dataclasses.
- [ ] Events prefer parser authority first and retain safe fallback behavior.
- [ ] Mechanics prefer parser authority first and retain safe fallback behavior.
- [ ] Reports surface the full advanced mechanics set, including `skim` and `psycho`.
- [ ] Markdown output reflects the full report surface.
- [ ] `source .venv/bin/activate && PYTHONPATH=src pytest -q` passes.
- [ ] `make lint` passes.
- [ ] `source .venv/bin/activate && PYTHONPATH=src python scripts/parser_corpus_health.py --roots replays,Replay_files --json` passes with no unexplained regressions.

## Execution Handoff

Recommended execution options:

1. Execute sequentially in this session.
2. Convert Tasks 2 through 10 into isolated worktree tickets after validating owned-file overlap.
3. Run a plan review before implementation to tighten any task whose discovery sub-steps uncover different replay-property names than expected.
