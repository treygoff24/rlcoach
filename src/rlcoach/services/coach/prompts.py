# src/rlcoach/services/coach/prompts.py
"""System prompts for AI Coach."""


SYSTEM_PROMPT = """You are an expert Rocket League coach powered by Claude Opus 4.5 with extended thinking. You have deep knowledge of all aspects of Rocket League gameplay and access to the player's replay analysis data.

## Your Expertise

**Mechanics:**
- Ground play: power shots, dribbling, flicks, 50/50s
- Aerial play: fast aerials, air rolls, double touches, flip resets
- Advanced: wave dashes, ceiling shots, musty flicks, breezies
- Recoveries: landing on wheels, momentum preservation

**Game Sense & Positioning:**
- Rotation: proper 3s rotation, 2s positioning, 1s mindset
- Shadow defense: when to challenge vs when to shadow
- Boost management: small pad pathing, boost denial
- Reading the play: predicting opponents, ball prediction

**Team Play:**
- Passing: infield passes, backboard setups
- Communication: "I got it", "All yours", "Bumping"
- Trust: knowing when to go and when to let teammates play

## How You Coach

1. **Use Extended Thinking**: Take time to analyze the player's data and situation before responding. Your thinking process helps you give better advice.

2. **Focus on 1-2 Key Improvements**: Don't overwhelm with feedback. Identify the highest-impact changes.

3. **Be Specific**: When giving advice, reference specific plays, stats, or patterns from their data when available.

4. **Be Encouraging but Honest**: Celebrate progress while being direct about areas that need work.

5. **Ask Clarifying Questions**: If you need more context, ask. Understanding their goals helps you coach better.

6. **Use RL Terminology**: Players understand the lingo. Use it.

## Your Tools

You have access to tools that let you query the player's replay data:
- get_recent_games: Fetch their recent matches with stats
- get_stats_by_mode: Aggregate stats by playlist (1v1, 2v2, 3v3)
- get_game_details: Deep dive into a specific replay
- get_rank_benchmarks: Compare their stats to their rank's average

Use these tools to provide data-driven coaching rather than generic advice.

## Your Communication Style

- Direct and concise
- Uses Rocket League terminology naturally
- Provides actionable feedback with specific examples
- Maintains a coaching personality - supportive but professional
- Adapts to the player's skill level and goals"""


def build_system_prompt(
    user_notes: list[str] | None = None,
    player_name: str | None = None,
    current_rank: str | None = None,
) -> str:
    """Build the complete system prompt with context.

    Args:
        user_notes: Previous coaching notes for this player
        player_name: Player's display name
        current_rank: Player's current rank (e.g., "Diamond II")

    Returns:
        Complete system prompt string
    """
    prompt = SYSTEM_PROMPT

    # Add player context
    if player_name or current_rank:
        prompt += "\n\n## Current Player Context\n"
        if player_name:
            prompt += f"- Player: {player_name}\n"
        if current_rank:
            prompt += f"- Rank: {current_rank}\n"

    # Add previous coaching notes
    if user_notes:
        notes_text = "\n".join(f"- {note}" for note in user_notes[:10])
        prompt += f"\n\n## Previous Coaching Notes\n{notes_text}"

    return prompt


def get_tool_descriptions() -> list[dict]:
    """Get Claude tool definitions for coach data access."""
    return [
        {
            "name": "get_recent_games",
            "description": "Get the player's recent games with stats like goals, assists, saves, shots, and more.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "limit": {
                        "type": "integer",
                        "description": "Number of recent games to fetch (default: 10, max: 50)",
                        "default": 10,
                    },
                    "playlist": {
                        "type": "string",
                        "description": "Filter by playlist (optional): 'duel', 'doubles', 'standard', 'rumble', etc.",
                    },
                },
                "required": [],
            },
        },
        {
            "name": "get_stats_by_mode",
            "description": "Get aggregated statistics for a specific game mode/playlist.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "mode": {
                        "type": "string",
                        "description": "Game mode: 'duel' (1v1), 'doubles' (2v2), 'standard' (3v3), or 'all'",
                        "enum": ["duel", "doubles", "standard", "all"],
                    },
                    "days": {
                        "type": "integer",
                        "description": "Number of days to analyze (default: 30)",
                        "default": 30,
                    },
                },
                "required": ["mode"],
            },
        },
        {
            "name": "get_game_details",
            "description": "Get detailed analysis of a specific game/replay including mechanics, positioning, and play-by-play.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "game_id": {
                        "type": "string",
                        "description": "The unique identifier of the game/replay to analyze",
                    },
                },
                "required": ["game_id"],
            },
        },
        {
            "name": "get_rank_benchmarks",
            "description": "Get average stats for a rank to compare against the player's performance.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "rank": {
                        "type": "string",
                        "description": "Rank to compare against (e.g., 'Diamond II', 'Champion I')",
                    },
                    "mode": {
                        "type": "string",
                        "description": "Game mode for benchmarks",
                        "enum": ["duel", "doubles", "standard"],
                        "default": "standard",
                    },
                },
                "required": ["rank"],
            },
        },
        {
            "name": "save_coaching_note",
            "description": "Save a coaching observation or insight for future reference. Use this to note patterns, strengths, weaknesses, or goals.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "content": {
                        "type": "string",
                        "description": "The coaching note to save",
                    },
                    "category": {
                        "type": "string",
                        "description": "Category of the note",
                        "enum": ["strength", "weakness", "goal", "observation"],
                    },
                },
                "required": ["content", "category"],
            },
        },
    ]
