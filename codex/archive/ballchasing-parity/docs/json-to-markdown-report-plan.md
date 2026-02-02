# JSON to Markdown Report Plan

## Objectives
- Transform the schema-validated JSON replay report into a Markdown dossier that mirrors or exceeds Ballchasing’s metric catalogue while extending into every instrumented datapoint captured by the RLCoach pipeline.
- Produce deterministic, shareable documents that enumerate the full stat surface without editorial coaching conclusions, so both humans and GPT-5-class tools can consume the same structured narrative.
- Preserve local-only processing; the Markdown composer must run inside the CLI or CI without external services.

## Inputs & References
- Primary data source: output of `rlcoach analyze` validated against `schemas/replay_report.schema.json`.
- Supplemental specs: architecture plan (`codex/Plans/rlcoach_implementation_plan.md`), analyzer contracts (`src/rlcoach/analysis/`), event detectors (`src/rlcoach/events.py`), and the existing CLI viewer (`src/rlcoach/ui.py`).
- Competitive baseline: Ballchasing stat taxonomy (fundamentals, boost, movement, positioning, role occupancy) plus the extended metrics from our plan (kickoff breakdowns, challenges, possession, heatmaps, rotation compliance).

## Output Structure (Markdown)
1. **Front Matter** – replay metadata, file provenance, engine/build identifiers, frame rate, quality warnings, and table of contents optimized for downstream parsing.
2. **Team Metrics** – comprehensive tables for fundamentals, boost economy, movement bands, positioning (halves/thirds/ahead-behind ball), kickoff outcomes, possession, challenges; include raw counts, per-minute normalization, and opponent deltas.
3. **Player Metrics** – dedicated subsection per player listing every metric bucket (fundamentals, boost, movement, positioning, rotation compliance, possession/passing, challenges, kickoffs, heatmap summaries). Present data both as tables and machine-friendly key-value blocks for GPT ingestion.
4. **Event Timeline** – chronological log of goals, demos, kickoffs, touches, challenges, boost pickups with timestamps, frames, coordinates, and involved entities.
5. **Heatmap Summaries** – numeric grids and derived statistics (top occupancy cells, percentage on offensive/defensive halves, boost pad hotspots) exported in Markdown tables.
6. **Appendices** – raw JSON mappings, schema version recap, and any ancillary derived stats not easily surfaced in the main sections.

## Metric Coverage Roadmap
- Map Ballchasing stats to existing analyzers: goals, assists, shots, saves, shooting %, score, demo counts, boost usage (BPM/BCPM), boost collected/stolen, pad pickups, time at 0/100, wasted/overfill, speed bands, ground/air/wall/motion states, behind-ball %, thirds occupancy, distance metrics.
- Extend analyzers where gaps exist: wall/ceiling time, corner occupation, time most back/forward, kickoff cheat distance, possession turnovers, pass success %, challenge depth distributions, momentum swings, peak boost usage, aerial/flip counts.
- Integrate RLCoach-only metrics: rotation compliance score, challenge risk index, possession time, give-and-go counts, kickoff role detection, timeline annotations, heatmap occupancy matrices.
- Provide both absolute values and normalized rates (per minute, per 5 minutes, per kickoff) alongside lobby averages for context.

## Implementation Steps
1. **Schema Mapping** – build a field-to-section matrix to guarantee every JSON leaf is represented; document any missing metrics as analyzer follow-ups.
2. **Composer Design** – implement `report_markdown.py` to load JSON and render Markdown using deterministic templates, structuring content for human skimming and GPT token-friendly parsing (consistent headings, table formats, key-value blocks).
3. **Analyzer Enhancements** – add missing stats and tests in the relevant `analysis` modules; update schema and fixtures accordingly.
4. **Normalization Helpers** – calculate derived rates, opponent differentials, and lobby averages inside the composer, keeping transformations transparent.
5. **Heatmap Presentation** – convert grid data into Markdown tables and summarize notable zones (top 3 cells, percentage coverage).
6. **CLI Integration** – add a CLI entry point (e.g., `rlcoach report-md`) that writes both JSON and Markdown outputs atomically.
7. **Documentation** – update `AGENTS.md` and README with usage instructions and examples of the Markdown output.

## Validation & QA
- Unit tests for composer sections to ensure all required headings, tables, and key-value blocks appear for golden fixtures (full replay and header-only).
- Regression tests verifying deterministic Markdown output; diff results in CI to catch accidental formatting drift.
- Cross-check metrics against Ballchasing exports to confirm parity and highlight expanded coverage.

## Open Questions
- How to best encode large tables for GPT consumption without exhausting context—multiple smaller tables or collapsible sections?
- Do we include optional CSV/JSON sidecars for easy ingestion by downstream analytics pipelines?
- Should we expose configuration flags to toggle verbose sections (e.g., full event log) for users who want slimmer reports?

  python -m rlcoach.cli report-md path/to/replay.replay --out out --pretty
