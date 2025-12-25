# src/rlcoach/config_templates.py
"""Configuration file templates."""

CONFIG_TEMPLATE = """# RLCoach Configuration
# Edit this file with your player info before running RLCoach.

[identity]
# Primary player identification - at least one required
# Platform IDs are checked first, then display_names as fallback
# Format: "platform:id" where platform is steam, epic, psn, xbox, or switch
platform_ids = [
    # "steam:76561198012345678",
    # "epic:abc123def456"
]
# Fallback display names (case-insensitive, used if platform_id not found)
display_names = ["YourGamertag"]
# Accounts to exclude from analysis entirely (replays skipped, not deleted)
# Use for casual/family accounts you don't want in your stats
excluded_names = []

[paths]
# Watch folder for incoming replays (Dropbox sync target)
watch_folder = "~/Dropbox/RocketLeague/Replays"
# Where to store processed data (SQLite database)
data_dir = "~/.rlcoach/data"
# Where to store JSON reports
reports_dir = "~/.rlcoach/reports"

[preferences]
# Primary playlist for comparisons (DOUBLES, STANDARD, DUEL)
primary_playlist = "DOUBLES"
# Target rank for benchmark comparisons (C2, C3, GC1, GC2, GC3, SSL)
target_rank = "GC1"
# Timezone for day boundary calculation (IANA format)
# Uses system timezone if not set
# timezone = "America/Los_Angeles"

[teammates]
# Tagged teammates for tracking (display_name = "optional notes")
[teammates.tagged]
# "DuoPartnerName" = "Main 2s partner"
"""
