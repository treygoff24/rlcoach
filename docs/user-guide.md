# RLCoach User Guide

Welcome to RLCoach, your AI-powered Rocket League coaching platform.

## Getting Started

### Creating an Account

1. Visit [rlcoach.gg](https://rlcoach.gg)
2. Click "Sign In" in the navigation bar
3. Choose your preferred sign-in method:
   - **Discord** (recommended for RL players)
   - **Google**
4. Accept the Terms of Service
5. Complete the OAuth flow

### Dashboard Overview

After signing in, you'll land on your personal dashboard with:

- **Stats Overview**: Your recent performance metrics
- **Trends Chart**: Performance over time
- **Quick Actions**: Upload replays, start coaching, view replays
- **Recent Replays**: Your latest uploaded games

## Uploading Replays

### Finding Your Replay Files

Rocket League replays are stored at:

- **Windows**: `%USERPROFILE%\Documents\My Games\Rocket League\TAGame\Demos`
- **macOS**: `~/Library/Application Support/Rocket League/TAGame/Demos`
- **Linux**: `~/.local/share/Rocket League/TAGame/Demos`

### Upload Methods

1. **Drag & Drop**: Drag `.replay` files directly onto the upload zone
2. **Click to Browse**: Click the upload zone to open a file picker
3. **Bulk Upload**: Select multiple files at once (up to 10)

### Processing

After upload, replays are processed in the background:
- Header extraction (immediate)
- Full frame analysis (1-2 minutes)
- AI coaching preparation (Pro only)

You'll see a notification when processing completes.

## Viewing Replays

### Replay Library

Navigate to **Replays** in the sidebar to see all your games.

- Sort by date, map, or rank
- Filter by game mode (1v1, 2v2, 3v3)
- Search by player name

### Replay Details

Click any replay to view detailed analysis:

- **Overview**: Game summary, score, duration
- **Performance**: Your key stats vs opponents
- **Positioning**: Field position heatmaps
- **Boost**: Boost management analysis
- **Mechanics**: Detected mechanical plays
- **Timeline**: Key events throughout the game

## AI Coach (Pro)

The AI Coach is available with a Pro subscription ($10/month).

### Starting a Coaching Session

1. Navigate to **Coach** in the sidebar
2. Select a replay to analyze
3. Ask questions about your gameplay

### Example Questions

- "What should I improve from this game?"
- "How was my boost management?"
- "Did I rotate properly?"
- "What mistakes did I make in defense?"
- "How can I improve my kickoffs?"

### Saving Notes

Click "Save as Note" on any AI response to keep it for later reference.

### Token Budget

Pro users get 100,000 tokens per month for AI coaching. Token usage is shown in Settings.

## Sessions

Sessions group related replays together (games played within 30 minutes).

Navigate to **Sessions** to:
- Review session summaries
- Track performance trends within sessions
- Get session-level insights

## Settings

### Account

- View your profile information
- See subscription status
- Export your data
- Delete your account

### Subscription

- View current plan (Free/Pro)
- Upgrade to Pro
- Manage billing through Stripe

### Data Export

Request a JSON export of all your data:
- Account information
- Replay metadata
- Analysis results
- Coach conversations
- Notes

### Account Deletion

Request account deletion:
- 30-day grace period to cancel
- All personal data anonymized after deletion
- You'll receive email confirmation

## Troubleshooting

### Replay Won't Upload

- Check file size (max 10MB)
- Ensure it's a `.replay` file
- Try a different browser
- Check your internet connection

### Processing Taking Too Long

Processing typically takes 1-2 minutes. If longer:
- Refresh the page
- Check the replay status in your library
- Large replays (overtime games) take longer

### AI Coach Not Responding

- Verify you have an active Pro subscription
- Check your token budget in Settings
- Try refreshing the page
- Select a specific replay for context

## Support

Need help? Contact us:

- Email: support@rlcoach.gg
- Discord: [RLCoach Community](https://discord.gg/rlcoach)

For privacy concerns: privacy@rlcoach.gg
