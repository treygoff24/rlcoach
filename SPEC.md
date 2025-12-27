# RLCoach AI Coaching System Specification

## Problem Statement

A Champion 3 Rocket League player wants to reach Grand Champion in 2v2 but doesn't know what's holding them back. Is it decision making? Positioning? Defense? Mechanics? Diving as last man?

Current replay analysis tools show stats but don't provide actionable coaching. The player needs a system that:
1. Ingests and analyzes their replays automatically
2. Compares their performance against GC-level benchmarks
3. Identifies patterns in wins vs losses
4. Diagnoses specific weaknesses
5. Prescribes focused practice to address those weaknesses

This is a personal tool for self-improvement, not a product for sale.

## Scope

### In Scope
- Automated replay ingestion from synced folder (Dropbox from Windows gaming PC)
- Persistent storage of replay analysis data (SQLite + raw JSON)
- Local web GUI for data exploration (FastAPI + React)
- Claude Code skill for AI-powered coaching conversations
- GC-level benchmark comparisons
- Win/loss pattern analysis
- Teammate and opponent tracking with adaptability coaching
- Practice prescriptions with web-searched resources (drills, workshop maps, training packs, tutorials)
- All competitive game modes (2v2 primary focus, 1v1 and 3v3 supported)

### Out of Scope (V1)
- Video/clip generation from replays
- 2D/3D replay visualization (future enhancement)
- Mobile app
- Cloud deployment (local only for V1)
- Real-time in-game overlay
- Ballchasing.com integration/upload
- Account/authentication (single user, local)

### Future Enhancements
- 2D field visualization of key moments (car/ball positions at timestamps)
- Ballchasing.com auto-upload with viewer links
- Cloud deployment for web access
- Session streaming from gaming PC (eliminate Dropbox sync delay)

---

## Configuration

### Overview
RLCoach requires initial configuration before first use. Configuration is stored in `~/.rlcoach/config.toml`.

### Configuration File Format

```toml
[identity]
# Primary player identification - at least one required
# These are checked in order: platform_ids first, then display_names as fallback
platform_ids = [
    "steam:76561198012345678",
    "epic:abc123def456"
]
# Fallback display names (used if platform_id not found in replay)
display_names = ["YourGamertag", "YourAltAccount"]

[paths]
# Watch folder for incoming replays (Dropbox sync target)
watch_folder = "~/Dropbox/RocketLeague/Replays"
# Where to store processed data
data_dir = "~/.rlcoach/data"
# Where to store JSON reports
reports_dir = "~/.rlcoach/reports"

[preferences]
# Primary playlist for comparisons (DOUBLES, STANDARD, DUEL)
primary_playlist = "DOUBLES"
# Target rank for benchmark comparisons
target_rank = "GC1"
# Timezone for day boundary calculation (uses system timezone if not set)
timezone = "America/Los_Angeles"

[teammates]
# Tagged teammates for tracking (display_name -> optional notes)
[teammates.tagged]
"DuoPartnerName" = "Main 2s partner"
"OtherFriend" = "Occasional 3s teammate"
```

### Player Identity Resolution

The system determines "who is me" in each replay using the following priority:

1. **Platform ID match**: Check if any `platform_ids` from config matches a player's platform ID in the replay
2. **Display name match**: If no platform ID match, check if any `display_names` matches (case-insensitive)
3. **Failure**: If no match found, log a warning and skip the replay (don't guess)

This handles:
- Name changes: Platform ID is stable across name changes
- Multiple accounts: List all platform IDs you play on
- Platform migration: Add both old and new platform IDs

### First-Run Setup

On first run, if no config exists:
1. Create `~/.rlcoach/config.toml` with template
2. Prompt user to edit config with their player info
3. Validate config before proceeding

CLI command: `rlcoach config --init` creates template, `rlcoach config --validate` checks config.

---

## User Stories

### Replay Ingestion
- As a player, I want my replays to automatically sync from my gaming PC and be ingested, so I don't have to manually import files
- As a player, I want replays grouped by day (in my local timezone), so I can easily find "last night's session"

### Data Exploration (GUI)
- As a player, I want a dashboard showing my recent trends and key metrics, so I can see how I'm doing at a glance
- As a player, I want to view all games from a specific day with win/loss and key stats, so I can review a session
- As a player, I want charts showing my metrics over weeks/months, so I can see if I'm improving
- As a player, I want to compare my stats against GC benchmarks, so I can see the gaps
- As a player, I want to deep-dive into a single replay with full event timeline and heatmaps, so I can understand specific games
- As a player, I want a "weaknesses" view showing what the data says I need to work on, so I have clear focus areas

### AI Coaching (Claude Code)
- As a player, I want to say "analyze today" and get a full coaching breakdown, so I understand my session
- As a player, I want to ask "why did I lose that last game?" and get specific mistakes with timestamps, so I can learn from losses
- As a player, I want to ask "what should I practice this week?" and get a focused prescription based on my trends
- As a player, I want to ask "compare my kickoffs to GC" and get a targeted deep-dive on that skill
- As a player, I want to validate hunches like "I felt slow today, was I?" with actual data

### Teammate/Opponent Analysis
- As a player, I want to tag frequent teammates by username, so I can track patterns with regular duo partners
- As a player, I want coaching that considers my teammate's playstyle, so I learn to adapt ("your teammate was diving, you should have stayed back")
- As a player, I want to understand opponent tendencies when relevant, so I can exploit patterns

### Practice Prescriptions
- As a player, I want drill recommendations that address my specific weaknesses
- As a player, I want workshop map codes for skill training
- As a player, I want training pack codes for specific scenarios
- As a player, I want YouTube tutorial links for mechanics I need to learn
- As a player, I want these resources to be current (web searched, not hardcoded)

---

## Technical Approach

### Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                         Gaming PC (Windows)                      │
│  ┌─────────────┐     ┌─────────────┐                            │
│  │ Rocket League│────▶│ Dropbox Sync │                           │
│  │  (replays)   │     │   Folder     │                           │
│  └─────────────┘     └──────┬──────┘                            │
└─────────────────────────────┼───────────────────────────────────┘
                              │ (cloud sync)
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                         MacBook (Local)                          │
│  ┌─────────────┐     ┌─────────────┐     ┌─────────────┐       │
│  │ Dropbox Sync │────▶│ Watch Folder │────▶│  Ingestion  │       │
│  │   Folder     │     │   Service    │     │  Pipeline   │       │
│  └─────────────┘     └─────────────┘     └──────┬──────┘       │
│                                                   │              │
│                                                   ▼              │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                      Data Layer                          │   │
│  │  ┌─────────────┐              ┌─────────────┐           │   │
│  │  │   SQLite    │              │  Raw JSON   │           │   │
│  │  │ (aggregates)│              │   Reports   │           │   │
│  │  └─────────────┘              └─────────────┘           │   │
│  └─────────────────────────────────────────────────────────┘   │
│           │                              │                       │
│           ▼                              ▼                       │
│  ┌─────────────┐              ┌─────────────────────┐          │
│  │   FastAPI   │◀────────────▶│    Claude Code      │          │
│  │   Backend   │              │  (coaching skill)   │          │
│  └──────┬──────┘              └─────────────────────┘          │
│         │                                                        │
│         ▼                                                        │
│  ┌─────────────┐                                                │
│  │    React    │                                                │
│  │   Frontend  │                                                │
│  │ (localhost) │                                                │
│  └─────────────┘                                                │
└─────────────────────────────────────────────────────────────────┘
```

### Components

#### 1. Ingestion Pipeline (existing + extension)
- **Watch folder service**: Monitors Dropbox-synced replay directory for new `.replay` files
- **File stability check**: Wait for file size to stabilize (no changes for 2 seconds) before processing
- **Parser**: Existing Rust + Python pipeline (already built, ballchasing parity achieved)
- **Identity resolution**: Match player to config using platform_id or display_name
- **Storage writer**: Writes to both SQLite (aggregates) and JSON files (full reports)
- **Deduplication**: Skip files where `replay_id` already exists in database

#### 2. Data Layer
- **SQLite** (chosen over DuckDB for simplicity and portability): Fast queries for aggregates, trends, comparisons
  - Player stats per game
  - Daily aggregates by playlist
  - Benchmark comparisons
  - Teammate/opponent tracking
- **JSON Reports**: Full replay analysis for deep dives
  - Frame-level events
  - Heatmaps
  - Complete analysis output from existing pipeline

#### 3. FastAPI Backend
- REST API serving data to both GUI and Claude Code
- Endpoints for:
  - Dashboard aggregates
  - Day/session queries with pagination
  - Trend data over time ranges
  - Single replay details
  - Benchmark comparisons
  - Player (teammate/opponent) lookups
- Runs on `localhost:8000` only (no external access)

#### 4. React Frontend
- Local web app at `localhost:5173` (dev) / served by FastAPI (prod)
- Views:
  - Dashboard (overview + recent trends)
  - Day view (games list with stats)
  - Trends (charts over time)
  - Comparison (vs GC benchmarks)
  - Replay deep-dive (single game breakdown)
  - Focus areas (computed weaknesses)

#### 5. Claude Code Coaching Skill
- Custom skill installed in Claude Code
- Knows how to:
  - Query the FastAPI backend for data
  - Read raw JSON reports for deep analysis
  - Follow the coaching loop (analysis → diagnosis → comparison → prescription)
  - Reference GC benchmarks
  - Search web for current practice resources
  - Point user to specific GUI views
  - Track context about frequent teammates

### Technology Stack
- **Backend**: Python 3.11+, FastAPI, SQLite, Pydantic
- **Frontend**: React 18+, TypeScript, Vite, Recharts, TailwindCSS
- **Parser**: Existing Rust (boxcars) + Python pipeline
- **Coaching**: Claude Code with custom skill
- **Sync**: Dropbox (user-configured on Windows PC)

---

## Data Model

### SQLite Schema

```sql
-- Core replay metadata
CREATE TABLE replays (
    replay_id TEXT PRIMARY KEY,  -- SHA256 of header bytes + match_guid
    source_file TEXT NOT NULL,
    file_hash TEXT NOT NULL,  -- SHA256 of entire file for dedup
    ingested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    played_at_utc TIMESTAMP NOT NULL,  -- UTC timestamp from replay
    play_date DATE NOT NULL,  -- Local date derived from played_at_utc + configured timezone
    map TEXT NOT NULL,
    playlist TEXT NOT NULL,  -- DUEL, DOUBLES, STANDARD, CHAOS
    team_size INTEGER NOT NULL,
    duration_seconds REAL NOT NULL,
    overtime BOOLEAN DEFAULT FALSE,
    my_player_id TEXT NOT NULL,  -- Player ID of "me" in this replay
    my_team TEXT NOT NULL,  -- BLUE or ORANGE
    my_score INTEGER NOT NULL,
    opponent_score INTEGER NOT NULL,
    result TEXT NOT NULL,  -- WIN, LOSS, DRAW
    json_report_path TEXT NOT NULL,  -- Path to full JSON report
    FOREIGN KEY (my_player_id) REFERENCES players(player_id)
);

-- Player registry (for tracking teammates/opponents)
CREATE TABLE players (
    player_id TEXT PRIMARY KEY,  -- From replay (unique per platform)
    display_name TEXT NOT NULL,
    platform TEXT,  -- steam, epic, psn, xbox
    is_me BOOLEAN DEFAULT FALSE,  -- True if this matches config identity
    is_tagged_teammate BOOLEAN DEFAULT FALSE,
    teammate_notes TEXT,  -- Optional notes from config
    first_seen_utc TIMESTAMP,
    last_seen_utc TIMESTAMP,
    games_with_me INTEGER DEFAULT 0  -- Games where this player appeared with me
);

-- Per-player per-game stats (denormalized for fast queries)
CREATE TABLE player_game_stats (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    replay_id TEXT NOT NULL,
    player_id TEXT NOT NULL,
    team TEXT NOT NULL,  -- BLUE or ORANGE
    is_me BOOLEAN DEFAULT FALSE,
    is_teammate BOOLEAN DEFAULT FALSE,  -- Same team as me, not me
    is_opponent BOOLEAN DEFAULT FALSE,  -- Opposite team from me

    -- Fundamentals
    goals INTEGER DEFAULT 0,
    assists INTEGER DEFAULT 0,
    saves INTEGER DEFAULT 0,
    shots INTEGER DEFAULT 0,
    shooting_pct REAL,  -- goals/shots * 100, NULL if 0 shots
    score INTEGER DEFAULT 0,
    demos_inflicted INTEGER DEFAULT 0,
    demos_taken INTEGER DEFAULT 0,

    -- Boost (see Metric Catalog for units)
    bcpm REAL,
    avg_boost REAL,
    time_zero_boost_s REAL,
    time_full_boost_s REAL,
    boost_collected REAL,
    boost_stolen REAL,
    big_pads INTEGER,
    small_pads INTEGER,

    -- Movement
    avg_speed_kph REAL,
    time_supersonic_s REAL,
    time_slow_s REAL,
    time_ground_s REAL,
    time_low_air_s REAL,
    time_high_air_s REAL,

    -- Positioning
    time_offensive_third_s REAL,
    time_middle_third_s REAL,
    time_defensive_third_s REAL,
    behind_ball_pct REAL,
    avg_distance_to_ball_m REAL,
    avg_distance_to_teammate_m REAL,
    first_man_pct REAL,
    second_man_pct REAL,
    third_man_pct REAL,  -- NULL for 1v1 and 2v2

    -- Challenges
    challenge_wins INTEGER,
    challenge_losses INTEGER,
    challenge_neutral INTEGER,
    first_to_ball_pct REAL,

    -- Kickoffs
    kickoffs_participated INTEGER,
    kickoff_first_touches INTEGER,

    -- Mechanics
    wavedash_count INTEGER,
    halfflip_count INTEGER,
    speedflip_count INTEGER,
    aerial_count INTEGER,
    flip_cancel_count INTEGER,

    -- Recovery
    total_recoveries INTEGER,
    avg_recovery_momentum REAL,  -- 0-100 scale

    -- Defense
    time_last_defender_s REAL,
    time_shadow_defense_s REAL,

    -- xG
    total_xg REAL,
    shots_xg_list TEXT,  -- JSON array of per-shot xG values

    FOREIGN KEY (replay_id) REFERENCES replays(replay_id),
    FOREIGN KEY (player_id) REFERENCES players(player_id),
    UNIQUE(replay_id, player_id)
);

-- Daily aggregates by playlist (materialized for performance)
CREATE TABLE daily_stats (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    play_date DATE NOT NULL,
    playlist TEXT NOT NULL,  -- DUEL, DOUBLES, STANDARD
    games_played INTEGER DEFAULT 0,
    wins INTEGER DEFAULT 0,
    losses INTEGER DEFAULT 0,
    draws INTEGER DEFAULT 0,
    win_rate REAL,  -- wins / games_played * 100

    -- Averaged stats for my games that day
    avg_goals REAL,
    avg_assists REAL,
    avg_saves REAL,
    avg_shots REAL,
    avg_shooting_pct REAL,
    avg_bcpm REAL,
    avg_boost REAL,
    avg_speed_kph REAL,
    avg_supersonic_pct REAL,  -- time_supersonic / duration * 100
    avg_behind_ball_pct REAL,
    avg_first_man_pct REAL,
    avg_challenge_win_pct REAL,

    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(play_date, playlist)
);

-- GC Benchmarks (imported from research data)
CREATE TABLE benchmarks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    metric TEXT NOT NULL,  -- Must match metric_catalog key
    playlist TEXT NOT NULL,  -- DOUBLES, STANDARD, DUEL
    rank_tier TEXT NOT NULL,  -- C2, C3, GC1, GC2, GC3, SSL
    median_value REAL NOT NULL,
    p25_value REAL,  -- 25th percentile (low end of normal)
    p75_value REAL,  -- 75th percentile (high end of normal)
    elite_threshold REAL,  -- Top 10% threshold
    source TEXT NOT NULL,  -- Where this data came from
    source_date DATE,  -- When source data was collected
    notes TEXT,
    imported_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(metric, playlist, rank_tier)
);

-- Indexes for common queries
CREATE INDEX idx_replays_date ON replays(play_date DESC);
CREATE INDEX idx_replays_playlist ON replays(playlist);
CREATE INDEX idx_replays_result ON replays(result);
CREATE INDEX idx_player_stats_replay ON player_game_stats(replay_id);
CREATE INDEX idx_player_stats_player ON player_game_stats(player_id);
CREATE INDEX idx_player_stats_me ON player_game_stats(is_me) WHERE is_me = TRUE;
CREATE INDEX idx_daily_stats_lookup ON daily_stats(play_date DESC, playlist);
CREATE INDEX idx_benchmarks_lookup ON benchmarks(metric, playlist, rank_tier);
```

### Replay Identity and Deduplication

**`replay_id`**: Deterministic hash computed as `SHA256(header_bytes + match_guid)`. This is:
- Stable across file renames/moves
- Unique per actual game
- Already computed by existing parser

**`file_hash`**: SHA256 of entire file contents. Used to detect:
- Dropbox conflict copies (same replay_id but different file_hash = skip)
- Re-synced identical files (same file_hash = skip)

**Deduplication logic**:
1. Compute file_hash of new file
2. If file_hash exists in DB → skip (exact duplicate)
3. Parse replay, get replay_id
4. If replay_id exists in DB → skip (same game, different file)
5. Otherwise → ingest

### JSON Report Structure
Existing schema from `schemas/replay_report.schema.json` - no changes needed. Full reports stored as files, referenced by `json_report_path` in SQLite.

---

## Metric Catalog

All metrics tracked in the system with definitions, units, validity, and comparison direction.

**Directionality**: `↑` = higher is better, `↓` = lower is better, `~` = context-dependent (no benchmark comparison)

| Metric Key | Display Name | Unit | Dir | Definition | Valid Modes | Source |
|------------|--------------|------|-----|------------|-------------|--------|
| `goals` | Goals | count | ↑ | Goals scored | All | fundamentals |
| `assists` | Assists | count | ↑ | Passes leading to goals | All | fundamentals |
| `saves` | Saves | count | ↑ | Shots blocked | All | fundamentals |
| `shots` | Shots | count | ↑ | Shots on goal | All | fundamentals |
| `shooting_pct` | Shooting % | percent | ↑ | goals / shots * 100 | All | fundamentals |
| `score` | Score | points | ↑ | In-game score | All | fundamentals |
| `demos_inflicted` | Demos | count | ↑ | Demolitions made | All | fundamentals |
| `demos_taken` | Deaths | count | ↓ | Times demolished | All | fundamentals |
| `bcpm` | Boost/Min | boost/min | ↑ | Boost collected per minute | All | boost |
| `avg_boost` | Avg Boost | 0-100 | ↑ | Average boost amount held | All | boost |
| `time_zero_boost_s` | Zero Boost Time | seconds | ↓ | Time at 0 boost | All | boost |
| `time_full_boost_s` | Full Boost Time | seconds | ~ | Time at 100 boost | All | boost |
| `boost_collected` | Boost Collected | total | ↑ | Total boost picked up | All | boost |
| `boost_stolen` | Boost Stolen | total | ↑ | Boost from opponent half | All | boost |
| `big_pads` | Big Pads | count | ~ | 100-boost pads collected | All | boost |
| `small_pads` | Small Pads | count | ~ | 12-boost pads collected | All | boost |
| `avg_speed_kph` | Avg Speed | km/h | ↑ | Average car speed | All | movement |
| `time_supersonic_s` | Supersonic Time | seconds | ↑ | Time at supersonic (95%+ max) | All | movement |
| `time_slow_s` | Slow Time | seconds | ↓ | Time below 50% max speed | All | movement |
| `time_ground_s` | Ground Time | seconds | ~ | Time on ground | All | movement |
| `time_low_air_s` | Low Air Time | seconds | ~ | Time in air below goal height | All | movement |
| `time_high_air_s` | High Air Time | seconds | ~ | Time in air above goal height | All | movement |
| `time_offensive_third_s` | Off. Third Time | seconds | ~ | Time in offensive third | All | positioning |
| `time_middle_third_s` | Mid Third Time | seconds | ~ | Time in middle third | All | positioning |
| `time_defensive_third_s` | Def. Third Time | seconds | ~ | Time in defensive third | All | positioning |
| `behind_ball_pct` | Behind Ball % | percent | ↑ | Time positioned behind ball | All | positioning |
| `avg_distance_to_ball_m` | Avg Dist to Ball | meters | ~ | Average distance to ball | All | positioning |
| `avg_distance_to_teammate_m` | Avg Teammate Dist | meters | ~ | Avg distance to teammate | 2v2, 3v3 | positioning |
| `first_man_pct` | 1st Man % | percent | ~ | Time as player closest to ball | All | positioning |
| `second_man_pct` | 2nd Man % | percent | ~ | Time as 2nd closest to ball | 2v2, 3v3 | positioning |
| `third_man_pct` | 3rd Man % | percent | ~ | Time as 3rd closest to ball | 3v3 only | positioning |
| `challenge_wins` | 50/50 Wins | count | ↑ | Challenges won | All | challenges |
| `challenge_losses` | 50/50 Losses | count | ↓ | Challenges lost | All | challenges |
| `first_to_ball_pct` | First to Ball % | percent | ↑ | % challenges touched first | All | challenges |
| `wavedash_count` | Wavedashes | count | ↑ | Wavedash mechanics used | All | mechanics |
| `halfflip_count` | Half-Flips | count | ↑ | Half-flip mechanics used | All | mechanics |
| `speedflip_count` | Speedflips | count | ↑ | Speedflip mechanics used | All | mechanics |
| `aerial_count` | Aerials | count | ↑ | Aerial touches | All | mechanics |
| `flip_cancel_count` | Flip Cancels | count | ↑ | Flip cancel mechanics used | All | mechanics |
| `avg_recovery_momentum` | Recovery Quality | 0-100 | ↑ | Avg momentum after landings | All | recovery |
| `time_last_defender_s` | Last Defender Time | seconds | ~ | Time as last player back | All | defense |
| `time_shadow_defense_s` | Shadow Time | seconds | ↑ | Time in shadow defense | All | defense |
| `total_xg` | Expected Goals | xG | ↑ | Sum of shot xG values | All | xg |

### Comparison Logic

When comparing metrics to benchmarks:
- **↑ (higher is better)**: `my_value > benchmark.p75` = ahead, `my_value < benchmark.p25` = behind
- **↓ (lower is better)**: `my_value < benchmark.p25` = ahead, `my_value > benchmark.p75` = behind
- **~ (context-dependent)**: Skip benchmark comparison; use only for win/loss pattern analysis

---

## Benchmark Data Format

### Import Format

Benchmarks are imported from JSON files with the following structure:

```json
{
  "metadata": {
    "source": "ballchasing.com aggregate data",
    "collected_date": "2024-12-01",
    "notes": "Based on 10,000+ ranked 2v2 replays per rank tier"
  },
  "benchmarks": [
    {
      "metric": "bcpm",
      "playlist": "DOUBLES",
      "rank_tier": "GC1",
      "median": 320,
      "p25": 280,
      "p75": 360,
      "elite": 400
    },
    {
      "metric": "avg_boost",
      "playlist": "DOUBLES",
      "rank_tier": "GC1",
      "median": 45,
      "p25": 38,
      "p75": 52,
      "elite": 58
    }
  ]
}
```

### Import CLI

```bash
# Import benchmarks from JSON file
rlcoach benchmarks import path/to/benchmarks.json

# List current benchmarks
rlcoach benchmarks list --playlist DOUBLES --rank GC1

# Clear and reimport
rlcoach benchmarks import path/to/benchmarks.json --replace
```

### Validation Rules
- `metric` must exist in Metric Catalog
- `playlist` must be DUEL, DOUBLES, or STANDARD
- `rank_tier` must be C2, C3, GC1, GC2, GC3, or SSL
- `median` is required; p25, p75, elite are optional
- Duplicate (metric, playlist, rank_tier) tuples update existing records

---

## Win/Loss Pattern Analysis

### Overview

Pattern analysis identifies statistically significant differences between wins and losses to surface actionable insights.

### Methodology

#### 1. Data Requirements
- Minimum 20 games in the analysis window for reliable patterns
- At least 5 wins and 5 losses (skewed W/L prevents meaningful comparison)
- Analysis window defaults to last 50 games, configurable

#### 2. Per-Metric Comparison

For each metric in the Metric Catalog:
```
win_avg = mean(metric in wins)
loss_avg = mean(metric in losses)
delta = win_avg - loss_avg
delta_pct = (delta / loss_avg) * 100  # Relative change
effect_size = delta / pooled_std_dev  # Cohen's d
```

#### 3. Significance Filtering

A pattern is "significant" if:
- `|effect_size| >= 0.3` (small-to-medium effect)
- AND `sample_size >= 10` per group (wins/losses)
- AND `delta_pct >= 5%` (at least 5% relative difference)

#### 4. Pattern Output

```json
{
  "analysis_window": {"games": 50, "wins": 28, "losses": 22},
  "significant_patterns": [
    {
      "metric": "avg_boost",
      "direction": "higher_in_wins",
      "win_avg": 48.2,
      "loss_avg": 41.5,
      "delta": 6.7,
      "delta_pct": 16.1,
      "effect_size": 0.52,
      "insight": "You maintain 16% higher average boost in wins"
    },
    {
      "metric": "time_last_defender_s",
      "direction": "higher_in_losses",
      "win_avg": 45.2,
      "loss_avg": 62.8,
      "delta": -17.6,
      "delta_pct": -28.0,
      "effect_size": -0.68,
      "insight": "You spend 28% more time as last defender in losses (possibly too passive)"
    }
  ],
  "no_pattern_metrics": ["goals", "saves", "shots"]  // No significant difference
}
```

#### 5. Avoiding Overfitting

- Don't surface patterns with p-value > 0.1 (if sample size allows statistical testing)
- Require minimum effect size to avoid noise
- Flag patterns that contradict GC benchmarks ("you have higher X in wins, but GC players have even higher X")
- Recalculate patterns as new games are added (rolling window)

---

## Teammate/Opponent Tendency Analysis

### Overview

Analyze playstyle tendencies of teammates and opponents to provide adaptive coaching.

### Tendency Metrics

For each player (teammate or opponent), compute their tendencies from games they appear in:

| Tendency | Computation | Interpretation |
|----------|-------------|----------------|
| `aggression_score` | `(time_offensive_third / duration) * 100` | High = aggressive, Low = passive |
| `challenge_rate` | `challenges_initiated / duration * 60` | Challenges per minute |
| `first_man_tendency` | `first_man_pct` average | High = ball-chaser, Low = rotator |
| `boost_priority` | `big_pads / (big_pads + small_pads)` | High = big pad hunter |
| `mechanical_index` | `(aerials + wavedashes + speedflips) / duration * 60` | Mechanical vs fundamental playstyle |
| `defensive_index` | `(saves + time_last_defender) / duration` | Defensive responsibility |

### Adaptation Score

Measures how well you adapted to your teammate's playstyle:

```python
def compute_adaptation_score(my_stats, teammate_tendencies):
    score = 100  # Start at 100, deduct for mismatches

    # If teammate is aggressive, you should be more passive
    if teammate_tendencies.aggression_score > 60:
        if my_stats.aggression_score > 50:
            score -= 20  # Both aggressive = double commit risk

    # If teammate ball-chases, you should rotate
    if teammate_tendencies.first_man_pct > 50:
        if my_stats.first_man_pct > 40:
            score -= 15  # Both first man = bad rotation

    # If teammate is passive/defensive, you can be more aggressive
    if teammate_tendencies.aggression_score < 40:
        if my_stats.time_offensive_third_pct < 30:
            score -= 10  # Both passive = no pressure

    return max(0, min(100, score))
```

### Storage

Tendencies are computed on-demand from `player_game_stats` using window functions over the last N games with that player. Not stored separately.

### API Response

```json
{
  "player_id": "steam:12345",
  "display_name": "DuoPartner",
  "games_together": 47,
  "win_rate_together": 58.5,
  "tendencies": {
    "aggression_score": 65.2,
    "challenge_rate": 4.8,
    "first_man_tendency": 48.3,
    "boost_priority": 0.62,
    "mechanical_index": 2.1,
    "defensive_index": 0.35
  },
  "your_adaptation": {
    "score": 72,
    "issues": [
      "You both play aggressive (high double-commit risk)",
      "Consider playing more second-man when with this teammate"
    ]
  }
}
```

---

## Weakness Detection Algorithm

### Overview

Automatically identify areas needing improvement by comparing against benchmarks and analyzing patterns.

### Severity Levels

| Level | Criteria | Action |
|-------|----------|--------|
| `critical` | Metric is >2 standard deviations below target rank benchmark | Immediate focus required |
| `high` | Metric is 1-2 SD below benchmark, OR strong negative pattern in losses | Priority practice area |
| `medium` | Metric is 0.5-1 SD below benchmark | Worth improving |
| `low` | Metric is slightly below benchmark but not impacting results | Nice to have |
| `strength` | Metric is above target rank benchmark | Keep doing this |

### Detection Process

```python
def detect_weaknesses(my_averages, benchmarks, patterns, min_games=20):
    weaknesses = []

    for metric in METRIC_CATALOG:
        my_value = my_averages.get(metric)
        benchmark = benchmarks.get(metric)
        pattern = patterns.get(metric)

        if my_value is None or benchmark is None:
            continue

        # Compute gap
        gap = my_value - benchmark.median
        gap_pct = (gap / benchmark.median) * 100

        # Estimate standard deviation from percentiles
        if benchmark.p25 and benchmark.p75:
            estimated_sd = (benchmark.p75 - benchmark.p25) / 1.35
            z_score = gap / estimated_sd
        else:
            z_score = None

        # Determine severity
        if z_score and z_score < -2:
            severity = "critical"
        elif z_score and z_score < -1:
            severity = "high"
        elif pattern and pattern.direction == "higher_in_wins" and gap < 0:
            severity = "high"  # Below benchmark AND pattern shows it matters
        elif z_score and z_score < -0.5:
            severity = "medium"
        elif gap < 0:
            severity = "low"
        else:
            severity = "strength"

        weaknesses.append({
            "metric": metric,
            "severity": severity,
            "my_value": my_value,
            "benchmark_median": benchmark.median,
            "gap": gap,
            "gap_pct": gap_pct,
            "z_score": z_score,
            "pattern_evidence": pattern.insight if pattern else None
        })

    # Sort by severity (critical first) then by gap magnitude
    return sorted(weaknesses, key=lambda w: (SEVERITY_ORDER[w.severity], w.gap))
```

### Minimum Data Requirements

- Need at least 20 games in the analysis window
- Benchmarks must be loaded for target rank
- Metrics with insufficient data show "needs more games"

---

## Insight Generation

### Overview

Insights are human-readable observations about gameplay. They come from two sources:

1. **Pipeline Insights**: Generated by the Python analysis pipeline during ingestion (deterministic, cached in JSON report)
2. **Claude Insights**: Generated by Claude Code skill during coaching sessions (dynamic, contextual)

### Pipeline Insights (Existing)

Already implemented in `src/rlcoach/analysis/insights.py`. Stored in JSON report under `analysis.coaching_insights`. Examples:
- "High boost waste (32%) - consider using small pads more"
- "Strong kickoff presence - won first touch 78% of the time"
- "Low recovery momentum (45%) - practice wavedash landings"

These are deterministic and don't change once computed.

### Claude Insights (Coaching Skill)

Generated on-demand during coaching conversations. Examples:
- "In your losses today, you averaged 15 more seconds as last defender than in wins - you might be playing too passive when down"
- "Your teammate DuoPartner plays very aggressive (65th percentile). When you play with them, consider hanging back more."

These are dynamic, consider context, and can incorporate pattern analysis + teammate data.

### API Response

The `/replays/{id}` endpoint returns pipeline insights:
```json
{
  "insights": [
    {"severity": "SUGGESTION", "message": "...", "evidence": {...}}
  ]
}
```

Claude reads this + runs additional analysis for conversational insights.

---

## API Contracts

### Base URL
`http://localhost:8000/api/v1`

### Common Parameters

**Pagination** (for list endpoints):
- `limit`: Max items to return (default: 50, max: 200)
- `offset`: Skip N items (default: 0)
- Response includes: `{"total": N, "limit": 50, "offset": 0, "items": [...]}`

**Sorting** (where applicable):
- `sort`: Field to sort by (prefix with `-` for descending)
- Example: `?sort=-played_at` (newest first)

**Filtering**:
- `playlist`: DUEL, DOUBLES, STANDARD
- `result`: WIN, LOSS, DRAW
- `start_date`, `end_date`: ISO format YYYY-MM-DD (in configured timezone)

### Error Codes

| Code | HTTP Status | Description |
|------|-------------|-------------|
| `not_found` | 404 | Specific resource doesn't exist (e.g., `/replays/{id}` with invalid id) |
| `invalid_param` | 400 | Invalid query parameter value |
| `config_error` | 500 | Configuration issue (e.g., no identity configured) |
| `benchmark_missing` | 404 | Requested benchmark rank/playlist not loaded |

### Empty vs 404 Behavior

**List endpoints** (return empty list, never 404):
- `/games?date=...` → `{"total": 0, "items": []}`
- `/players?tagged=true` → `{"total": 0, "items": []}`
- `/patterns` with insufficient data → `{"insufficient_data": true, "reason": "..."}`

**Resource endpoints** (return 404 if not found):
- `/replays/{id}` → 404 if replay doesn't exist
- `/players/{id}` → 404 if player not in database
- `/benchmarks?rank=GC1` → 404 if no benchmarks loaded for that rank

### Endpoints

#### Dashboard
```
GET /dashboard
Response: {
    "recent_games": [...],  // Last 10 games (summary only)
    "today": {
        "games": 5, "wins": 3, "losses": 2, "win_rate": 60.0
    },
    "week_trend": {
        "games": 35, "wins": 20, "win_rate": 57.1,
        "trend": "improving"  // improving, declining, stable
    },
    "top_weaknesses": [  // Top 3 by severity
        {"metric": "bcpm", "severity": "high", "gap_pct": -12.5}
    ],
    "vs_target_rank": {
        "rank": "GC1",
        "metrics_ahead": 8,
        "metrics_behind": 12,
        "biggest_gap": {"metric": "avg_boost", "gap_pct": -15.2}
    }
}
```

#### Games List
```
GET /games
GET /games?date=2024-12-23
GET /games?start_date=2024-12-20&end_date=2024-12-23
GET /games?playlist=DOUBLES&result=LOSS
GET /games?limit=20&offset=40&sort=-played_at

Response: {
    "total": 156,
    "limit": 50,
    "offset": 0,
    "summary": {
        "games": 156, "wins": 89, "losses": 67, "win_rate": 57.1
    },
    "items": [
        {
            "replay_id": "abc123...",
            "played_at": "2024-12-23T19:45:00Z",
            "play_date": "2024-12-23",
            "map": "DFH Stadium",
            "playlist": "DOUBLES",
            "result": "WIN",
            "my_score": 3,
            "opponent_score": 1,
            "duration_seconds": 312,
            "my_stats_summary": {
                "goals": 1, "assists": 1, "saves": 2, "bcpm": 295
            }
        }
    ]
}
```

#### Single Replay
```
GET /replays/{replay_id}
Response: {
    "replay_id": "abc123...",
    "metadata": {
        "played_at": "2024-12-23T19:45:00Z",
        "map": "DFH Stadium",
        "playlist": "DOUBLES",
        "duration_seconds": 312,
        "overtime": false
    },
    "result": {"my_score": 3, "opponent_score": 1, "result": "WIN"},
    "my_stats": {...},  // Full player_game_stats for me
    "teammates": [...],  // Array of teammate stats
    "opponents": [...],  // Array of opponent stats
    "events_summary": {
        "goals": 4,
        "demos": 2,
        "kickoffs": 5
    },
    "insights": [...]  // From pipeline
}

GET /replays/{replay_id}/events?type=GOAL
Response: {
    "total": 4,
    "items": [
        {"t": 45.2, "type": "GOAL", "player_id": "...", "data": {...}}
    ]
}

GET /replays/{replay_id}/full
Response: <complete JSON report file contents>

GET /replays/{replay_id}/heatmaps
Response: {
    "replay_id": "abc123...",
    "field_dimensions": {"width": 8192, "height": 10240},  // RLBot field units
    "grid_resolution": {"rows": 20, "cols": 16},  // 20x16 grid cells
    "heatmaps": {
        "position": {
            "description": "Time spent in each grid cell",
            "unit": "seconds",
            "player_id": "steam:12345",
            "data": [[0.5, 1.2, ...], ...]  // 20x16 grid, row-major
        },
        "touches": {
            "description": "Ball touches per grid cell",
            "unit": "count",
            "player_id": "steam:12345",
            "data": [[0, 2, ...], ...]
        },
        "boost_pickups": {
            "description": "Boost pad pickups per cell",
            "unit": "count",
            "player_id": "steam:12345",
            "data": [[1, 0, ...], ...]
        }
    },
    "normalization": "per_player"  // Each player's data is independent
}
```

**Heatmap Grid Coordinates**:
- Origin (0,0) is bottom-left (blue goal corner)
- Row 0 = blue goal line, Row 19 = orange goal line
- Col 0 = left side wall, Col 15 = right side wall
- Each cell is ~512 x 512 field units

#### Trends

**Data Source**: Trends query `player_game_stats` directly (not `daily_stats`), aggregating per day. This allows trending any metric in the catalog, not just the subset materialized in `daily_stats`. For performance, results are cached with 5-minute TTL.

```
GET /trends?metric=bcpm&period=30d&playlist=DOUBLES
GET /trends?metric=avg_boost&period=90d

Response: {
    "metric": "bcpm",
    "metric_display": "Boost/Min",
    "period": "30d",
    "playlist": "DOUBLES",
    "data_points": [
        {"date": "2024-12-01", "value": 280.5, "games": 8},
        {"date": "2024-12-02", "value": 295.2, "games": 12},
        ...
    ],
    "summary": {
        "start_value": 280.5,
        "end_value": 310.2,
        "change": 29.7,
        "change_pct": 10.6,
        "trend": "improving"
    },
    "benchmark": {  // If loaded for target rank
        "rank": "GC1",
        "median": 320
    }
}
```

#### Benchmarks
```
GET /benchmarks?playlist=DOUBLES&rank=GC1
Response: {
    "playlist": "DOUBLES",
    "rank": "GC1",
    "source": "ballchasing.com",
    "source_date": "2024-12-01",
    "metrics": {
        "bcpm": {"median": 320, "p25": 280, "p75": 360, "elite": 400},
        "avg_boost": {"median": 45, "p25": 38, "p75": 52, "elite": 58},
        ...
    }
}

GET /compare?playlist=DOUBLES&period=30d
Response: {
    "period": "30d",
    "games_analyzed": 45,
    "target_rank": "GC1",
    "comparison": [
        {
            "metric": "bcpm",
            "my_avg": 285,
            "benchmark_median": 320,
            "gap": -35,
            "gap_pct": -10.9,
            "status": "behind"  // behind, on_par, ahead
        },
        ...
    ],
    "summary": {
        "ahead": 8,
        "on_par": 5,
        "behind": 12
    }
}
```

#### Players
```
GET /players?tagged=true
GET /players?min_games=5&sort=-games_with_me

Response: {
    "total": 23,
    "items": [
        {
            "player_id": "steam:12345",
            "display_name": "DuoPartner",
            "is_tagged_teammate": true,
            "games_with_me": 47,
            "win_rate_together": 58.5,
            "last_seen": "2024-12-23T20:30:00Z"
        }
    ]
}

GET /players/{player_id}
Response: {
    "player": {...},
    "games_together": 47,
    "win_rate_together": 58.5,
    "recent_games": [...],  // Last 10 games together
    "tendencies": {
        "aggression_score": 65.2,
        "challenge_rate": 4.8,
        ...
    },
    "your_adaptation": {
        "score": 72,
        "issues": ["..."]
    }
}

POST /players/{player_id}/tag
Body: {"is_tagged_teammate": true, "notes": "Main 2s partner"}
Response: {"success": true}
```

#### Weaknesses
```
GET /weaknesses?playlist=DOUBLES&period=30d
Response: {
    "period": "30d",
    "games_analyzed": 45,
    "min_games_required": 20,
    "target_rank": "GC1",
    "weaknesses": [
        {
            "metric": "avg_boost",
            "severity": "high",
            "my_avg": 38.5,
            "benchmark_median": 45,
            "gap": -6.5,
            "gap_pct": -14.4,
            "z_score": -1.2,
            "pattern_evidence": "12% lower in losses than wins",
            "recommendation": "Focus on small pad collection"
        }
    ],
    "strengths": [
        {
            "metric": "first_to_ball_pct",
            "my_avg": 58.2,
            "benchmark_median": 52,
            "gap": 6.2,
            "status": "above_elite"
        }
    ]
}
```

#### Patterns (Win/Loss Analysis)
```
GET /patterns?playlist=DOUBLES&period=50g
Response: {
    "period": "last 50 games",
    "games": 50,
    "wins": 28,
    "losses": 22,
    "significant_patterns": [
        {
            "metric": "avg_boost",
            "direction": "higher_in_wins",
            "win_avg": 48.2,
            "loss_avg": 41.5,
            "effect_size": 0.52,
            "insight": "You maintain 16% higher average boost in wins"
        }
    ]
}
```

### Error Response Format
```json
{
    "error": "not_found",
    "message": "Replay abc123 not found",
    "details": {"replay_id": "abc123"}
}
```

---

## UI/UX Requirements

### Views

#### 1. Dashboard
- **Header**: Current rank goal (from config), overall win rate
- **Quick stats cards**: Games today, win rate today, current streak
- **Recent games list**: Last 10 games with result, key stats, clickable to deep-dive
- **Trend sparklines**: Key metrics over last 7 days (bcpm, win rate, avg boost)
- **Focus areas**: Top 3 weaknesses with severity badges
- **vs GC snapshot**: How many metrics ahead/behind target rank

**States**: Loading (skeleton), Empty (no games yet, show setup guide), Populated

#### 2. Day View
- **Date picker**: Calendar widget, prev/next day arrows
- **Day summary card**: Games played, W/L record, win rate, total time played
- **Games list**: Each game as expandable card
  - Collapsed: Result badge, score, map, duration, 4 key stats
  - Expanded: Full stats, link to deep-dive
- **Day patterns**: "Today you did X differently than usual" (if significant)

**States**: Loading, No games on date (show empty state with date), Populated

#### 3. Trends View
- **Controls bar**:
  - Metric dropdown (grouped by category: Boost, Movement, etc.)
  - Time range: 7d / 30d / 90d / All time
  - Playlist filter: All / 2v2 / 3v3 / 1v1
- **Main chart**: Line chart with data points, trendline
- **Benchmark overlay**: Toggle to show GC benchmark as horizontal line
- **Stats panel**: Start value, end value, change %, trend direction

**States**: Loading, Insufficient data (<5 data points), Populated

#### 4. Comparison View
- **Controls**:
  - Benchmark rank selector: C3 / GC1 / GC2 / GC3 / SSL
  - Analysis period: 7d / 30d / 90d
- **Category tabs**: All / Boost / Movement / Positioning / Challenges / Mechanics
- **Comparison table**: Metric | Your Avg | Benchmark | Gap | Status (color-coded)
- **Gap chart**: Horizontal bar chart showing all gaps, sorted by magnitude
- **Summary card**: X ahead, Y on par, Z behind

**States**: Loading, No benchmarks (show import prompt), Populated

#### 5. Replay Deep-Dive
- **Header**: Map, date, playlist, result, score, duration
- **Players section**: Cards for all players (me highlighted)
  - Each card: Name, team color, key stats
- **Events timeline**: Vertical scrollable timeline
  - Filter buttons: All / Goals / Demos / Kickoffs
  - Each event: Timestamp, type icon, description
- **Heatmaps section**: Tab switcher for Position / Touch / Boost heatmaps
- **Insights panel**: Pipeline-generated insights for this game

**States**: Loading, Not found (404 page), Populated

#### 6. Focus Areas View
- **Priority section**: "This week, focus on:" with top 1-2 critical/high items
- **Weaknesses list**: Cards sorted by severity
  - Each card: Metric name, your value vs target, gap visualization, severity badge
  - Expandable: Pattern evidence, trend chart, drill suggestions
- **Strengths section**: Collapsible list of things going well
- **Insufficient data banner**: If <20 games, show prompt to play more

**States**: Loading, Insufficient data, Populated

#### 7. Players View
- **Search/Filter bar**:
  - Text search by display name
  - Filter: All / Tagged Teammates / Frequent (5+ games)
  - Sort: Games together / Win rate / Last seen
- **Player list**: Cards for each player
  - Display name, platform badge, games together, win rate together
  - Tagged badge for marked teammates
  - Last seen date
  - Click to expand details
- **Player detail panel** (expanded or side panel):
  - Tendencies radar chart (aggression, challenge rate, first man, etc.)
  - Your adaptation score with issues
  - Recent games together (last 10)
  - Quick actions: Tag/Untag, Add notes
- **Name collision handling**:
  - If multiple players share display name, show platform prefix
  - Group by platform_id, not display_name

**States**: Loading, No players yet, Populated

**Tagging workflow**:
1. User searches or browses player list
2. Clicks player card to expand
3. Clicks "Tag as Teammate" button
4. Optionally adds notes (e.g., "Main 2s partner")
5. Tagged players appear with badge and can be filtered

### Design Principles
- **Dark mode default**: Easier on eyes during gaming sessions
- **Information density**: Show lots of data but keep it scannable
- **Quick navigation**: Sidebar with all views, get anywhere in 1 click
- **Color coding**: Green = good/ahead, Yellow = warning/on-par, Red = bad/behind
- **Responsive**: Optimized for laptop screens (1280px+), no mobile needed

---

## Acceptance Criteria

### Configuration
- [ ] `rlcoach config --init` creates template config file
- [ ] `rlcoach config --validate` checks config and reports errors
- [ ] Missing or invalid config prevents service startup with clear error message
- [ ] Player identity correctly matches across platform ID and display name fallback

### Ingestion
- [ ] New replays in watch folder are detected within 60 seconds
- [ ] File stability check waits for sync to complete before parsing
- [ ] Replays are parsed and stored in both SQLite and JSON
- [ ] Duplicate replays (same replay_id or file_hash) are skipped with log message
- [ ] Parse failures are logged with file path but don't crash the service
- [ ] Player identity is resolved correctly; unmatched replays are skipped with warning
- [ ] `play_date` uses configured timezone for day boundary
- [ ] `daily_stats` table updates incrementally after each ingestion

### Data Layer
- [ ] Queries for last 30 days of games complete in <500ms (warm cache, 1000 replays)
- [ ] Full JSON reports load in <1s
- [ ] Daily stats recalculated correctly when games are added
- [ ] `rlcoach benchmarks import` successfully loads benchmark JSON
- [ ] Benchmark import validates metric names against catalog

### API
- [ ] All endpoints return valid JSON with correct content-type
- [ ] List endpoints support limit, offset, sort parameters
- [ ] Date filtering works correctly with configured timezone
- [ ] Errors return appropriate HTTP status codes and error objects
- [ ] Player tagging via POST persists across service restarts
- [ ] `/patterns` endpoint returns empty patterns gracefully when <20 games
- [ ] `/compare` endpoint returns 404 when benchmarks not loaded

### GUI
- [ ] Dashboard loads in <2s with 500+ games in database
- [ ] All views have skeleton loading states
- [ ] Empty states provide guidance (setup config, import benchmarks, play games)
- [ ] Charts render smoothly with 90 days of daily data points
- [ ] Navigation between views preserves filter state where logical
- [ ] Date picker respects configured timezone
- [ ] Replay deep-dive shows all events with correct timestamps

### Coaching Skill
- [ ] "Analyze today" returns structured coaching output with all 4 phases
- [ ] Skill correctly queries API endpoints (test with mock server)
- [ ] Skill reads JSON reports for detailed event analysis
- [ ] "Why did I lose" references specific timestamps from the replay
- [ ] Web search returns relevant training resources (or graceful fallback)
- [ ] Prescriptions include specific drill names/codes, not generic advice
- [ ] Skill correctly interprets pattern analysis results

### Patterns & Weaknesses
- [ ] Pattern analysis requires minimum 20 games, 5 wins, 5 losses
- [ ] Effect size calculation matches documented formula
- [ ] Weakness severity levels assigned correctly per documented thresholds
- [ ] Strengths are identified for metrics above benchmark

---

## Edge Cases

### Configuration
- **No config file**: Service refuses to start, prompts for `rlcoach config --init`
- **Invalid platform ID format**: Config validation fails with specific error
- **Player not found in replay**: Skip replay, log warning with file path

### Ingestion
- **Corrupted replay file**: Log error with file path, skip, don't retry unless file changes
- **Dropbox conflict copy**: Different file_hash but same replay_id → skip duplicate
- **Replay from unsupported mode**: Parse what we can, flag with quality warning
- **Very old replay**: Parse normally, note schema version in quality block
- **Replay mid-sync**: File size check prevents premature parsing
- **Watch folder doesn't exist**: Log error, retry every 60s, don't crash

### Data
- **No games for date range**: Return empty results with `total: 0`, not error
- **Missing benchmarks for metric**: Show "no benchmark" in comparison, skip in weakness detection
- **Metric not applicable to mode**: `third_man_pct` is NULL for 1v1/2v2, exclude from analysis
- **All wins or all losses**: Skip pattern analysis, return `"insufficient_variance": true`
- **Player appears on both teams**: Log warning, use first appearance (shouldn't happen)
- **Timezone change**: `play_date` uses timezone at ingestion time, won't retroactively change

### Coaching
- **Insufficient data for trends**: "Need more games for trend analysis" (min 5 data points)
- **No benchmarks loaded**: "Benchmarks not configured, showing relative analysis only"
- **Web search fails**: "Couldn't find specific resources, here's general advice for [skill]"
- **User asks about game not in system**: "I don't have that replay. Check if it's in the watch folder."
- **Teammate not found**: "I don't have data on [name]. Have you played with them recently?"

### GUI
- **Very long session (50+ games in a day)**: Virtual scrolling, load more on scroll
- **Extreme outlier stats**: Flag outliers in UI, don't skew trend lines
- **No internet connection**: GUI works fully offline, web search in coaching fails gracefully
- **Database locked**: Retry with backoff, show "syncing" indicator

---

## Non-Functional Requirements

### Performance

| Metric | Target | Measurement Conditions |
|--------|--------|----------------------|
| Dashboard load | <2s | 500 replays, warm cache, M1 MacBook |
| API aggregates | <500ms | 30-day query, 1000 replays |
| Full report load | <1s | Single replay JSON (~500KB) |
| Trend chart render | <500ms | 90 days of daily data points |
| Ingestion throughput | 50 replays in <5min | Batch import, no UI queries |
| Database size | <1GB for 10,000 replays | SQLite + JSON reports |

### Reliability
- Ingestion failures don't lose data (source files remain in watch folder)
- Database corruption recovery via re-ingestion from JSON reports
- Graceful degradation if watch folder temporarily unavailable
- Background ingestion doesn't block API responses

### Security
- Binds to `localhost` only (no external network access)
- No authentication needed (single user, local machine)
- No sensitive data in replay files (just gameplay)
- JSON reports stored in user-accessible location

### Maintainability
- Modular architecture (ingestion, API, GUI can evolve independently)
- Typed Python with Pydantic models
- Typed TypeScript frontend
- Comprehensive logging at DEBUG, INFO, WARNING, ERROR levels
- All SQL queries parameterized (no injection risk)

### Extensibility
- Metric Catalog is single source of truth for adding new metrics
- Benchmark import format allows easy updates from new sources
- API versioned (`/api/v1`) for future breaking changes
- Skill can be updated independently of backend

---

## Appendix A: Coaching Skill Specification

The Claude Code coaching skill will be created as `skills/rl-coach/SKILL.md`.

### Frontmatter
```yaml
name: rl-coach
description: |
  Rocket League coaching skill for analyzing replays and improving gameplay.
  Use when the user asks about: analyzing games, coaching, practice recommendations,
  comparing stats to GC, understanding losses/wins, or improving at Rocket League.
  Triggers: "analyze today", "why did I lose", "what should I practice",
  "compare my X to GC", "coaching session", "what's holding me back"
```

### Capabilities
- Query RLCoach API at `localhost:8000/api/v1`
- Read full JSON reports from configured `reports_dir`
- Access GC benchmark data via API
- Search web for practice resources
- Follow structured coaching methodology

### Coaching Loop
1. **Analysis**: Summarize what happened (games played, results, notable events)
2. **Diagnosis**: Identify what went right, wrong, and stood out
3. **Comparison**: Compare against win/loss patterns and GC benchmarks
4. **Prescription**: Recommend specific practice with searched resources

### Web Search Strategy
When prescribing drills:
1. Search for: `"rocket league [skill] training pack code 2024"`
2. Search for: `"rocket league [skill] workshop map steam"`
3. Search for: `"rocket league [skill] tutorial youtube"`
4. Validate results are relevant before recommending
5. Fallback: Provide general practice advice if search fails

### Reference Data
- Benchmark thresholds loaded from API
- Metric catalog for understanding stats
- Common weakness → drill mappings

---

## Appendix B: Directory Structure

```
~/.rlcoach/
├── config.toml           # User configuration
├── rlcoach.db            # SQLite database
├── data/
│   └── daily_cache.json  # Optional precomputed aggregates
├── reports/
│   ├── 2024-12-23/
│   │   ├── abc123.json   # Full replay report
│   │   └── def456.json
│   └── ...
└── logs/
    └── rlcoach.log       # Rotating log file
```

---

## Appendix C: CLI Commands

```bash
# Configuration
rlcoach config --init              # Create template config
rlcoach config --validate          # Validate current config
rlcoach config --show              # Display current config

# Ingestion
rlcoach ingest                     # Process all new replays in watch folder
rlcoach ingest path/to/replay.replay  # Process single replay
rlcoach ingest --watch             # Run watch folder service

# Benchmarks
rlcoach benchmarks import FILE     # Import benchmarks from JSON
rlcoach benchmarks list            # List loaded benchmarks
rlcoach benchmarks export FILE     # Export current benchmarks

# Database
rlcoach db stats                   # Show database statistics
rlcoach db rebuild-daily           # Rebuild daily_stats table
rlcoach db vacuum                  # Optimize database

# Server
rlcoach serve                      # Start API + GUI server
rlcoach serve --api-only           # Start API server only
rlcoach serve --port 8080          # Custom port

# Analysis (CLI output, no GUI needed)
rlcoach analyze today              # Quick analysis of today's games
rlcoach analyze --date 2024-12-23  # Analyze specific date
rlcoach compare                    # Compare to benchmarks
```

---

## Appendix D: Future Enhancements

### 2D Field Visualization
- Render car and ball positions at key moments on field diagram
- Show movement paths leading up to mistakes
- Interactive scrubbing through events
- Export as image for sharing

### Ballchasing Integration
- Auto-upload replays to ballchasing.com
- Generate viewer links for specific timestamps
- Pull additional stats not in local analysis
- Sync benchmarks from ballchasing aggregate data

### Cloud Deployment
- Deploy FastAPI to Railway/Fly.io
- Deploy React to Vercel/Netlify
- Add authentication (single user or team)
- Sync replays directly from gaming PC via API
- Mobile-friendly responsive design
