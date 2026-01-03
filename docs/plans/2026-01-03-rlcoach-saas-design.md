# rlcoach SaaS Product Design

**Status:** APPROVED (Codex reviewed, critical issues addressed)
**Date:** 2026-01-03
**Next Step:** Create implementation plan

---

## Vision

Turn rlcoach from a CLI tool into a SaaS product: the best AI Rocket League coach to ever exist.

**Core loop:** Land → Free dashboard (wow factor) → Upload replays → Explore data → Pay for AI coach → Get coached

**Differentiator:** Parser extracts granular mechanics data that competitors don't have. Dashboard excellence is the marketing funnel. Product sells itself.

---

## Business Model

| Tier | Price | What's included |
|------|-------|-----------------|
| **Free** | $0 | Unlimited replay uploads, full dashboard access |
| **Pro** | $10/month | AI coach with Claude Opus 4.5, extended thinking |

**Why unlimited free replays:** Parsing is cheap. The dashboard is the marketing. Let users fall in love with the data, then sell them the coach.

---

## Tech Stack

| Component | Choice | Rationale |
|-----------|--------|-----------|
| Frontend | Next.js | React ecosystem, best UI libraries for dashboard wow-factor |
| Backend | Python FastAPI | Existing pipeline, PyO3 Rust bindings already work |
| Database | PostgreSQL | Free, handles concurrent writes, no migration pain |
| Hosting | Single Hetzner box | Simplicity. Monolith. Scale later if needed. |
| Auth | NextAuth.js | Free, self-hosted, no vendor lock-in |
| OAuth | Discord, Steam, Google, Epic | Where RL players live |
| Payments | Stripe Checkout + Portal | Minimal code, handles edge cases |
| CDN/SSL | Cloudflare free tier | DNS, SSL, CDN, DDoS — zero maintenance |
| Backups | pg_dump + Backblaze B2 | Daily dumps, offsite sync, ~$5/TB/month |

---

## Dashboard Structure

### Pages (7 total)

| Page | Purpose |
|------|---------|
| **Home** | Hero view: mechanics breakdown with rank comparisons + topline stats |
| **Replay List** | All uploaded replays, sortable/filterable |
| **Replay Detail** | Deep dive on single game, tabbed interface |
| **Session History** | Replays grouped by play session |
| **Trends** | Stats over time with flexible axis (session/time/replay) |
| **Comparison** | You vs your rank, you vs yourself over time |
| **Settings** | Profile, linked accounts, preferences |

### Home Page (Hero View)

**Primary:** Mechanics breakdown with rank comparisons
- "You hit 47 flip resets this season — top 3% for Diamond"
- Visual, shareable, demonstrates unique value

**Secondary:** Topline stats with visual hierarchy
- Core fundamentals large/prominent: Goals, assists, saves, shots, demos
- Efficiency metrics smaller/secondary: Boost/100, avg speed, time supersonic, third splits

### Replay Detail Tabs (7 tabs)

| Tab | Content |
|-----|---------|
| **Overview** | Game result, scoreboard, hero stats, quick highlights |
| **Mechanics** | Detected mechanics with counts, timestamps, success rates |
| **Boost** | Pickups, efficiency, starves, time at 0/100 |
| **Positioning** | Heatmaps, avg position, rotation compliance, third splits |
| **Timeline** | Interactive event timeline, expandable moments |
| **Defense** | Saves, clears, shadow defense, last defender time |
| **Offense** | Shots, xG, assists, passes, pressure time |

Each tab must look crispy and sharp. Clean data visualization, thoughtful hierarchy.

### Trends Page

**Axis options (user toggles):**
- Session-based (default) — each play session is a data point
- Time-based — days/weeks/months on X-axis
- Replay-based — every replay is a dot (highest granularity)

### Comparison Page

**Two modes (no social features):**
1. **Rank comparison:** Your stats vs your rank average, vs next rank up
2. **Self comparison:** Current period vs previous (this week vs last week, this season vs last)

---

## Upload Flow

**Method:** Manual drag-drop only for V1. BakkesMod plugin planned post-launch.

**Experience:**
1. Drop files anywhere on dashboard
2. Progress bar for each file
3. Immediate preview of key stats as each replay finishes
4. Instant gratification before navigating anywhere

### Rate Limits & Resource Protection

**Upload limits:**
- Max 50 replays per upload batch
- Max 10 MB per file (replays are typically 1-2 MB)
- Max 100 uploads per hour per user
- File type validation: must be valid .replay format (magic bytes check)

**Processing architecture:**
- Uploads go to temporary storage first
- Background worker (Celery/RQ) processes queue
- Immediate preview = first N replays processed synchronously, rest queued
- Progress via WebSocket or polling

**Resource protection:**
- Parser runs in subprocess with timeout (30s per replay)
- Memory limit per parse job (512 MB)
- Queue backpressure: reject new uploads if queue > 1000 items
- Disk monitoring: alert at 80%, reject uploads at 90%

**Storage management:**
- Deduplicate by replay match_id (same game = one copy)
- Original .replay files stored on disk
- Move to B2 after 30 days (cold storage)
- User can delete their replays (cascades to parsed data)

---

## Data Model

### User Identity

- OAuth-linked platform IDs (Steam, Discord, Google, Epic)
- Auto-match replays to account based on platform ID in replay data
- Manual claiming for alt accounts and old replays

### Session Detection

- Replays within X minutes = same session
- Default gap: 30 minutes
- Tunable in settings (user can adjust threshold)

### Storage

- Original .replay files on disk (or B2 if disk fills)
- Parsed data in PostgreSQL
- Replays are small (~1-2MB each)

---

## AI Coach

### Model

Claude Opus 4.5 with extended thinking. Genuinely thoughtful coaching.

### Usage Limits & Cost Controls

**Token-budget model (not conversation count):**
- Monthly budget: 150K tokens (input + output combined, thinking excluded)
- Per-request limits:
  - Input: 16K tokens max (system prompt + history + tool results)
  - Output: 8K tokens max
  - Extended thinking: 32K tokens budget (not counted against user quota)
- Soft limit at 80%: "You've used 80% of your monthly coaching budget"
- Hard limit at 100%: "Monthly limit reached, resets in X days"

**Context management:**
- Truncate conversation history to fit input limit (keep recent turns)
- Tool results summarized if exceeding 4K tokens
- System prompt: ~2K tokens (coaching instructions + user notes)
- Efficient context = more conversations within budget

**Cost math at $10/mo (conservative):**
- Opus 4.5: ~$15/1M input, ~$75/1M output, ~$15/1M thinking tokens
- Stripe: 2.9% + $0.30 = $0.59/transaction
- 150K token budget at worst-case output-heavy (40% input, 60% output):
  - 60K input ($0.90) + 90K output ($6.75) = ~$7.65/user/month
  - Plus ~50K avg thinking tokens = ~$0.75
  - Total API cost: ~$8.40/user/month at cap
- Net margin at cap: $10.00 - $8.40 - $0.59 = $1.01
- Median user margin much higher (uses ~50% of budget)

**Expected usage patterns:**
- Light user: 2-3 sessions/month, ~30K tokens = ~$2.50 cost → $6.91 margin
- Medium user: 1-2 sessions/week, ~80K tokens = ~$5.50 cost → $3.91 margin
- Heavy user: hits 150K cap = ~$8.40 cost → $1.01 margin (acceptable)

**Viability notes:**
- Median user profitable; power users near break-even
- If economics don't work at scale, options: raise to $15/mo, lower cap, or use Sonnet for routine queries
- Monitor actual usage in first 3 months, adjust

**Abuse prevention:**
- Rate limit: max 10 requests/hour per user
- Monitor for anomalous usage patterns (automated alerting)
- Token budget enforced server-side before API call

### Interaction Model

**Default:** Chat interface for quick questions

**Optional:** Structured review sessions
- "Let's review my last session"
- Coach walks through specific areas
- Ends with action items

### Personality

**Adaptive.** Coach reads player's tone and preferences over time:
- Some players want blunt feedback
- Others need encouragement
- Starts balanced, learns what resonates

### Data Tools

```
get_recent_games(n)        — Last N games with full stats
get_stats_by_mode(mode)    — Aggregate stats filtered by 1v1/2v2/3v3
get_stats_by_date_range()  — Session-level analysis
get_rank_benchmarks(rank)  — Compare to rank / next rank
get_game_details(game_id)  — Deep dive on one replay
```

### Session Notes

**Collaborative model:**
- Coach saves observations ("struggles with backboard reads")
- User can view all notes
- User can add their own ("I know my left-side aerials are weak")
- User can delete outdated notes
- Notes persist across conversations

### Initial Context

Topline data only: rank, MMR, username, main mode. Coach pulls details on-demand via tools.

---

## Infrastructure

### Hosting

Single Hetzner dedicated box. Monolith:
- Next.js frontend
- FastAPI backend
- PostgreSQL database
- Background worker (replay processing queue)

All on one machine. Scale later if needed.

**Sizing target (Hetzner AX41-NVMe or similar):**
- CPU: 6-core Ryzen (parsing is CPU-bound)
- RAM: 64 GB (PostgreSQL, workers, headroom)
- Disk: 512 GB NVMe (replays + database, cold storage to B2)
- Bandwidth: 1 Gbps unmetered

**Capacity planning:**
- Target: 1000 daily active users, 50 uploads/day average
- Parsing: ~2 seconds/replay → 6-core handles 10+ concurrent parses
- Database: 50K replays × 10 KB parsed data = 500 MB (tiny)
- Replay storage: 50K replays × 2 MB = 100 GB (manageable)

**Overload handling:**
- Queue backpressure (see Upload Flow)
- Cloudflare rate limiting as first layer
- Alert on CPU > 80% sustained, disk > 80%
- Horizontal scale path: separate worker box if needed

### Cloudflare (free tier)

- DNS management
- SSL certificates (auto-renewed)
- CDN caching
- DDoS protection
- Zero maintenance

### Auth Flow

NextAuth.js with four providers:
1. Discord — where RL community lives
2. Steam — primary PC platform
3. Google — fallback/convenience
4. Epic — where RL accounts live (if API allows)

### Auth Architecture (NextAuth ↔ FastAPI)

**Token flow:**
1. User authenticates via NextAuth.js (OAuth providers)
2. NextAuth creates session + JWT with user ID and subscription status
3. Next.js API routes proxy to FastAPI with JWT in Authorization header
4. FastAPI validates JWT signature using shared secret

**FastAPI auth middleware:**
- Verify JWT signature (shared NEXTAUTH_SECRET)
- Extract user_id and subscription_tier from claims
- Gate paid endpoints (AI coach) by checking tier == "pro"
- Return 401 for invalid/expired tokens, 403 for wrong tier

**Why proxy through Next.js:**
- Single origin (no CORS complexity)
- Next.js can add/refresh tokens transparently
- FastAPI never exposed directly to internet
- Simpler Cloudflare/nginx config

**Session storage:**
- NextAuth sessions in PostgreSQL (shared with FastAPI)
- JWT for stateless API calls
- Session refresh on activity, 7-day expiry

### Payments & Subscription Management

**Stripe integration:**
- Stripe Checkout for initial subscription
- Stripe Billing Portal for self-service (cancel, update payment, view invoices)
- One tier: $10/month

**Webhook handling (critical path):**
- Endpoint: `/api/stripe/webhook`
- Verify signature using STRIPE_WEBHOOK_SECRET
- Handle events:
  - `checkout.session.completed` → set user tier to "pro", store subscription_id
  - `customer.subscription.updated` → sync status (active/past_due/canceled)
  - `customer.subscription.deleted` → set user tier to "free"
  - `invoice.payment_failed` → set status to "past_due", email user

**Subscription state in database:**
```
users.subscription_tier: "free" | "pro"
users.subscription_status: "active" | "past_due" | "canceled" | null
users.stripe_customer_id: string
users.stripe_subscription_id: string
users.subscription_period_end: timestamp
```

**Entitlement logic:**
- AI coach access requires: tier == "pro" AND status == "active"
- 3-day grace period for past_due before cutting access
- Immediate access on successful checkout (webhook → database → JWT refresh)

**Token freshness (preventing stale access):**
- JWT lifetime: 15 minutes (short-lived)
- NextAuth silently refreshes token on API calls
- On webhook (cancel/downgrade): update database immediately
- FastAPI checks JWT expiry; stale token = 401 → client refreshes → gets updated tier
- Worst case: 15 minutes of stale access after cancellation (acceptable)

**Edge cases:**
- Failed webhook: Stripe retries for 72 hours; idempotency via subscription_id
- User cancels: Access until period_end, then reverts to free
- Payment failure: Email notification, grace period, then downgrade

### Backups

- Daily pg_dump via cron
- Sync to Backblaze B2
- ~$5/TB/month for offsite storage
- Point-in-time recovery not needed at this scale

---

## V2 Features (Post-Launch)

Explicitly deferred to keep V1 scope tight:

- BakkesMod auto-upload plugin
- Goal setting and tracking
- Training pack / workshop map recommendations
- Friends comparison (social features)
- Public profiles
- Leaderboards

---

## Success Metrics

**Acquisition:**
- Organic signups from Reddit/X sharing
- Dashboard screenshots drive awareness

**Activation:**
- Time to first "wow moment" (< 30 seconds)
- Replay upload completion rate

**Revenue:**
- Free → paid conversion rate
- Monthly recurring revenue
- Churn rate

---

## Design Principles

1. **Dashboard is marketing** — Every view should be screenshot-worthy
2. **Parsing is cheap, be generous** — No artificial limits on free tier
3. **Coach is the product** — Dashboard sells, coach retains
4. **Simplicity over scale** — Single box, monolith, optimize later
5. **Meet players where they are** — Discord/Steam auth, familiar stats + unique data

---

## Privacy & Compliance

### Data Handling

**What we store:**
- User account info (OAuth profile, email if provided)
- Uploaded .replay files (contain uploader + other players' game data)
- Parsed metrics per player per game
- AI coach session notes
- Usage/billing data

**Third-party data processing:**
- Replays sent to Claude API for coaching (Anthropic's data processing terms apply)
- Stripe for payment processing
- OAuth providers for authentication

### Consent Model

**Uploader consent:**
- Terms of Service acceptance on signup
- Clear disclosure: "Replays are processed locally and coaching data may be sent to our AI provider"
- Data retention policy in ToS

**Other players in replays:**
- Replays contain platform IDs and gameplay data of all players in the match
- This is publicly available match data (similar to ballchasing.gg, calculated.gg)
- No special consent required for public match data
- Users can request removal of specific matches they appear in (GDPR right to erasure)

### User Rights

**Data export:**
- Settings page: "Export my data" → JSON dump of all user data
- Includes: profile, replays metadata, parsed stats, coach notes

**Data deletion:**
- Settings page: "Delete my account" → soft delete, 30-day grace period
- After 30 days: hard delete of all user data, replays, notes
- Stripe subscription canceled immediately

**Coach notes:**
- User can view all notes the AI has saved about them
- User can delete individual notes or all notes
- Notes are never shared with other users

### Security

**Secrets management:**
- All secrets in environment variables, never in code
- NEXTAUTH_SECRET, STRIPE_SECRET_KEY, STRIPE_WEBHOOK_SECRET, DATABASE_URL, ANTHROPIC_API_KEY
- Rotate secrets quarterly or on suspected compromise

**Data at rest:**
- PostgreSQL on encrypted disk (Hetzner default)
- Backups encrypted before upload to B2

**Data in transit:**
- HTTPS everywhere (Cloudflare SSL)
- Internal services communicate over localhost (no network exposure)

### Rank Benchmark Data

**Data source:**
- Aggregate stats from rlcoach users (anonymized)
- Minimum sample size: 100 players per rank before showing comparisons
- Clearly labeled: "Based on X players at your rank"

**Bias handling:**
- Self-selection bias acknowledged (users who upload are more engaged)
- Display as "rlcoach users at your rank" not "all players at your rank"
- Update benchmarks weekly as sample grows
