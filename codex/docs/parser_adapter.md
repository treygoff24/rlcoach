# Parser Adapter Contract (As-Built)

This document is the source of truth for what the Rust replay parser emits and how
the Python pipeline consumes it. It describes the contract as it actually exists in
the code, not as it was originally sketched. Where the shipped design diverges from
the original implementation plan, that divergence is called out explicitly at the
end of this document.

Grounding files:

- `parsers/rlreplay_rust/src/lib.rs` — the pyo3 module (`rlreplay_rust`) and all parsing
- `parsers/rlreplay_rust/src/pads.rs` — boost-pad event detection and the `PadEvent` shape
- `src/rlcoach/parser/types.py` — the typed Python dataclasses the rest of the pipeline uses
- `src/rlcoach/parser/rust_adapter.py` — the adapter that turns Rust dicts into those dataclasses
- `src/rlcoach/normalize.py` — how raw parser dicts become normalized `Frame` objects
- `src/rlcoach/report.py` — how header, frames, diagnostics, and metadata reach the report

## Module surface

The compiled extension `rlreplay_rust` exposes these functions plus a `RUST_CORE = True`
health flag:

- `parse_header(path) -> dict` — header-only parse (`never_parse_network_data`).
- `iter_frames(path) -> list[dict]` — network frames only; returns the frame list of
  `run_iter_frames` and drops the player-metadata half.
- `parse_network_with_diagnostics(path) -> dict` — the rich entry point used in production.
  Returns `{"frames": [...], "player_metadata": {...}, "diagnostics": {...}}`.
- `header_property_keys(path) -> list[str]` and `header_property(path, key) -> Optional[obj]` —
  raw header introspection helpers.
- `net_frame_count(path) -> int` — count of network frames.
- `debug_first_frames(path, max_frames) -> list` — a debug harness that dumps raw actor
  mappings, attribute reprs, and boost-actor events for the first N frames. Not part of the
  production path; used for investigation only.

The adapter calls `parse_header` for headers and prefers `parse_network_with_diagnostics`
for network data (falling back to `iter_frames` only if the diagnostics function is missing).

## Header fields

`parse_header` parses with `never_parse_network_data` and returns a dict with these keys.
`RustAdapter._header_from_rust_dict` maps them onto the `Header` dataclass.

| Key | Type | Notes |
| --- | --- | --- |
| `playlist_id` | str | Defaults to `"unknown"`. From `PlaylistID` (string or int). When absent, inferred from `MatchType` + `TeamSize`: `Online` → `inferred_<team_size>`, `Tournament` → `tournament`, `Private`/`Offline` → `private`. |
| `map_name` | str | From `MapName`, defaults to `"unknown"`. |
| `team_size` | int | From `TeamSize`, then overridden by the max per-team count of `PlayerStats` when players are present. |
| `team0_score` / `team1_score` | int | From `Team0Score` / `Team1Score`. |
| `match_length` | float | Seconds, computed as `NumFrames / 30.0`. |
| `match_guid` | str \| None | From `MatchGUID` or `MatchGuid`. |
| `overtime` | bool \| None | From `bOverTime` / `Overtime` / `IsOvertime`. `None` when the property is absent (preserved through to the dataclass — not coerced to `False`). |
| `mutators` | dict | Flattened fields of the `MutatorSettings` / `Mutators` struct. A non-struct value is wrapped as `{"raw": ...}`. |
| `engine_build` | str | Only present when `BuildVersion` exists. It is captured as a `build_version:<value>` warning and re-surfaced under this key. |
| `players` | list | See below. |
| `goals` | list | `{frame, player_name, player_team}` per header `Goals` entry. Header-derived only. |
| `highlights` | list | `{frame, ball_name, car_name}` per header `HighLights` entry. |
| `quality_warnings` | list | Always starts with `"parsed_with_rust_core"`. May include `build_version:<v>`, `boxcars_no_playerstats`, `boxcars_parse_error: <msg>`, and `rust_core_suspect_format`. |

### Players in the header

When `PlayerStats` is present, each player is `{name, team, stats}`, where `stats` is the
full per-player property struct (everything except `Name`/`Team`). The adapter mines `stats`
for richer identity data:

- `platform_id` / `platform_ids` — from `Platform`, `PlayerID`/`UniqueId` (Steam UID,
  EpicAccountId, PSN NpId, Remote), and the older `OnlineID` fallback.
- `camera_settings` — from a `CameraSettings` struct if present in header stats.
- `loadout` — from `Loadout` / `PlayerLoadout` / `LoadoutPaint(s)` if present in header stats.
- `score` — from `Score`.

Header camera/loadout are usually empty; the authoritative camera and loadout come from the
network stream (see `player_metadata`). When `PlayerStats` is missing entirely, players are
emitted as bare `{name, team}` dicts and `boxcars_no_playerstats` is added to warnings.

If the boxcars header parse fails outright, the parser emits two placeholder players
(`Unknown Player 1`/`2`), `team_size = 1`, and a `boxcars_parse_error` warning (plus
`rust_core_suspect_format` when the bytes do not look like a replay header).

## Per-frame fields

Both `iter_frames` and the `frames` half of `parse_network_with_diagnostics` produce a list
of frame dicts (network parsed with `must_parse_network_data`). Each frame:

- `timestamp` — float seconds, the network frame time.
- `ball` — `{position{x,y,z}, velocity{x,y,z}, angular_velocity{x,y,z}}`.
- `players` — list of player dicts (below), ordered by header player index.
- `_parser_meta` — `{classification_source}`: `"object_name"`, `"component_owner_chain"`, or
  `"fallback_unclassified"`. The frame-level value degrades to the weakest source used by any
  emitted actor in that frame.
- `boost_pad_events`, `parser_touch_events`, `parser_demo_events`, `parser_tickmarks`,
  `parser_kickoff_markers` — the authoritative per-frame event streams (below).

### Player state per frame

| Field | Type | Notes |
| --- | --- | --- |
| `player_id` | str | `"player_<index>"`, where index is the header player index this actor resolved to. |
| `team` | int | `0` or `1`. Prefers decoded `TeamPaint`; otherwise inferred from the sign of `y` (`y > 0` → orange/1). |
| `position` | `{x,y,z}` | Car position. Default `(0, 0, 17)` if not yet observed. |
| `velocity` | `{x,y,z}` | Linear velocity. |
| `rotation` | dict | When a `RigidBody` quaternion is available: `{pitch, yaw, roll, quaternion{x,y,z,w}}` with euler angles derived from the quaternion (aerospace ZYX). Otherwise a velocity-direction fallback `{pitch, yaw, roll}` with **no** `quaternion` key. |
| `boost_amount` | int | `0..100`, scaled from the replicated `0..255` value. Default `33` when unobserved. |
| `is_supersonic` | bool | `speed > 2300`. |
| `is_on_ground` | bool | `z <= 18.0`. |
| `is_demolished` | bool | From decoded demolition state. |
| `is_jumping` | bool (optional key) | Authoritative jump-component active state. Key is present only when the parser observed a jump component for this actor; absent otherwise. |
| `is_dodging` | bool (optional key) | Same semantics for the dodge component. |
| `is_double_jumping` | bool (optional key) | Same semantics for the double-jump component. |

The three component flags carry **True / False / None** semantics end-to-end. The Rust side
emits the key only when it has authoritative state to report; when the key is absent, the
Python `PlayerFrame` field defaults to `None`, meaning "unknown / not observed", which is
distinct from an explicit `False`. Normalization copies these through verbatim via
`_apply_component_state_flags`, so an analyzer can tell "parser said the player was not
jumping" apart from "parser had nothing to say."

### Authoritative per-frame event streams

These are sparse — most frames carry empty lists. Each event is attached to the `Frame` where
it occurs, so an event's position in the timeline is the frame it lives on. All four
`parser_*` streams stamp `source = "parser"`.

**`boost_pad_events`** (shape from `PadEvent` in `pads.rs`):

- `pad_id` (int), `is_big` (bool)
- `pad_side` — `"blue"`, `"orange"`, or `"mid"`
- `arena` — canonical arena slug (e.g. `"soccar"`) or `"unknown"`
- `arena_supported` (bool) — when `false`, treat `pad_id` / `pad_side` / `is_big` as unreliable
- `status` — `"COLLECTED"` or `"RESPAWNED"`
- `object_name` (str), `raw_state` (int), `timestamp` (float), `position{x,y,z}`
- Optional: `instigator_actor_id`, `actor_id` (resolved owner), `player_index`, `player_id`,
  `player_team`, `snap_distance`, `snap_error_uu`

**`parser_touch_events`**: `{timestamp, player_id, team, frame_index, source}`. Proximity-based
detection (car within `200` uu of the ball) with debounce (`0.2` s between touches, plus a
location epsilon of `120` uu).

**`parser_demo_events`**: `{timestamp, victim_id, frame_index, source}` plus optional
`attacker_id`, `victim_team`, `attacker_team`. Emitted from attribute-attributed demolitions
(`Demolish`, `DemolishExtended`, `DemolishFx`) and, as a backstop, from the rising edge of an
actor's demolished state (deduplicated against the attributed events in the same frame).

**`parser_tickmarks`**: `{timestamp, kind, frame_index, payload{description, frame}, source}`,
keyed off `replay.tick_marks` and attached to the frame matching each tickmark's frame index.

**`parser_kickoff_markers`**: `{timestamp, phase, frame_index, source}`. `phase` is `"INITIAL"`
or `"OT"` (inferred from header overtime and match length). Emitted on the rising edge of the
ball being at center (within `120` uu of `(0, 0, 93.15)`) and stationary (speed `<= 60`).

## player_metadata

`parse_network_with_diagnostics` returns a top-level `player_metadata` map alongside `frames`.
This is **new** as-built surface (it does not exist in `iter_frames`). It is keyed by header
player index and shaped:

```
{
  <header_index>: {
    "name": <str | None>,                 # from header PlayerStats order
    "camera": {                           # or null
      "fov", "height", "angle", "distance",
      "stiffness", "swivel_speed", "transition_speed"
    },
    "loadout": {                          # or null
      "body", "decal", "wheels", "rocket_trail", "antenna", "topper",
      # present-only optionals:
      "engine_audio", "trail", "goal_explosion", "banner", "product_id"
    }
  }
}
```

Camera values come from the `CamSettings` network attribute, which arrives either directly on
the PRI (`TAGame.PRI_TA:CameraSettings`) or on a `CameraSettingsActor` that is linked to its
PRI via an `ActiveActor` update (`CameraSettingsActor_TA:PRI`); settings seen before the link
are buffered and flushed once the link appears. The boxcars `swivel`/`transition` fields are
surfaced under the more descriptive `swivel_speed`/`transition_speed`, and a missing
`transition` is emitted as `0.0` rather than dropped.

Loadout values come from the `Loadout` attribute (replicated directly on the PRI) or from
`TeamLoadout`, in which case the player's own team loadout is selected (team `1` → orange,
otherwise blue). The six mandatory cosmetic slots are always present; the remaining slots are
emitted only when the stream carried a value.

Per-PRI camera/loadout buffers are resolved to header player indices at the end of the parse
using the PRI-name → index bindings, which accumulate across the whole replay. As a result a
player's profile survives actor deletion and respawn even though the underlying actor ids churn.

### How metadata threads through Python

`NetworkFrames.player_metadata` (`src/rlcoach/parser/types.py`) carries this map. The adapter's
`_normalize_player_metadata` coerces keys to `int` and drops malformed entries
(`rust_adapter.py`). In `report.py`, `network_player_metadata = raw_frames.player_metadata` is
looked up per player by header index; the report's per-player `camera` and `loadout` prefer the
network-decoded values and fall back to the (usually empty) header values:

```
camera_payload  = player_meta.get("camera")  or player_info.camera_settings or {}
loadout_payload = player_meta.get("loadout") or player_info.loadout          or {}
```

## Diagnostics

`parse_network_with_diagnostics` returns a `diagnostics` dict that the adapter maps onto the
`NetworkDiagnostics` dataclass:

- `status` — `"ok"` on success; `"degraded"` when the primary network parse failed and the
  parser fell back. The Python layer can also produce `"unavailable"` (e.g. a non-boxcars
  backend, or no backend run at all).
- `error_code` — `None` on success. On a degraded parse, one of:
  `replay_io_error`, `boxcars_unknown_attribute_network_error`, or `boxcars_network_error`
  (classified from the error message by `map_network_error_code`).
- `error_detail` — `None` on success, else the error message (with any fallback failure detail
  appended).
- `frames_emitted` — number of frames returned (placeholder frames in the degraded path).
- `attempted_backends` — `["boxcars"]` from Rust; the adapter prepends any chain backends it
  attempted.

### Parser scorecard

Separately, `report.py::_build_parser_scorecard` computes a quality scorecard from the frames
and diagnostics: `usable_network_parse` (requires `status == "ok"`, non-empty player-frame
coverage `>= 0.5`, and player-identity coverage `>= 0.5`), plus the supporting counts
(`non_empty_player_frame_coverage`, `player_identity_coverage`, `network_frame_count`,
`non_empty_player_frames`, `players_with_identity`, `expected_players`). It lands under
`quality.parser.scorecard` in the report.

## Degraded, null-adapter, and header-only behavior

**Degraded network parse.** If `must_parse_network_data` fails, `parse_network_with_diagnostics`
retries with `ignore_network_data_on_error` and emits one placeholder frame per network frame:
ball at rest `(0, 0, 93.15)`, empty `players`, and empty `boost_pad_events` /
`parser_touch_events` / `parser_demo_events` / `parser_tickmarks` / `parser_kickoff_markers`.
`player_metadata` is empty in this path. `status = "degraded"` with the classified `error_code`.

**Null adapter / Rust unavailable.** If the compiled `rlreplay_rust` module cannot be imported,
`RustAdapter.supports_network_parsing` is `False` and `parse_network` returns `None`. The header
path degrades to an ingest-validated minimal header with two `Unknown Player` entries,
`team_size = 1`, and warnings `rust_core_unavailable_fallback_header_only` plus
`network_data_unparsed_fallback_header_only`. The report builder also falls back to the `null`
adapter if header parsing raises.

**Header-only.** When `generate_report(..., header_only=True)` is requested (or no network frames
are available), `build_timeline` returns a single minimal frame (ball at spawn, no players, all
event lists empty). Header-derived goals are suppressed in this mode so header data is never
presented as if it came from real frames. Diagnostics report `status = "unavailable"` with
`error_code = "network_data_unavailable"` when network parsing was supported but produced nothing.

**Backend chain.** `RustAdapter` honors `RLCOACH_PARSER_BACKEND_CHAIN` (comma-separated). Only
`boxcars` is implemented; any other backend yields a `*_backend_unavailable` `unavailable`
diagnostic and is skipped, with the boxcars attempt still made if present in the chain.

## Contract divergence: the original `AuthoritativeEvents` design was not built

The original implementation plan (Task 0 of
`docs/plans/2026-04-07-rlcoach-full-parser-analysis-vision.md`) specified an
`AuthoritativeEvents` dataclass hung off `NetworkFrames` (with `touches` / `demos` / `kickoffs` /
`tickmarks` lists) and a `Frame.authoritative_touches` field. **Those symbols do not exist in the
shipped code, and there is no `NetworkFrames.authoritative_events` field.**

The as-built design instead:

1. Attaches the authoritative event streams directly to each `Frame` as the per-frame
   `boost_pad_events`, `parser_touch_events`, `parser_demo_events`, `parser_tickmarks`, and
   `parser_kickoff_markers` lists, and
2. Carries per-player profile data as a top-level `NetworkFrames.player_metadata` map rather than
   inside an events container.

Rationale: an event belongs on the frame where it occurs, which keeps the event's timestamp and
frame index co-located with the ball/player state at that instant. This is also exactly what the
downstream consumers want — `normalize.py` reads the `parser_*` lists frame by frame (converting
and clock-shifting them per frame), and the event detectors prefer those per-frame authoritative
streams before falling back to inference. A separate, replay-global `AuthoritativeEvents` bag
would have forced normalization and the detectors to re-associate each event with its frame, for
no benefit. This document supersedes the Task 0 contract; where the two disagree, the as-built
shape described here is authoritative.
