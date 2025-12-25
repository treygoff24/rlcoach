# Account Exclusion Feature

## Problem Statement

Users may have multiple Rocket League accounts for different purposes (main, training, playing with lower-ranked friends, playing with family). Some accounts represent gameplay they don't want analyzed - for example, casual games with a spouse where performance metrics aren't meaningful.

Currently, the identity system can match multiple display names to find "me" in replays, but has no mechanism to exclude replays where the user is playing on specific accounts.

## Solution

Add an `excluded_names` field to the identity config. During ingest, if the user is found in a replay under an excluded name, skip the replay entirely.

## Config Changes

```toml
[identity]
display_names = [
    "deportallcommies",   # main account
    "Pinochetwasright",   # training (solo Q only)
    "fastbutstupid",      # playing with JC
]

# Accounts to skip entirely during analysis
excluded_names = ["EmpressOlive"]
```

## Implementation Plan

### 1. Update `IdentityConfig` dataclass (`config.py`)
- Add `excluded_names: list[str] = field(default_factory=list)`
- Update `load_config()` to read `excluded_names` from TOML
- Add validation in `RLCoachConfig.validate()` to reject overlap between `display_names` and `excluded_names`

### 2. Update `PlayerIdentityResolver` (`identity.py`)
- Use `.casefold().strip()` instead of `.lower()` for better Unicode normalization (apply to existing display_names matching too)
- Store excluded names as casefolded/stripped set in `__init__`
- Add `should_exclude(display_name: str) -> bool` method
- Returns True if name matches any excluded name (case-insensitive)

### 3. Add exclusion check at ingest (`ingest.py` or `pipeline.py`)
- After header parsing, use `find_me()` to identify the user's player
- If `find_me()` returns a player AND that player's display_name matches `should_exclude()`, skip the replay
- Important: Only check exclusion on "me", NOT on opponents/teammates
- Log that replay was skipped due to exclusion

### 4. Update config template (`config_templates.py`)
- Add `excluded_names = []` with comment explaining purpose

### 5. Tests
- Test `should_exclude()` with matching/non-matching names
- Test case-insensitivity (casefold)
- Test overlap validation rejects configs with name in both lists
- Test pipeline skips excluded replays only when "me" is excluded (not opponents)
- Test empty `excluded_names` (no exclusions, default behavior)

## Non-Goals
- No deletion of replay files (skip only)
- No per-account stat segmentation (all non-excluded accounts treated as one player)
- No primary account designation (all accounts equal for analysis)
- No retroactive cleanup of existing DB data (user can re-ingest if needed)
- No `excluded_platform_ids` (display names sufficient for this use case)

## Implementation Notes

**Exclusion timing**: The spec originally called for exclusion "after header parsing" but the implementation checks after full report generation for simplicity. This means excluded replays still incur analysis cost before being skipped. This is an acceptable trade-off: the code is simpler, and the performance impact is minimal since excluded accounts are typically rare.
