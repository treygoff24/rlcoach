# Replay Parser Refactor and Reliability Upgrade Implementation Plan

**Goal:** Refactor the replay parser stack to maximize authoritative data extraction from `.replay` files, reduce silent degradation, and only introduce a non-boxcars backend if measured reliability thresholds are not met.

**Architecture:** Keep the current Rust (`boxcars`) + Python adapter pipeline, but add explicit diagnostics/provenance, parse-mode hardening, authoritative component-state extraction, and corpus-level regression tests. Introduce a backend-abstraction seam and a decision gate for optional fallback backend implementation (instead of immediate full parser replacement).

**Tech Stack:** Rust (`boxcars`, `pyo3`), Python (`pytest`, dataclasses), existing RLCoach parser/normalize/events/analysis modules.

---

## Why This Plan

- Replay files contain both header metadata and network replication data; we already extract substantial authoritative data.
- Current risk is not “no data,” it is **unreported degradation** and **over-inference when authoritative signals exist**.
- A full parser rewrite now is high risk and high maintenance; measured hardening + fallback seam gives better ROI.

---

## Success Criteria

1. `parse_network` never fails silently: every degraded parse has machine-readable diagnostics in report quality warnings.
2. Corpus target: >= 99.5% network parse availability on a representative local replay corpus (header parse remains 100%).
3. LTM/unknown-attribute replay no longer produces opaque fallback; root cause appears in diagnostics.
4. Parser emits authoritative component-state flags (`jump/dodge/double-jump`) when present.
5. Mechanics analyzer prefers authoritative flags over pure derivative inference when available.
6. New regression suite covers diagnostics, LTM degradation behavior, and component-state extraction.
7. Decision gate completed for secondary backend (rrrocket/subtr-actor/custom), with explicit go/no-go criteria.

---

## Non-Goals

- Replacing all analytics logic in one pass.
- Immediate full custom replay decoder implementation.
- Adding cloud dependencies.

---

## Task Breakdown

## Pre-requisite: Performance Baseline

**Objective:** Establish pre-refactor performance and memory baseline so diagnostics/provenance additions can be measured objectively.

**Files:**
- Modify: `tests/test_benchmarks.py`
- Create (optional): `scripts/parser_perf_baseline.py`

**Steps:**
1. Add/verify a benchmark case for rust adapter parse latency and memory on replay samples.
2. Record baseline on at least 100 replays across `replays/` and `Replay_files/` with mixed modes (private, tournament, ranked).
3. Save baseline results in `codex/logs/2026-02-10-parser-perf-baseline.md`.

---

### Task 1: Define Parser Diagnostics and Provenance Contract

**Parallel:** no  
**Blocked by:** none  
**Owned files:** `src/rlcoach/parser/types.py`, `src/rlcoach/report.py`, `schemas/replay_report.schema.json`, `tests/test_schema_validation.py`, `tests/test_schema_validation_hardening.py`

**Files:**
- Modify: `src/rlcoach/parser/types.py`
- Modify: `src/rlcoach/report.py`
- Modify: `schemas/replay_report.schema.json`
- Modify: `tests/test_schema_validation.py`
- Modify: `tests/test_schema_validation_hardening.py`

**Step 1: Write the failing test**
```python
# tests/test_schema_validation.py

def test_quality_parser_supports_network_diagnostics():
    report = make_minimal_report()
    report["quality"]["parser"]["network_diagnostics"] = {
        "status": "degraded",
        "error_code": "boxcars_network_error",
        "error_detail": "unknown attributes for object",
        "frames_emitted": 0,
    }
    validate_report(report)
```

**Step 2: Run test to verify it fails**  
Run: `source .venv/bin/activate && PYTHONPATH=src pytest tests/test_schema_validation.py::test_quality_parser_supports_network_diagnostics -q`  
Expected: FAIL with schema additional-properties/unknown field error.

**Step 3: Write minimal implementation**
```python
# src/rlcoach/parser/types.py (example dataclass)
@dataclass(frozen=True)
class NetworkDiagnostics:
    status: str  # "ok" | "degraded" | "unavailable"
    error_code: str | None = None
    error_detail: str | None = None
    frames_emitted: int | None = None
```

```json
// schemas/replay_report.schema.json (parser section)
"network_diagnostics": {
  "type": "object",
  "properties": {
    "status": {"type": "string"},
    "error_code": {"type": ["string", "null"]},
    "error_detail": {"type": ["string", "null"]},
    "frames_emitted": {"type": ["integer", "null"]}
  },
  "additionalProperties": false
}
```

**Step 4: Run test to verify it passes**  
Run: `source .venv/bin/activate && PYTHONPATH=src pytest tests/test_schema_validation.py::test_quality_parser_supports_network_diagnostics -q`  
Expected: PASS.

---

### Task 2: Add Rust Network Parse API with Diagnostics (No Silent Loss)

**Parallel:** no  
**Blocked by:** Task 1  
**Owned files:** `parsers/rlreplay_rust/src/lib.rs`, `tests/parser/test_rust_adapter_smoke.py`

**Files:**
- Modify: `parsers/rlreplay_rust/src/lib.rs`
- Modify: `tests/parser/test_rust_adapter_smoke.py`

**Step 1: Write the failing test**
```python
# tests/parser/test_rust_adapter_smoke.py

def test_rust_network_parse_returns_diagnostics_shape():
    import rlreplay_rust
    result = rlreplay_rust.parse_network_with_diagnostics("testing_replay.replay")
    assert isinstance(result, dict)
    assert "frames" in result
    assert "diagnostics" in result
```

**Step 2: Run test to verify it fails**  
Run: `source .venv/bin/activate && PYTHONPATH=src pytest tests/parser/test_rust_adapter_smoke.py::test_rust_network_parse_returns_diagnostics_shape -q`  
Expected: FAIL (`AttributeError: module has no attribute parse_network_with_diagnostics`).

**Step 3: Write minimal implementation**
```rust
// parsers/rlreplay_rust/src/lib.rs
#[pyfunction]
fn parse_network_with_diagnostics(path: &str) -> PyResult<PyObject> {
    // 1) try must_parse_network_data for strict success
    // 2) on error, retry ignore_network_data_on_error to salvage frames
    // 3) explicitly map low-level parse errors into stable error_code/error_detail fields
    // 4) return {"frames": [...], "diagnostics": {...}}
}
```

**Step 4: Run test to verify it passes**  
Run: `source .venv/bin/activate && PYTHONPATH=src pytest tests/parser/test_rust_adapter_smoke.py::test_rust_network_parse_returns_diagnostics_shape -q`  
Expected: PASS.

**Step 5: Performance checkpoint**  
Run: `source .venv/bin/activate && PYTHONPATH=src python scripts/parser_perf_baseline.py --sample 100 --json`  
Expected: no material regression versus pre-requisite baseline, or documented deltas with mitigation follow-up.

---

### Task 3: Harden Rust Classification and Frame Metadata Emission

**Parallel:** no  
**Blocked by:** Task 2  
**Owned files:** `parsers/rlreplay_rust/src/lib.rs`, `tests/test_rust_adapter.py`

**Files:**
- Modify: `parsers/rlreplay_rust/src/lib.rs`
- Modify: `tests/test_rust_adapter.py`

**Step 1: Write the failing test**
```python
# tests/test_rust_adapter.py

def test_frame_contains_parser_frame_meta_when_available():
    frames = _load_frames(limit=5)
    meta = frames[0].get("_parser_meta")
    assert isinstance(meta, dict)
    assert "classification_source" in meta
```

**Step 2: Run test to verify it fails**  
Run: `source .venv/bin/activate && PYTHONPATH=src pytest tests/test_rust_adapter.py::test_frame_contains_parser_frame_meta_when_available -q`  
Expected: FAIL (`None is not dict`).

**Step 3: Write minimal implementation**
```rust
// attach frame-level parser metadata
f.set_item("_parser_meta", meta_dict)?;
```

Include classification source markers such as:
- `object_name` (default)
- `fallback_unclassified`
- `component_owner_chain`

Keep this payload minimal and deterministic to avoid avoidable serialization overhead.

**Step 4: Run test to verify it passes**  
Run: `source .venv/bin/activate && PYTHONPATH=src pytest tests/test_rust_adapter.py::test_frame_contains_parser_frame_meta_when_available -q`  
Expected: PASS.

---

### Task 4: Emit Authoritative Jump/Dodge/DoubleJump Component Flags

**Parallel:** no  
**Blocked by:** Task 3  
**Owned files:** `parsers/rlreplay_rust/src/lib.rs`, `src/rlcoach/parser/types.py`, `src/rlcoach/normalize.py`, `tests/test_normalize.py`, `tests/test_analysis_new_modules.py`

**Files:**
- Modify: `parsers/rlreplay_rust/src/lib.rs`
- Modify: `src/rlcoach/parser/types.py`
- Modify: `src/rlcoach/normalize.py`
- Modify: `tests/test_normalize.py`
- Modify: `tests/test_analysis_new_modules.py`

**Step 1: Write the failing test**
```python
# tests/test_normalize.py

def test_normalize_preserves_component_state_flags():
    raw = [{
        "timestamp": 0.0,
        "ball": {...},
        "players": [{
            "player_id": "player_0",
            "team": 0,
            "position": {"x":0,"y":0,"z":17},
            "velocity": {"x":0,"y":0,"z":0},
            "rotation": {"pitch":0,"yaw":0,"roll":0},
            "boost_amount": 33,
            "is_jumping": True,
            "is_dodging": False,
            "is_double_jumping": False,
        }],
    }]
    frames = build_normalized_frames(header, raw)
    assert frames[0].players[0].is_jumping is True
```

**Step 2: Run test to verify it fails**  
Run: `source .venv/bin/activate && PYTHONPATH=src pytest tests/test_normalize.py::test_normalize_preserves_component_state_flags -q`  
Expected: FAIL (attribute missing).

**Step 3: Write minimal implementation**
```python
# src/rlcoach/parser/types.py
@dataclass(frozen=True)
class PlayerFrame:
    ...
    # None means authoritative component state was unavailable for this sample.
    # True/False means parser observed and emitted state explicitly.
    is_jumping: bool | None = None
    is_dodging: bool | None = None
    is_double_jumping: bool | None = None
```

```rust
// parsers/rlreplay_rust/src/lib.rs (on player emission)
p.set_item("is_jumping", ...)?;
p.set_item("is_dodging", ...)?;
p.set_item("is_double_jumping", ...)?;
```

**Step 4: Run test to verify it passes**  
Run: `source .venv/bin/activate && PYTHONPATH=src pytest tests/test_normalize.py::test_normalize_preserves_component_state_flags -q`  
Expected: PASS.

---

### Task 5: Make Python Rust Adapter Diagnostics-First (No Broad Exception Swallow)

**Parallel:** no  
**Blocked by:** Task 2  
**Owned files:** `src/rlcoach/parser/rust_adapter.py`, `tests/test_rust_adapter.py`, `tests/test_parser_interface.py`

**Files:**
- Modify: `src/rlcoach/parser/rust_adapter.py`
- Modify: `tests/test_rust_adapter.py`
- Modify: `tests/test_parser_interface.py`

**Step 1: Write the failing test**
```python
# tests/test_rust_adapter.py

def test_parse_network_returns_diagnostics_on_degradation(monkeypatch):
    adapter = RustAdapter()
    monkeypatch.setattr("rlcoach.parser.rust_adapter._rust", FakeRustDegraded())
    result = adapter.parse_network(Path("testing_replay.replay"))
    assert result is not None
    assert "network_error" in (result.diagnostics.error_code or "")
```

**Step 2: Run test to verify it fails**  
Run: `source .venv/bin/activate && PYTHONPATH=src pytest tests/test_rust_adapter.py::test_parse_network_returns_diagnostics_on_degradation -q`  
Expected: FAIL (current adapter returns `None` or lacks diagnostics).

**Step 3: Write minimal implementation**
```python
# src/rlcoach/parser/rust_adapter.py
parsed = _rust.parse_network_with_diagnostics(str(path))
frames = parsed.get("frames", [])
diag = parsed.get("diagnostics", {})
# Avoid expensive deep copies here; keep adapter boundary lightweight.
return NetworkFrames(..., frames=frames, diagnostics=NetworkDiagnostics(...))
```

**Step 4: Run test to verify it passes**  
Run: `source .venv/bin/activate && PYTHONPATH=src pytest tests/test_rust_adapter.py::test_parse_network_returns_diagnostics_on_degradation -q`  
Expected: PASS.

---

### Task 6: Propagate Diagnostics to Final Report Quality Block

**Parallel:** no  
**Blocked by:** Task 1, Task 5  
**Owned files:** `src/rlcoach/report.py`, `tests/test_report_end_to_end.py`, `tests/test_report_markdown.py`

**Files:**
- Modify: `src/rlcoach/report.py`
- Modify: `tests/test_report_end_to_end.py`
- Modify: `tests/test_report_markdown.py`

**Step 1: Write the failing test**
```python
# tests/test_report_end_to_end.py

def test_report_includes_network_diagnostics_when_degraded():
    report = generate_report(Path("replays/A181B...replay"), adapter_name="rust")
    nd = report["quality"]["parser"].get("network_diagnostics")
    assert nd is not None
    assert nd["status"] in {"ok", "degraded", "unavailable"}
```

**Step 2: Run test to verify it fails**  
Run: `source .venv/bin/activate && PYTHONPATH=src pytest tests/test_report_end_to_end.py::test_report_includes_network_diagnostics_when_degraded -q`  
Expected: FAIL (field missing).

**Step 3: Write minimal implementation**
```python
# src/rlcoach/report.py
quality["parser"]["network_diagnostics"] = _serialize_network_diagnostics(raw_frames)
```

**Step 4: Run test to verify it passes**  
Run: `source .venv/bin/activate && PYTHONPATH=src pytest tests/test_report_end_to_end.py::test_report_includes_network_diagnostics_when_degraded -q`  
Expected: PASS.

---

### Task 7: Add Explicit Regression for Known LTM Failure Replay

**Parallel:** no  
**Blocked by:** Task 6  
**Owned files:** `tests/parser/test_rust_adapter_smoke.py`, `tests/test_report_end_to_end.py`

**Files:**
- Modify: `tests/parser/test_rust_adapter_smoke.py`
- Modify: `tests/test_report_end_to_end.py`

**Step 1: Write the failing test**
```python
# tests/parser/test_rust_adapter_smoke.py

def test_ltm_replay_reports_parse_reason_not_silent_none():
    p = Path("replays/A181B28546BBD8AC71E63793B65BABAE.replay")
    adapter = get_adapter("rust")
    nf = adapter.parse_network(p)
    assert nf is not None
    assert nf.diagnostics is not None
```

**Step 2: Run test to verify it fails**  
Run: `source .venv/bin/activate && PYTHONPATH=src pytest tests/parser/test_rust_adapter_smoke.py::test_ltm_replay_reports_parse_reason_not_silent_none -q`  
Expected: FAIL with `None` path or missing diagnostics.

**Step 3: Write minimal implementation**
- No new code expected if Tasks 2/5/6 were completed correctly; adjust test fixtures/mocks as needed.

**Step 4: Run test to verify it passes**  
Run: `source .venv/bin/activate && PYTHONPATH=src pytest tests/parser/test_rust_adapter_smoke.py::test_ltm_replay_reports_parse_reason_not_silent_none -q`  
Expected: PASS.

---

### Task 8: Mechanics Analyzer Uses Authoritative Component Flags First

**Parallel:** no  
**Blocked by:** Task 4  
**Owned files:** `src/rlcoach/analysis/mechanics.py`, `tests/test_analysis_new_modules.py`

**Files:**
- Modify: `src/rlcoach/analysis/mechanics.py`
- Modify: `tests/test_analysis_new_modules.py`

**Step 1: Write the failing test**
```python
# tests/test_analysis_new_modules.py

def test_mechanics_prefers_authoritative_jump_flags_over_derivative_only():
    frames = build_frames_with_component_flags()
    result = analyze_mechanics(frames)
    assert result["per_player"]["player_0"]["jump_count"] >= 1
```

**Step 2: Run test to verify it fails**  
Run: `source .venv/bin/activate && PYTHONPATH=src pytest tests/test_analysis_new_modules.py::test_mechanics_prefers_authoritative_jump_flags_over_derivative_only -q`  
Expected: FAIL.

**Step 3: Write minimal implementation**
```python
# src/rlcoach/analysis/mechanics.py
if player.is_jumping is True:
    # authoritative jump start path
elif player.is_dodging is True:
    # authoritative dodge/flip path
else:
    # existing derivative fallback
```

**Step 4: Run test to verify it passes**  
Run: `source .venv/bin/activate && PYTHONPATH=src pytest tests/test_analysis_new_modules.py::test_mechanics_prefers_authoritative_jump_flags_over_derivative_only -q`  
Expected: PASS.

---

### Task 8.5: Update Type Hints and Docstrings for New Parser Contracts

**Parallel:** yes  
**Blocked by:** Task 4, Task 5, Task 6, Task 8  
**Owned files:** `src/rlcoach/parser/types.py`, `src/rlcoach/parser/rust_adapter.py`, `src/rlcoach/normalize.py`, `src/rlcoach/report.py`, `src/rlcoach/analysis/mechanics.py`

**Files:**
- Modify: `src/rlcoach/parser/types.py`
- Modify: `src/rlcoach/parser/rust_adapter.py`
- Modify: `src/rlcoach/normalize.py`
- Modify: `src/rlcoach/report.py`
- Modify: `src/rlcoach/analysis/mechanics.py`

**Step 1: Write the failing test**
```python
# tests/test_parser_interface.py

def test_network_diagnostics_contract_is_documented_and_typed():
    from rlcoach.parser.types import NetworkFrames
    assert "diagnostics" in getattr(NetworkFrames, "__dataclass_fields__", {})
```

**Step 2: Run test to verify it fails**  
Run: `source .venv/bin/activate && PYTHONPATH=src pytest tests/test_parser_interface.py::test_network_diagnostics_contract_is_documented_and_typed -q`  
Expected: FAIL until type surface is complete.

**Step 3: Write minimal implementation**
- Update type hints and docstrings to reflect:
  - `NetworkDiagnostics` structure and semantics
  - `PlayerFrame` authoritative component flags
  - report quality parser diagnostics fields
- Ensure function signatures and return annotations are aligned.

**Step 4: Run static checks**  
Run: `source .venv/bin/activate && make lint`  
Expected: PASS.

---

### Task 9: Build Corpus Reliability Harness and Decision Metrics

**Parallel:** yes  
**Blocked by:** Task 6  
**Owned files:** `scripts/parser_corpus_health.py`, `tests/test_benchmarks.py`, `codex/docs/master_status.md`

**Files:**
- Create: `scripts/parser_corpus_health.py`
- Modify: `tests/test_benchmarks.py`
- Modify: `codex/docs/master_status.md`

**Step 1: Write the failing test**
```python
# tests/test_benchmarks.py

def test_parser_corpus_health_output_schema(tmp_path):
    # invoke script in dry mode
    # assert json contains network_success_rate and degraded_count
```

**Step 2: Run test to verify it fails**  
Run: `source .venv/bin/activate && PYTHONPATH=src pytest tests/test_benchmarks.py::test_parser_corpus_health_output_schema -q`  
Expected: FAIL (script missing).

**Step 3: Write minimal implementation**
```python
# scripts/parser_corpus_health.py
# emits json summary:
# {"total":..., "header_success_rate":..., "network_success_rate":..., "degraded_count":..., "top_error_codes":...}
# Require corpus metadata in output (count by playlist/match type/build) so
# the 99.5% target is evaluated on a representative sample, not a narrow subset.
```

**Step 4: Run test to verify it passes**  
Run: `source .venv/bin/activate && PYTHONPATH=src pytest tests/test_benchmarks.py::test_parser_corpus_health_output_schema -q`  
Expected: PASS.

---

### Task 10: Introduce Backend Abstraction Seam (Boxcars Primary)

**Parallel:** no  
**Blocked by:** Task 5  
**Owned files:** `src/rlcoach/parser/interface.py`, `src/rlcoach/parser/rust_adapter.py`, `src/rlcoach/parser/__init__.py`, `tests/test_parser_interface.py`

**Files:**
- Modify: `src/rlcoach/parser/interface.py`
- Modify: `src/rlcoach/parser/rust_adapter.py`
- Modify: `src/rlcoach/parser/__init__.py`
- Modify: `tests/test_parser_interface.py`

**Step 1: Write the failing test**
```python
# tests/test_parser_interface.py

def test_rust_adapter_backend_chain_default_boxcars():
    adapter = get_adapter("rust")
    assert getattr(adapter, "backend_chain", ["boxcars"])[0] == "boxcars"
```

**Step 2: Run test to verify it fails**  
Run: `source .venv/bin/activate && PYTHONPATH=src pytest tests/test_parser_interface.py::test_rust_adapter_backend_chain_default_boxcars -q`  
Expected: FAIL.

**Step 3: Write minimal implementation**
```python
# src/rlcoach/parser/rust_adapter.py
class RustAdapter(ParserAdapter):
    def __init__(self, backend_chain: list[str] | None = None):
        self.backend_chain = backend_chain or ["boxcars"]
```

**Step 4: Run test to verify it passes**  
Run: `source .venv/bin/activate && PYTHONPATH=src pytest tests/test_parser_interface.py::test_rust_adapter_backend_chain_default_boxcars -q`  
Expected: PASS.

---

### Task 11: Optional Secondary Backend Spike (Decision Gate)

**Parallel:** no  
**Blocked by:** Task 9, Task 10  
**Owned files:** `codex/Plans/2026-02-10-parser-refactor-update-plan.md`, `codex/logs/2026-02-10-parser-backend-spike.md`, `src/rlcoach/parser/rust_adapter.py`

**Files:**
- Modify: `src/rlcoach/parser/rust_adapter.py`
- Create: `codex/logs/2026-02-10-parser-backend-spike.md`

**Step 1: Write the failing test**
```python
# tests/test_parser_interface.py

def test_rust_adapter_can_report_attempted_backends_in_diagnostics():
    adapter = get_adapter("rust")
    nf = adapter.parse_network(Path("testing_replay.replay"))
    assert nf.diagnostics.attempted_backends
```

**Step 2: Run test to verify it fails**  
Run: `source .venv/bin/activate && PYTHONPATH=src pytest tests/test_parser_interface.py::test_rust_adapter_can_report_attempted_backends_in_diagnostics -q`  
Expected: FAIL.

**Step 3: Write minimal implementation**
- Record attempted backend names in diagnostics even if only `boxcars` is implemented now.
- Add feature flag/env guard for future backend integration (`RLCOACH_PARSER_BACKEND_CHAIN`).

**Step 4: Run test to verify it passes**  
Run: `source .venv/bin/activate && PYTHONPATH=src pytest tests/test_parser_interface.py::test_rust_adapter_can_report_attempted_backends_in_diagnostics -q`  
Expected: PASS.

**Decision Gate (go/no-go for non-boxcars backend):**
- **Go** if after Tasks 1-10 network success rate < 99.5% or any ranked-standard replay class has >1% degradation.
- **No-go** if thresholds are met; keep fallback seam only.

---

### Task 12: Full Verification Sweep and Documentation Update

**Parallel:** no  
**Blocked by:** Task 1-11, Task 8.5  
**Owned files:** `codex/docs/network-frames-integration-issue.md`, `codex/docs/network-frames-integration-issue-report.md`, `README.md`, `tests/*`

**Files:**
- Modify: `codex/docs/network-frames-integration-issue.md`
- Modify: `codex/docs/network-frames-integration-issue-report.md`
- Modify: `README.md`

**Step 1: Run targeted parser + downstream tests**  
Run:
```bash
source .venv/bin/activate && PYTHONPATH=src pytest -q \
  tests/test_rust_adapter.py \
  tests/parser/test_rust_adapter_smoke.py \
  tests/parser/test_rust_pad_registry.py \
  tests/test_parser_interface.py \
  tests/test_normalize.py \
  tests/test_events.py \
  tests/test_analysis_new_modules.py \
  tests/test_report_end_to_end.py \
  tests/test_schema_validation.py
```
Expected: all pass.

**Step 2: Run corpus health harness**  
Run: `source .venv/bin/activate && PYTHONPATH=src python scripts/parser_corpus_health.py --roots replays,Replay_files --json`  
Expected: JSON summary with success rates and degraded replay IDs.

**Step 3: Update docs with final behavior**
- Document that rust adapter is authoritative-first with explicit degradation diagnostics.
- Document decision gate outcome for secondary backend.

---

## Rollout Strategy

1. Land diagnostics contract first (non-breaking schema extension).
2. Land Rust diagnostics API + Python adapter consumption.
3. Run performance checkpoint; mitigate if regressions exceed agreed threshold.
4. Land component-state extraction + mechanics preference.
5. Run corpus health harness and evaluate threshold.
6. Decide on secondary backend implementation only if thresholds fail.

---

## Risks and Mitigations

- Risk: schema drift breaks consumers.  
Mitigation: additive-only schema changes, explicit defaults, compatibility tests.

- Risk: new component flags unstable across replay versions.  
Mitigation: optional nullable flags; keep derivative fallback in mechanics.

- Risk: diagnostics flood warnings and reduce usability.  
Mitigation: normalized `error_code` taxonomy + capped error detail string length.

- Risk: diagnostics/provenance payload increases parse latency or memory.  
Mitigation: baseline + checkpoints, payload minimization, and documented perf budget gates before rollout completion.

- Risk: backend fallback adds complexity prematurely.  
Mitigation: decision gate with objective thresholds.

---

## Execution Options

1. Execute sequentially in this session.
2. Execute in a new worktree using `using-git-worktrees`.
3. Split tasks marked `Parallel: yes` into separate tickets/worktrees using `ticket-builder`.
