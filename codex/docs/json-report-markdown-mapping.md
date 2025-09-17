# JSON Report -> Markdown Dossier Mapping

This matrix maps every field in `schemas/replay_report.schema.json` to the planned Markdown dossier layout so we can guarantee nothing from the JSON payload is dropped. Patterns ending in `[]` represent repeated rows rendered as tables or lists. Derived statistics (per-minute rates, opponent deltas, success percentages) are computed inside the composer using the mapped source fields.

## Field Coverage Matrix

### Front Matter
| JSON Path Pattern | Markdown Placement | Rendering Notes |
| --- | --- | --- |
| `replay_id`, `source_file`, `generated_at_utc` | Provenance block | Provide replay identifier, absolute path, and generation timestamp. |
| `schema_version` | Provenance block | Listed with schema recap and appendix cross-link. |
| `metadata.engine_build` | Metadata summary | Labelled as game build. |
| `metadata.playlist`, `metadata.map`, `metadata.team_size`, `metadata.overtime` | Match overview table | Combined with match duration and frame rate. |
| `metadata.mutators` | Match overview table | Rendered as key-value list; empty map -> "None". |
| `metadata.match_guid` | Metadata summary | Shown under provenance for cross-system tracing. |
| `metadata.duration_seconds`, `metadata.recorded_frame_hz`, `metadata.total_frames` | Metadata summary | Used to compute per-minute normalizations and tick rate. |
| `metadata.coordinate_reference.*` | Field reference callout | Included in appendix and referenced when describing heatmaps. |
| `quality.parser.*` | Parser status block | Show parser name/version, network/header flags, CRC state. |
| `quality.warnings[]` | Quality warnings list | Highlighted near top with severity tags. |
| `players[].player_id`, `players[].display_name`, `players[].team`, `players[].platform_ids`, `players[].camera`, `players[].loadout` | Roster overview | Displayed as roster table in front matter and reused in player sections for camera/loadout details. |

### Team Metrics
| JSON Path Pattern | Markdown Placement | Rendering Notes |
| --- | --- | --- |
| `teams.blue.*`, `teams.orange.*` | Scoreboard header | Team names, scores, roster membership. |
| `analysis.per_team.blue.fundamentals.*`, `analysis.per_team.orange.fundamentals.*` | Fundamentals table | Include goals, assists, shots, saves, demos, score, shooting %. |
| `analysis.per_team.*.boost.*` | Boost economy table | Present absolute values plus per-minute rates and opponent deltas. |
| `analysis.per_team.*.movement.*` | Movement bands table | Convert seconds to minutes/% of match, annotate supersonic share. |
| `analysis.per_team.*.positioning.*` | Positioning table | Time by halves/thirds, behind/ahead %, spacing metrics. |
| `analysis.per_team.*.passing.*` | Possession & passing table | Compute pass success %, turnovers per minute. |
| `analysis.per_team.*.challenges.*` | Challenges table | Report win/loss counts, win rate, depth, risk index. |
| `analysis.per_team.*.kickoffs.*` | Kickoff outcomes table | Include counts, goals for/against, approach type distribution, avg time to first touch. |
| `analysis.coaching_insights[]` | Team insights callout | Render as bullet insights with severity tags inside Team Metrics section. |

### Player Metrics
| JSON Path Pattern | Markdown Placement | Rendering Notes |
| --- | --- | --- |
| `analysis.per_player[].player_id` + roster lookup | Player section heading | Use display name (roster) and team color. |
| `analysis.per_player[].fundamentals.*` | Fundamentals subsection | Add shooting %, goal participation (derived). |
| `analysis.per_player[].boost.*` | Boost subsection | Show per-minute rates, pad splits, stolen boost, zero/100 time. |
| `analysis.per_player[].movement.*` | Movement & speed subsection | Convert to min/% of match, highlight aerial count/time. |
| `analysis.per_player[].positioning.*` | Positioning subsection | Halves/thirds occupancy, spacing, rotation role percentages. |
| `analysis.per_player[].passing.*` | Possession & passing subsection | Calculate completion %, give-and-go rate, possession per minute. |
| `analysis.per_player[].challenges.*` | Challenges subsection | Include win rate, first-to-ball %, depth, risk index. |
| `analysis.per_player[].kickoffs.*` | Kickoff subsection | Present kickoff role distribution, approaches, time to touch. |
| `analysis.per_player[].rotation_compliance.*` | Rotation compliance subsection | Numeric score plus flag list; flags rendered as bullet list. |
| `analysis.per_player[].insights[]` | Player insights callout | Badges with severity labels. |
| `players[].camera`, `players[].loadout` | Player appendix | Render compact tables when data present. |

### Event Timeline
| JSON Path Pattern | Markdown Placement | Rendering Notes |
| --- | --- | --- |
| `events.timeline[]` | Chronological timeline | Render table containing timestamp, frame, event type, primary actor, summary payload. |
| `events.goals[]` | Goal log | Nested table under timeline with scorer, assister, frame, location. |
| `events.demos[]` | Demo log | Table with attacker/victim, time, location. |
| `events.kickoffs[]` | Kickoff log | Include phase, player roles, outcome, time-to-first-touch. |
| `events.boost_pickups[]` | Boost pickup log | Optionally toggleable subtable showing pad, player, stolen flag. |
| `events.touches[]` | Touch stream | Subtable with timestamp, player, result, location, ball speed. |
| `events.challenges[]` | Challenge log | Table summarizing contest outcome, depths, players involved. |

### Heatmap Summaries
| JSON Path Pattern | Markdown Placement | Rendering Notes |
| --- | --- | --- |
| `analysis.per_player[].heatmaps.position_occupancy_grid.*` | Position heatmap | Render numeric grid table, compute top occupancy cells and offensive/defensive share. |
| `analysis.per_player[].heatmaps.touch_density_grid.*` | Touch heatmap | Similar grid plus highlight hotspots. |
| `analysis.per_player[].heatmaps.boost_pickup_grid.*` | Boost pickup heatmap | Grid plus dominant pad zones. |
| `analysis.per_player[].heatmaps.boost_usage_grid` | Usage heatmap | If non-null, rendered as grid; if null, documented as unavailable in appendix. |

### Appendices
| JSON Path Pattern | Markdown Placement | Rendering Notes |
| --- | --- | --- |
| `schema_version` (repeat), `metadata.coordinate_reference.*` | Schema & field appendix | Restate schema version with link to JSON schema and field extents. |
| Full JSON payload | Raw JSON appendix | Provide collapsible fenced block for deterministic diffing. |
| Derived stat sources | Computation appendix | Table listing derived metrics with source fields and formulas. |
| `quality.warnings[]` (repeat) | Quality appendix | Copy warnings to ensure they survive trimming. |

## Missing Metrics & Follow-Ups
- Kickoff cheat distance, kickoff boost expenditure breakdown, and kickoff positional deltas are not present in `analysis.kickoffs`; needs analyzer enhancement.
- Challenge depth distributions (histograms), momentum swing tracking, and peak boost usage metrics are absent; follow-up analyzers required.
- Lobby average baselines are not computable from a single replay JSON; composer will expose placeholders until comparative datasets exist.
- Heatmaps currently omit `boost_usage_grid` (null in samples); implement analyzer support before enabling in Markdown.

## Derived Metric Notes
- Team and player sections will compute per-minute/per-five-minute rates using `metadata.duration_seconds` and kickoff counts.
- Opponent differentials are calculated within the composer by subtracting orange metrics from blue metrics (and vice versa) for shared fields.
- Pass, challenge, and kickoff win rates are derived inside the Markdown composer to keep JSON schema stable.

This mapping will be kept in sync with schema updates so the Markdown report remains lossless relative to the JSON source.
