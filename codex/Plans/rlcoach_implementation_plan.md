Plan (concise)
	•	Map the Rocket League .replay structure and available signals (header vs network frames) and note sampling limits.
	•	Propose an all-local architecture: ingest/validate → parse/normalize → analyze (modular) → JSON report generator → (optional) offline UI.
	•	Define actionable metrics for coaching: fundamentals, boost economy, positioning/rotations, challenges/50s, possession/passing, kickoffs, event timeline.
	•	Specify robust error handling (header-only fallback; corrupted/network-incompatible replays) and the required error JSON.
	•	Deliver an explicit JSON Schema and illustrative success/error payloads.
	•	Validate each section against requirements and self-correct where needed.

⸻

1) Architecture Overview

A. File Ingestion & Validation
	•	Accepts *.replay paths; computes file hash; checks size bounds; opens with safe, buffered reader.
	•	Integrity gates: CRC check (header), version parsing, and optional full-network parse gate.
	•	Degradation policy: If network data fails (post-patch drift), continue with header-only stats and emit a quality warning in the JSON. Boxcars (widely used RL parser) explicitly supports “header-only” vs “parse network frames” and describes ignoring network-data errors so header data is still returned.  ￼

B. Parser Layer (local-only)
	•	Pluggable adapters (e.g., a Rust adapter akin to boxcars/rrrocket semantics or a Haskell adapter akin to rattletrap), compiled into the app. No cloud.
	•	Extracts:
	•	Header: playlist, map, team sizes, team scores, goal tickmarks/frames, player identities, camera/loadout, mutators, etc. (rrrocket shows properties.Team0Score/Team1Score, Goals[ { PlayerName, PlayerTeam, frame } ]).  ￼
	•	Network stream (“network frames”): per-frame actor updates (ball, cars), rigid bodies (pos/rot/vel), demolish/explosion/boost pickup events, tickmarks. These entities (e.g., RigidBody, Demolish, ReplicatedBoost, UpdatedAttribute, TickMark) are documented in the boxcars API.  ￼

C. Normalization Layer
	•	Converts engine-centric data to a normalized timeline:
	•	Determines effective replay sample rate from frames (many replays record ~30 FPS / 30 ticks per second; physics sim is 120 Hz, so replays are a downsample; see “TickMark … at 30 fps” in boxcars docs). We record the measured rate per file and never assume fixed 30 if not present.  ￼ ￼ ￼
	•	Standardize coordinates and field semantics using RLBot’s reference values (origin at center, side walls x=±4096, back walls y=±5120, ceiling z≈2044, boost pad coordinates).  ￼
	•	Unifies player identity (name, platform IDs) and team assignment across frames.

D. Analysis Engine (modular, all local)
	•	Independent analyzers consume the normalized timeline:
	•	Fundamentals (goals, assists, shots, saves, demos, score).
	•	Boost economy (BPM, collections by pad type, “stolen” on opponent half, overfill/waste, time at 0/100, average boost). These categories align with the community’s established metrics (e.g., Ballchasing: BPM, stolen pads, boost ranges).  ￼
	•	Movement & speed (avg speed, time slow/boost/supersonic; ground/air time; powerslides; aerials).  ￼
	•	Positioning/rotations (time in defensive/offensive halves and thirds; behind-/ahead-of-ball; spacing; first/second/third-man occupancy; rotation compliance).
	•	Possession/passing (touch sequences, passes completed/received, turnovers).
	•	Challenges & 50s (first-to-ball, wins/losses/neutral outcomes, contest contexts).
	•	Kickoffs (role detection, time-to-first-touch, boost used, outcome classification).
	•	Event timeline (chronological, frame+time-indexed list of goals/shots/saves/demos/boost pickups/challenges/kickoff events and analyzer “findings”).

E. Report Generator
	•	Emits single JSON per replay with:
	•	Replay metadata and quality/warnings.
	•	Per-team aggregates.
	•	Per-player metrics and coaching insights.
	•	Event/touch/kickoff timelines.
	•	Optional heatmaps as downsampled 2D grid arrays (numeric only, suitable for local visualization).
	•	On failure: the mandated error structure.

F. Optional Local UI
	•	CLI + offline desktop UI (e.g., Rust + Tauri/Electron) that opens local files, renders tables/plots from the emitted JSON, never contacting the network.

G. Performance & Extensibility
	•	Zero-copy parsing where possible; parallel analyzers; chunked frame iteration; schema versioning with schema_version.

Validation — Architecture
	•	Local-only? Yes (no cloud/APIs).
	•	Supports per-replay/per-player? Yes.
	•	Handles unreadable/invalid? Yes (degradation + error JSON).
	•	Grounded in actual replay structure (header vs network frames; tickmarks; actor updates)? Yes, per boxcars/rattletrap/rrrocket docs. If future patches alter network data, header-only fallback still works.  ￼ ￼

⸻

2) Feature Specification (focused on actionable coaching)

Each line names the feature → what it computes → why it matters.

Replay ingestion
	•	Auto-detect playlist/map/teams/duration → contextual baselines for metrics (e.g., 1v1 vs 3v3 expectations).  ￼
	•	Sampling disclosure → record measured frame rate and any gaps (downsampled vs physics 120 Hz).  ￼ ￼

Event breakdown
	•	Goal/assist/shot/save timeline with frame & seconds; “on-target” shots via ball trajectory intersection with goal plane and post-collision states. (Tickmarks help show ramp-up context.)  ￼
	•	Demos (inflicted/taken; who, whom, where, time since last touch). Boxcars surfaces Demolish and Explosion events.  ￼
	•	Boost pickups (pad id/location; big/small; team-half; “stolen” if on opponent half). Uses RLBot boost pad coordinates.  ￼
	•	Touches (player, contact speed, outcome classification: shot/clear/pass/dribble/50/neutral).

Fundamentals summary (per player & team)
	•	Goals, assists, shots, saves, shooting %, demos (inflicted/taken), points (if present in header).  ￼

Boost economy (per player & team)
	•	BPM (boost used/min), BCPM (collected/min), overfill (collected beyond 100), waste (spending above needed for speed bracketing), time at 0/100, avg boost, stolen big/small pad counts, collection efficiency (#pads collected when under threshold). Mirrors community conventions for coaching utility.  ￼

Movement & speed
	•	Avg speed, time slow/boost/supersonic, ground/low-air/high-air time, powerslide count/duration, aerial count/duration (>= jump+boost with Z threshold). (Categories widely used by established tools.)  ￼

Positioning & rotations
	•	Field occupancy by halves/thirds; behind-/ahead-of-ball time%; distance to ball (avg, 10th/90th percentiles); spacing (avg nearest-teammate distance).
	•	Role occupancy (first/second/third-man time%) derived from sorted distances to own backboard/ball and last touch context.
	•	Rotation compliance score (0–100): penalize double-commits, last-man overcommit (ahead-of-ball with no back cover), extended low-boost in forward roles, and “ball-chasing” (high ahead-of-ball time without possession).
	•	Heatmaps (X×Y grids) for positions, touches, and boost pickups.

Possession & passing
	•	Possession time (team in control if last touch by team within τ seconds and ball not immediately traveling toward own half at high speed).
	•	Pass attempts/completions (touch by A → next teammate touch within τ and Δposition favoring opponent net), turnovers (A touch → opponent next touch under pressure), give-and-go sequences.

Challenges & 50/50s
	•	Identify contests (opposing cars within radius/time to ball) and tag outcomes (win/lose/neutral) using post-contact ball speed/trajectory change and next touch ownership.
	•	First to ball rate; challenge depth (where on field); risk index (was last-man? boost state?).

Kickoff module
	•	Classify approach type (standard, cheat, fake, delay) from start positions and early-motion vectors;
	•	Time to first touch, boost used before touch, outcome (first possession, neutral, conceded).
	•	Track cheat coordination (mid/third-man cheat distance & timing).

Coaching insights (auto-generated)
	•	Short, evidence-backed suggestions (“You had 52% ahead-of-ball without possession; shift to back-post rotation on defense”) with direct metric links.

Validation — Features
	•	Per-replay and per-player? Yes across all modules.
	•	Fundamentals and advanced positioning/rotations + event timelines? Yes.
	•	Maximizes actionable coaching? Yes (explicit thresholds, role/rotation compliance, possession/passing, kickoff reviews).
	•	All local; no external/AI APIs? Yes.

⸻

3) Statistical Analysis Report Schema

Contract: The application emits one JSON object per replay.
If unreadable/invalid:

{ "error": "unreadable_replay_file", "details": "<problem description>" }



3.1 JSON Schema (Draft‑07)

{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "RocketLeagueReplayReport",
  "type": "object",
  "oneOf": [
    {
      "required": ["replay_id", "schema_version", "metadata", "quality", "teams", "players", "events", "analysis"]
    },
    {
      "required": ["error", "details"]
    }
  ],
  "properties": {
    "replay_id": { "type": "string", "description": "Deterministic hash of header bytes + match GUID if present" },
    "source_file": { "type": "string", "description": "Absolute or relative path provided by user" },
    "schema_version": { "type": "string", "pattern": "^1\\.0\\.\\d+$" },
    "generated_at_utc": { "type": "string", "format": "date-time" },

    "metadata": {
      "type": "object",
      "required": ["engine_build", "playlist", "map", "team_size", "match_guid", "started_at_utc", "duration_seconds"],
      "properties": {
        "engine_build": { "type": "string", "description": "Replay build/version as parsed from header" },
        "playlist": { "type": "string", "enum": ["DUEL", "DOUBLES", "STANDARD", "CHAOS", "PRIVATE", "EXTRA_MODE", "UNKNOWN"] },
        "map": { "type": "string" },
        "team_size": { "type": "integer", "minimum": 1, "maximum": 4 },
        "overtime": { "type": "boolean" },
        "mutators": { "type": "object", "additionalProperties": { "type": ["string","number","boolean"] } },
        "match_guid": { "type": "string" },
        "started_at_utc": { "type": "string", "format": "date-time" },
        "duration_seconds": { "type": "number" },
        "recorded_frame_hz": { "type": "number", "description": "Measured replay sampling rate (often ~30 Hz). See TickMark 30fps note in boxcars.", "minimum": 1, "maximum": 240 },
        "total_frames": { "type": "integer", "minimum": 1 },
        "coordinate_reference": {
          "type": "object",
          "description": "Field constants used for analysis",
          "properties": {
            "side_wall_x": { "type": "number", "const": 4096 },
            "back_wall_y": { "type": "number", "const": 5120 },
            "ceiling_z": { "type": "number", "const": 2044 }
          },
          "additionalProperties": false
        }
      },
      "additionalProperties": false
    },

    "quality": {
      "type": "object",
      "required": ["parser", "warnings"],
      "properties": {
        "parser": {
          "type": "object",
          "required": ["name", "version", "parsed_header", "parsed_network_data"],
          "properties": {
            "name": { "type": "string", "description": "Internal parser id (e.g., rl-local/boxcars-core)" },
            "version": { "type": "string" },
            "parsed_header": { "type": "boolean" },
            "parsed_network_data": { "type": "boolean" },
            "crc_checked": { "type": "boolean" }
          },
          "additionalProperties": false
        },
        "warnings": {
          "type": "array",
          "items": { "type": "string" },
          "description": "E.g., 'network_data_unparsed_fallback_header_only', 'missing_demolish_stream', 'low_frame_rate_sampling'"
        }
      },
      "additionalProperties": false
    },

    "teams": {
      "type": "object",
      "required": ["blue", "orange"],
      "properties": {
        "blue": { "$ref": "#/definitions/teamBlock" },
        "orange": { "$ref": "#/definitions/teamBlock" }
      },
      "additionalProperties": false
    },

    "players": {
      "type": "array",
      "minItems": 1,
      "items": { "$ref": "#/definitions/playerBlock" }
    },

    "events": {
      "type": "object",
      "required": ["timeline", "goals", "demos", "kickoffs", "boost_pickups", "touches"],
      "properties": {
        "timeline": {
          "type": "array",
          "description": "Chronological significant events",
          "items": { "$ref": "#/definitions/timelineEvent" }
        },
        "goals": { "type": "array", "items": { "$ref": "#/definitions/goalEvent" } },
        "demos": { "type": "array", "items": { "$ref": "#/definitions/demoEvent" } },
        "kickoffs": { "type": "array", "items": { "$ref": "#/definitions/kickoffEvent" } },
        "boost_pickups": { "type": "array", "items": { "$ref": "#/definitions/boostPickupEvent" } },
        "touches": { "type": "array", "items": { "$ref": "#/definitions/touchEvent" } }
      },
      "additionalProperties": false
    },

    "analysis": {
      "type": "object",
      "required": ["per_team", "per_player", "coaching_insights"],
      "properties": {
        "per_team": {
          "type": "object",
          "required": ["blue", "orange"],
          "properties": {
            "blue": { "$ref": "#/definitions/teamAnalysis" },
            "orange": { "$ref": "#/definitions/teamAnalysis" }
          },
          "additionalProperties": false
        },
        "per_player": {
          "type": "object",
          "description": "Keyed by player_id",
          "additionalProperties": { "$ref": "#/definitions/playerAnalysis" }
        },
        "coaching_insights": {
          "type": "array",
          "items": { "$ref": "#/definitions/insight" }
        }
      },
      "additionalProperties": false
    },

    "error": { "type": "string", "enum": ["unreadable_replay_file"] },
    "details": { "type": "string" }
  },

  "definitions": {
    "teamBlock": {
      "type": "object",
      "required": ["name", "score", "players"],
      "properties": {
        "name": { "type": "string", "enum": ["BLUE", "ORANGE"] },
        "score": { "type": "integer", "minimum": 0 },
        "players": { "type": "array", "items": { "type": "string" }, "description": "Array of player_id" }
      },
      "additionalProperties": false
    },

    "playerBlock": {
      "type": "object",
      "required": ["player_id", "display_name", "team", "platform_ids", "camera", "loadout"],
      "properties": {
        "player_id": { "type": "string" },
        "display_name": { "type": "string" },
        "team": { "type": "string", "enum": ["BLUE", "ORANGE"] },
        "platform_ids": {
          "type": "object",
          "properties": {
            "steam": { "type": "string" },
            "epic": { "type": "string" },
            "psn": { "type": "string" },
            "xbox": { "type": "string" }
          },
          "additionalProperties": false
        },
        "camera": {
          "type": "object",
          "properties": {
            "fov": { "type": "number" }, "height": { "type": "number" }, "angle": { "type": "number" },
            "distance": { "type": "number" }, "stiffness": { "type": "number" }, "swivel_speed": { "type": "number" }, "transition_speed": { "type": "number" }
          },
          "additionalProperties": false
        },
        "loadout": { "type": "object", "additionalProperties": true }
      },
      "additionalProperties": false
    },

    "timelineEvent": {
      "type": "object",
      "required": ["t", "type"],
      "properties": {
        "t": { "type": "number", "description": "Seconds from kickoff (including OT)" },
        "frame": { "type": "integer" },
        "type": {
          "type": "string",
          "enum": ["GOAL","SHOT","SAVE","ASSIST","DEMO","BOOST_PICKUP","TOUCH","KICKOFF","CHALLENGE","ROTATION_FLAG","WARNING"]
        },
        "player_id": { "type": "string" },
        "team": { "type": "string", "enum": ["BLUE","ORANGE"] },
        "data": { "type": "object", "additionalProperties": true }
      }
    },

    "goalEvent": {
      "type": "object",
      "required": ["t","frame","scorer","team","shot_speed_kph","assist","distance_m"],
      "properties": {
        "t": { "type": "number" }, "frame": { "type": "integer" },
        "scorer": { "type": "string" }, "team": { "type": "string", "enum":["BLUE","ORANGE"] },
        "assist": { "type": ["string","null"] },
        "shot_speed_kph": { "type": "number" },
        "distance_m": { "type": "number" },
        "on_target": { "type": "boolean" },
        "tickmark_lead_seconds": { "type": "number", "description": "Goal tickmark ramp-up context (see boxcars TickMark semantics)" }
      }
    },

    "demoEvent": {
      "type": "object",
      "required": ["t","victim","attacker","location","team_attacker","team_victim"],
      "properties": {
        "t": { "type": "number" },
        "victim": { "type": "string" }, "attacker": { "type": "string" },
        "team_attacker": { "type": "string", "enum":["BLUE","ORANGE"] },
        "team_victim": { "type": "string", "enum":["BLUE","ORANGE"] },
        "location": { "$ref": "#/definitions/vec3" }
      }
    },

    "kickoffEvent": {
      "type": "object",
      "required": ["phase","t_start","players","outcome"],
      "properties": {
        "phase": { "type": "string", "enum": ["INITIAL","OT"] },
        "t_start": { "type": "number" },
        "players": {
          "type": "array",
          "items": {
            "type": "object",
            "required": ["player_id","role","boost_used","approach_type","time_to_first_touch"],
            "properties": {
              "player_id": { "type": "string" },
              "role": { "type": "string", "enum":["GO","CHEAT","WING","BACK"] },
              "boost_used": { "type": "number" },
              "approach_type": { "type": "string", "enum":["STANDARD","SPEEDFLIP","FAKE","DELAY","UNKNOWN"] },
              "time_to_first_touch": { "type": ["number","null"] }
            }
          }
        },
        "outcome": { "type": "string", "enum": ["FIRST_POSSESSION_BLUE","FIRST_POSSESSION_ORANGE","NEUTRAL","GOAL_AGAINST","GOAL_FOR"] }
      }
    },

    "boostPickupEvent": {
      "type": "object",
      "required": ["t","player_id","pad_type","stolen","pad_id","location"],
      "properties": {
        "t": { "type": "number" },
        "player_id": { "type": "string" },
        "pad_type": { "type": "string", "enum": ["SMALL","BIG"] },
        "stolen": { "type": "boolean", "description": "True if pickup occurred on opponent half (excluding mid boosts)" },
        "pad_id": { "type": "integer" },
        "location": { "$ref": "#/definitions/vec3" }
      }
    },

    "touchEvent": {
      "type": "object",
      "required": ["t","player_id","location","ball_speed_kph","outcome"],
      "properties": {
        "t": { "type": "number" }, "frame": { "type": "integer" },
        "player_id": { "type": "string" },
        "location": { "$ref": "#/definitions/vec3" },
        "ball_speed_kph": { "type": "number" },
        "outcome": { "type": "string", "enum": ["SHOT","CLEAR","PASS","DRIBBLE","50","NEUTRAL"] }
      }
    },

    "teamAnalysis": {
      "type": "object",
      "required": ["fundamentals","boost","movement","positioning","passing","challenges","kickoffs"],
      "properties": {
        "fundamentals": { "$ref": "#/definitions/fundamentals" },
        "boost": { "$ref": "#/definitions/boost" },
        "movement": { "$ref": "#/definitions/movement" },
        "positioning": { "$ref": "#/definitions/positioning" },
        "passing": { "$ref": "#/definitions/passing" },
        "challenges": { "$ref": "#/definitions/challenges" },
        "kickoffs": { "$ref": "#/definitions/kickoffs" }
      }
    },

    "playerAnalysis": {
      "type": "object",
      "required": ["player_id","fundamentals","boost","movement","positioning","passing","challenges","kickoffs","heatmaps","rotation_compliance","insights"],
      "properties": {
        "player_id": { "type": "string" },
        "fundamentals": { "$ref": "#/definitions/fundamentals" },
        "boost": { "$ref": "#/definitions/boost" },
        "movement": { "$ref": "#/definitions/movement" },
        "positioning": { "$ref": "#/definitions/positioning" },
        "passing": { "$ref": "#/definitions/passing" },
        "challenges": { "$ref": "#/definitions/challenges" },
        "kickoffs": { "$ref": "#/definitions/kickoffs" },
        "heatmaps": {
          "type": "object",
          "properties": {
            "position_occupancy_grid": { "$ref": "#/definitions/grid2d" },
            "touch_density_grid": { "$ref": "#/definitions/grid2d" },
            "boost_pickup_grid": { "$ref": "#/definitions/grid2d" }
          }
        },
        "rotation_compliance": {
          "type": "object",
          "required": ["score_0_to_100","flags"],
          "properties": {
            "score_0_to_100": { "type": "number", "minimum": 0, "maximum": 100 },
            "flags": {
              "type": "array",
              "items": { "type": "string", "description": "e.g., 'double_commit', 'last_man_overcommit', 'no_back_post', 'low_boost_forward'" }
            }
          }
        },
        "insights": { "type": "array", "items": { "$ref": "#/definitions/insight" } }
      }
    },

    "fundamentals": {
      "type": "object",
      "required": ["goals","assists","shots","saves","demos_inflicted","demos_taken","score","shooting_percentage"],
      "properties": {
        "goals": { "type": "integer", "minimum": 0 },
        "assists": { "type": "integer", "minimum": 0 },
        "shots": { "type": "integer", "minimum": 0 },
        "saves": { "type": "integer", "minimum": 0 },
        "demos_inflicted": { "type": "integer", "minimum": 0 },
        "demos_taken": { "type": "integer", "minimum": 0 },
        "score": { "type": "integer", "minimum": 0 },
        "shooting_percentage": { "type": "number", "minimum": 0, "maximum": 100 }
      }
    },

    "boost": {
      "type": "object",
      "required": ["bpm","bcpm","avg_boost","time_zero_boost_s","time_hundred_boost_s","amount_collected","amount_stolen","big_pads","small_pads","overfill","waste"],
      "properties": {
        "bpm": { "type": "number" },
        "bcpm": { "type": "number" },
        "avg_boost": { "type": "number" },
        "time_zero_boost_s": { "type": "number" },
        "time_hundred_boost_s": { "type": "number" },
        "amount_collected": { "type": "number" },
        "amount_stolen": { "type": "number" },
        "big_pads": { "type": "integer" },
        "small_pads": { "type": "integer" },
        "stolen_big_pads": { "type": "integer" },
        "stolen_small_pads": { "type": "integer" },
        "overfill": { "type": "number", "description": "Sum of (100 - boost_before) for pickups that exceed 100" },
        "waste": { "type": "number", "description": "Boost spent with negligible speed benefit (heuristic)" }
      }
    },

    "movement": {
      "type": "object",
      "required": ["avg_speed_kph","time_slow_s","time_boost_speed_s","time_supersonic_s","time_ground_s","time_low_air_s","time_high_air_s","powerslide_count","powerslide_duration_s","aerial_count","aerial_time_s"],
      "properties": {
        "avg_speed_kph": { "type": "number" },
        "time_slow_s": { "type": "number" },
        "time_boost_speed_s": { "type": "number" },
        "time_supersonic_s": { "type": "number" },
        "time_ground_s": { "type": "number" },
        "time_low_air_s": { "type": "number" },
        "time_high_air_s": { "type": "number" },
        "powerslide_count": { "type": "integer" },
        "powerslide_duration_s": { "type": "number" },
        "aerial_count": { "type": "integer" },
        "aerial_time_s": { "type": "number" }
      }
    },

    "positioning": {
      "type": "object",
      "required": ["time_offensive_half_s","time_defensive_half_s","time_offensive_third_s","time_middle_third_s","time_defensive_third_s","behind_ball_pct","ahead_ball_pct","avg_distance_to_ball_m","avg_distance_to_teammate_m","first_man_pct","second_man_pct","third_man_pct"],
      "properties": {
        "time_offensive_half_s": { "type": "number" },
        "time_defensive_half_s": { "type": "number" },
        "time_offensive_third_s": { "type": "number" },
        "time_middle_third_s": { "type": "number" },
        "time_defensive_third_s": { "type": "number" },
        "behind_ball_pct": { "type": "number", "minimum": 0, "maximum": 100 },
        "ahead_ball_pct": { "type": "number", "minimum": 0, "maximum": 100 },
        "avg_distance_to_ball_m": { "type": "number" },
        "avg_distance_to_teammate_m": { "type": "number" },
        "first_man_pct": { "type": "number", "minimum": 0, "maximum": 100 },
        "second_man_pct": { "type": "number", "minimum": 0, "maximum": 100 },
        "third_man_pct": { "type": "number", "minimum": 0, "maximum": 100 }
      }
    },

    "passing": {
      "type": "object",
      "required": ["passes_completed","passes_attempted","passes_received","turnovers","give_and_go_count","possession_time_s"],
      "properties": {
        "passes_completed": { "type": "integer" },
        "passes_attempted": { "type": "integer" },
        "passes_received": { "type": "integer" },
        "turnovers": { "type": "integer" },
        "give_and_go_count": { "type": "integer" },
        "possession_time_s": { "type": "number" }
      }
    },

    "challenges": {
      "type": "object",
      "required": ["contests","wins","losses","neutral","first_to_ball_pct","challenge_depth_m","risk_index_avg"],
      "properties": {
        "contests": { "type": "integer" },
        "wins": { "type": "integer" },
        "losses": { "type": "integer" },
        "neutral": { "type": "integer" },
        "first_to_ball_pct": { "type": "number", "minimum": 0, "maximum": 100 },
        "challenge_depth_m": { "type": "number", "description": "Average Y (field-relative) of contests" },
        "risk_index_avg": { "type": "number", "description": "Heuristic 0–1: last-man + low boost + ahead-of-ball increases risk" }
      }
    },

    "kickoffs": {
      "type": "object",
      "required": ["count","first_possession","neutral","goals_for","goals_against","avg_time_to_first_touch_s","approach_types"],
      "properties": {
        "count": { "type": "integer" },
        "first_possession": { "type": "integer" },
        "neutral": { "type": "integer" },
        "goals_for": { "type": "integer" },
        "goals_against": { "type": "integer" },
        "avg_time_to_first_touch_s": { "type": "number" },
        "approach_types": {
          "type": "object",
          "properties": {
            "STANDARD": { "type": "integer" },
            "SPEEDFLIP": { "type": "integer" },
            "FAKE": { "type": "integer" },
            "DELAY": { "type": "integer" },
            "UNKNOWN": { "type": "integer" }
          }
        }
      }
    },

    "insight": {
      "type": "object",
      "required": ["severity","message","evidence"],
      "properties": {
        "severity": { "type": "string", "enum": ["INFO","SUGGESTION","WARNING"] },
        "message": { "type": "string" },
        "evidence": { "type": "object", "additionalProperties": true }
      }
    },

    "grid2d": {
      "type": "object",
      "required": ["x_bins","y_bins","extent","values"],
      "properties": {
        "x_bins": { "type": "integer", "minimum": 4 },
        "y_bins": { "type": "integer", "minimum": 4 },
        "extent": {
          "type": "object",
          "required": ["xmin","xmax","ymin","ymax"],
          "properties": {
            "xmin": { "type": "number" }, "xmax": { "type": "number" },
            "ymin": { "type": "number" }, "ymax": { "type": "number" }
          }
        },
        "values": {
          "type": "array",
          "items": { "type": "array", "items": { "type": "number" } },
          "description": "Row-major grid values normalized [0..1] or counts"
        }
      }
    },

    "vec3": {
      "type": "object",
      "required": ["x","y","z"],
      "properties": { "x": { "type": "number" }, "y": { "type": "number" }, "z": { "type": "number" } }
    }
  }
}

3.2 Example (success, abridged)

{
  "replay_id": "c8f187...7a",
  "source_file": "Demos/2025-09-01-rlcs.replay",
  "schema_version": "1.0.0",
  "generated_at_utc": "2025-09-08T16:28:00Z",

  "metadata": {
    "engine_build": "v2.54",
    "playlist": "STANDARD",
    "map": "DFH_Stadium",
    "team_size": 3,
    "overtime": true,
    "mutators": {},
    "match_guid": "GUID-abc123",
    "started_at_utc": "2025-09-01T20:04:33Z",
    "duration_seconds": 383.7,
    "recorded_frame_hz": 30.0,
    "total_frames": 11511,
    "coordinate_reference": { "side_wall_x": 4096, "back_wall_y": 5120, "ceiling_z": 2044 }
  },

  "quality": {
    "parser": {
      "name": "rl-local-core",
      "version": "0.9.2",
      "parsed_header": true,
      "parsed_network_data": true,
      "crc_checked": true
    },
    "warnings": []
  },

  "teams": {
    "blue": { "name": "BLUE", "score": 3, "players": ["p1","p2","p3"] },
    "orange": { "name": "ORANGE", "score": 2, "players": ["p4","p5","p6"] }
  },

  "players": [
    {
      "player_id": "p1",
      "display_name": "Trey",
      "team": "BLUE",
      "platform_ids": { "epic": "Epic_123" },
      "camera": { "fov": 110, "height": 110, "angle": -5, "distance": 270, "stiffness": 0.5, "swivel_speed": 5, "transition_speed": 1.2 },
      "loadout": { "car": "Octane" }
    }
    /* ... other players ... */
  ],

  "events": {
    "timeline": [
      { "t": 0.0, "frame": 0, "type": "KICKOFF", "team": null, "data": { "phase": "INITIAL" } },
      { "t": 8.5, "frame": 255, "type": "SHOT", "player_id": "p4" },
      { "t": 9.0, "frame": 270, "type": "SAVE", "player_id": "p1" },
      { "t": 63.2, "frame": 1896, "type": "DEMO", "player_id": "p2", "data": { "victim": "p5" } },
      { "t": 71.7, "frame": 2151, "type": "GOAL", "player_id": "p3", "team": "BLUE" }
    ],
    "goals": [
      { "t": 71.7, "frame": 2151, "scorer": "p3", "team": "BLUE", "assist": "p1", "shot_speed_kph": 108.2, "distance_m": 28.5, "on_target": true, "tickmark_lead_seconds": 1.6 }
    ],
    "demos": [
      { "t": 63.2, "attacker": "p2", "victim": "p5", "team_attacker": "BLUE", "team_victim": "ORANGE", "location": { "x": -2100, "y": 1200, "z": 0 } }
    ],
    "kickoffs": [
      {
        "phase": "INITIAL",
        "t_start": 0.0,
        "players": [
          { "player_id": "p1", "role": "GO", "boost_used": 33, "approach_type": "SPEEDFLIP", "time_to_first_touch": 1.45 },
          { "player_id": "p2", "role": "CHEAT", "boost_used": 12, "approach_type": "STANDARD", "time_to_first_touch": null }
        ],
        "outcome": "FIRST_POSSESSION_BLUE"
      }
    ],
    "boost_pickups": [
      { "t": 22.9, "player_id": "p1", "pad_type": "SMALL", "stolen": false, "pad_id": 7, "location": { "x": 0, "y": -2816, "z": 70 } }
    ],
    "touches": [
      { "t": 71.3, "frame": 2140, "player_id": "p1", "location": { "x": -300, "y": 2100, "z": 180 }, "ball_speed_kph": 94.0, "outcome": "PASS" }
    ]
  },

  "analysis": {
    "per_team": {
      "blue": {
        "fundamentals": { "goals": 3, "assists": 2, "shots": 10, "saves": 6, "demos_inflicted": 4, "demos_taken": 2, "score": 1435, "shooting_percentage": 30.0 },
        "boost": { "bpm": 1120, "bcpm": 1190, "avg_boost": 43, "time_zero_boost_s": 142.2, "time_hundred_boost_s": 71.8, "amount_collected": 6800, "amount_stolen": 980, "big_pads": 52, "small_pads": 175, "stolen_big_pads": 9, "stolen_small_pads": 41, "overfill": 420, "waste": 95 },
        "movement": { "avg_speed_kph": 117.4, "time_slow_s": 498.1, "time_boost_speed_s": 402.7, "time_supersonic_s": 95.3, "time_ground_s": 612.0, "time_low_air_s": 425.0, "time_high_air_s": 40.2, "powerslide_count": 318, "powerslide_duration_s": 39.2, "aerial_count": 47, "aerial_time_s": 58.1 },
        "positioning": { "time_offensive_half_s": 381.5, "time_defensive_half_s": 555.8, "time_offensive_third_s": 197.6, "time_middle_third_s": 406.4, "time_defensive_third_s": 333.3, "behind_ball_pct": 61.2, "ahead_ball_pct": 38.8, "avg_distance_to_ball_m": 25.3, "avg_distance_to_teammate_m": 19.8, "first_man_pct": 32.1, "second_man_pct": 34.7, "third_man_pct": 33.2 },
        "passing": { "passes_completed": 14, "passes_attempted": 24, "passes_received": 12, "turnovers": 9, "give_and_go_count": 3, "possession_time_s": 476.8 },
        "challenges": { "contests": 37, "wins": 18, "losses": 12, "neutral": 7, "first_to_ball_pct": 56.8, "challenge_depth_m": 12.3, "risk_index_avg": 0.31 },
        "kickoffs": { "count": 6, "first_possession": 4, "neutral": 1, "goals_for": 1, "goals_against": 0, "avg_time_to_first_touch_s": 1.53, "approach_types": { "STANDARD": 3, "SPEEDFLIP": 2, "FAKE": 1, "DELAY": 0, "UNKNOWN": 0 } }
      },
      "orange": { /* ... */ }
    },
    "per_player": {
      "p1": {
        "player_id": "p1",
        "fundamentals": { "goals": 1, "assists": 1, "shots": 4, "saves": 3, "demos_inflicted": 1, "demos_taken": 0, "score": 520, "shooting_percentage": 25.0 },
        "boost": { "bpm": 1088, "bcpm": 1122, "avg_boost": 45, "time_zero_boost_s": 41.7, "time_hundred_boost_s": 18.3, "amount_collected": 2120, "amount_stolen": 310, "big_pads": 14, "small_pads": 55, "stolen_big_pads": 2, "stolen_small_pads": 11, "overfill": 128, "waste": 23 },
        "movement": { "avg_speed_kph": 118.9, "time_slow_s": 165.4, "time_boost_speed_s": 138.2, "time_supersonic_s": 31.1, "time_ground_s": 205.0, "time_low_air_s": 132.3, "time_high_air_s": 12.0, "powerslide_count": 96, "powerslide_duration_s": 12.7, "aerial_count": 15, "aerial_time_s": 17.6 },
        "positioning": { "time_offensive_half_s": 122.7, "time_defensive_half_s": 197.1, "time_offensive_third_s": 67.8, "time_middle_third_s": 148.1, "time_defensive_third_s": 103.9, "behind_ball_pct": 59.2, "ahead_ball_pct": 40.8, "avg_distance_to_ball_m": 24.7, "avg_distance_to_teammate_m": 20.1, "first_man_pct": 33.0, "second_man_pct": 35.8, "third_man_pct": 31.2 },
        "passing": { "passes_completed": 6, "passes_attempted": 9, "passes_received": 5, "turnovers": 3, "give_and_go_count": 1, "possession_time_s": 161.0 },
        "challenges": { "contests": 13, "wins": 7, "losses": 3, "neutral": 3, "first_to_ball_pct": 61.5, "challenge_depth_m": 10.8, "risk_index_avg": 0.28 },
        "kickoffs": { "count": 2, "first_possession": 2, "neutral": 0, "goals_for": 1, "goals_against": 0, "avg_time_to_first_touch_s": 1.45, "approach_types": { "STANDARD": 0, "SPEEDFLIP": 2, "FAKE": 0, "DELAY": 0, "UNKNOWN": 0 } },
        "heatmaps": {
          "position_occupancy_grid": { "x_bins": 24, "y_bins": 16, "extent": { "xmin": -4096, "xmax": 4096, "ymin": -5120, "ymax": 5120 }, "values": [[0.00,0.01, ... ]] },
          "touch_density_grid": { "x_bins": 24, "y_bins": 16, "extent": { "xmin": -4096, "xmax": 4096, "ymin": -5120, "ymax": 5120 }, "values": [[...]] },
          "boost_pickup_grid": { "x_bins": 24, "y_bins": 16, "extent": { "xmin": -4096, "xmax": 4096, "ymin": -5120, "ymax": 5120 }, "values": [[...]] }
        },
        "rotation_compliance": { "score_0_to_100": 78.5, "flags": ["double_commit@312.4s"] },
        "insights": [
          { "severity": "SUGGESTION", "message": "Earlier back-post coverage on defensive rotations.", "evidence": { "ahead_ball_pct": 40.8, "third_man_pct": 31.2 } }
        ]
      }
      /* ... other players ... */
    },
    "coaching_insights": [
      { "severity": "INFO", "message": "Kickoff edge: BLUE won first possession 4/6.", "evidence": { "kickoffs.first_possession": { "blue": 4, "orange": 1 } } }
    ]
  }
}

3.3 Error (exact contract)

{ "error": "unreadable_replay_file", "details": "CRC check failed on header; expected 0x9A0C1BEE, got 0x00000000" }

Validation — Schema
	•	Output is JSON with “extensively defined data points”? Yes, with a formal schema and worked example.
	•	Explicit error JSON exactly as specified? Yes.
	•	Per-replay and per-player coverage with fundamentals, advanced analytics, and a timeline? Yes.
	•	Local-only assumptions preserved? Yes.

⸻

Notes on technical grounding & implementation realism
	•	Replay structure: Header contains teams/scores/goals; network frames carry actor updates (rigid bodies), demolishes, boost replication, and tickmarks. Boxcars docs expose these symbols, and rrrocket’s sample JSON shows goals in header and rigid body attributes when network parsing is enabled.  ￼ ￼
	•	Sampling: Many community references and boxcars docs discuss tickmarks and frame examples at ~30 FPS; physics simulation is 120 Hz max, so analysis should disclose replay sampling and avoid overclaiming frame accuracy.  ￼ ￼
	•	Coordinates & boost pads: Use RLBot’s canonical field and 34 boost pad coordinates to classify pickups and “stolen” events robustly.  ￼
	•	Community metric alignment: Ballchasing’s FAQ and recent examples ground the metric families (BPM/BCPM, stolen pads, halves/thirds, heatmaps). This spec stays consistent so coaches can transfer intuition.  ￼

⸻

Requirement Check (final)
	•	Research data structures/metrics? Done with citations (boxcars, rrrocket, rattletrap, RLBot, Ballchasing).  ￼ ￼ ￼ ￼
	•	Comprehensive local-only architecture? Yes—no cloud/APIs anywhere.
	•	Actionable metrics? Yes—rotation compliance, possession/passing, kickoff analysis, challenge risk, plus fundamentals/boost/speed/positioning.
	•	JSON output defined? Yes—formal schema + example.
	•	Error JSON defined? Yes (exact contract).
	•	Per-replay & per-player + timelines? Yes.

If you want, I’ll also draft:
	•	Threshold defaults for insights (e.g., ahead-of-ball > 45% without possession → flag).
	•	A test harness with golden JSONs (including header-only fallback cases) and replay fixtures spanning different game versions.