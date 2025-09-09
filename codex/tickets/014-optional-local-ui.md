# Execution Prompt — Ticket 014: Optional Local UI (Offline Viewer)

You are a coding agent in Codex CLI. Plan–execute–verify until all acceptance checks pass.

## Critical Rules (repeat)
- Persist; read first; small, focused diffs; offline-only.

## Environment & Tools
- Agent context: Codex CLI
- Tools: plan, shell, apply_patch
- Approvals: never; Network: enabled; Filesystem: full


## Goal
- Provide a minimal offline UI (CLI or Tauri/Electron stub) to open a local replay, run analysis, and render key tables/plots from the generated JSON (no network).

## Scope
- Add `ui/` with a simple CLI viewer first: `python -m rlcoach.ui view out/<file>.json` pretty-prints teams, players, and key metrics.
- (Optional) Scaffold Tauri/Electron project with local file open and JSON render of a subset (timeline + per-player summary).
- Document how to run locally; no external calls.

## Out of Scope
- Cloud services; complex charts; live telemetry.

## Primary Files to Modify or Add
- `src/rlcoach/ui.py`
- `docs/ui.md`
- (Optional) `ui/tauri/*` or `ui/electron/*`

## Implementation Plan
1) Implement CLI viewer to render JSON sections deterministically.
2) Add docs with screenshots (if feasible) and commands.
3) (Optional) Scaffold desktop UI project structure without heavy dependencies committed.

## Acceptance Checks (must pass)
- `python -m rlcoach.ui view examples/replay_report.success.json` prints readable summaries.
- No network usage; file open dialogs restricted to local filesystem.

## Validation Steps
- Manual: view provided example JSON; inspect output.

## Deliverables
- Files: UI CLI, docs, optional scaffold
- Log: `./codex/logs/014.md`

## Safety & Compliance
- Offline-only; no large binaries committed; deterministic renders.

---
