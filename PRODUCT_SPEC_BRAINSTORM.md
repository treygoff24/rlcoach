# rlcoach Product Spec — Brainstorm Complete

**Status:** COMPLETE — See `docs/plans/2026-01-03-rlcoach-saas-design.md`
**Last Updated:** 2026-01-03
**Next Step:** Create implementation plan with `superpowers:writing-plans` skill

---

## Vision

Turn rlcoach from a CLI tool into a SaaS product: the best AI Rocket League coach to ever exist.

**Core loop:** Land → Free dashboard (wow factor) → Upload replays → Explore data → Pay for AI coach → Get coached

**Differentiator:** Our parser extracts far more granular mechanics data than ballchasing or calculated.gg. The dashboard excellence is the marketing funnel. Product sells itself.

---

## Decisions Made

### Business Model
- **Free tier:** Dashboard with generous replay limits (parsing is cheap)
- **Paid tier:** AI coach subscription (one tier, generous usage, simple pricing)
- **Marketing strategy:** Dashboard wow-factor drives organic sharing on Reddit/X. No traditional marketing.

### Tech Stack
| Component | Choice | Rationale |
|-----------|--------|-----------|
| Frontend | **Next.js** | React ecosystem has best UI libraries for dashboard wow-factor |
| Backend | **Python FastAPI** | Existing pipeline, PyO3 Rust bindings already work |
| Database | **PostgreSQL** | Free, handles concurrent writes, no migration pain later |
| Hosting | **Single Hetzner box** | Simplicity. Monolith. Scale later if needed. |
| Auth | **NextAuth.js** | Free, self-hosted, no vendor lock-in |
| OAuth providers | Discord, Steam, Google, Epic (if possible) | Where RL players already live |
| Payments | **Stripe Checkout + billing portal** | Minimal code, Stripe handles edge cases |

### AI Coach Architecture
- **Model:** Claude Opus 4.5 with extended thinking, maxed token + thinking budget
- **Initial context:** Topline data only (rank, MMR, username, main mode)
- **Data access:** On-demand via tools — Claude pulls what it needs
- **Skill/prompts:** Custom coaching skill (10x better than current rlcoach skill)

---

## Open Questions (Resume Here)

### Coach Tooling — PAUSED MID-QUESTION

**Proposed tools:**
```
Data retrieval:
- get_recent_games(n) — Last N games with full stats
- get_stats_by_mode(mode) — Aggregate stats filtered by 1v1/2v2/3v3
- get_stats_by_date_range(start, end) — Session-level analysis
- get_rank_benchmarks(rank) — Compare to rank / next rank
- get_game_details(game_id) — Deep dive on one replay
```

**User noted:** `get_mechanic_breakdown()` is NOT useful — cut it.

**Still need to decide:**
1. Just data retrieval? Or also...
2. Goal setting / tracking (save goals, check progress over time)
3. Training recommendations (suggest training packs / workshop maps)
4. Session notes (persist observations across conversations)

**Where I was heading:** I'd recommend starting with just data retrieval + session notes. Goals and training packs feel like V2 features. Session notes are high value, low complexity — lets the coach remember "this player struggles with backboard reads" across conversations.

### After Coach Tooling

Topics still to cover:
1. **Dashboard specifics** — What views/visualizations? What makes it "wow"?
2. **Replay upload flow** — Drag-drop? Bulk upload? Progress indicators?
3. **Data model** — Schema for users, replays, analysis results, coach sessions
4. **Coach skill/prompts** — What coaching methodology? How structured?
5. **Deployment specifics** — Nginx config, SSL, backup strategy

---

## For Next Claude

### How to Resume

1. Read this file first
2. Invoke `superpowers:brainstorming` skill
3. Continue from "Coach Tooling" section above
4. Ask ONE question at a time, multiple choice preferred
5. After coach tooling, move to dashboard specifics (the wow-factor piece)

### Key Context
- User values simplicity over scalability
- Marginal costs matter (self-funded project)
- Dashboard wow-factor is critical — it's the entire marketing strategy
- This is a niche product, don't over-engineer
- User is direct, appreciates concise responses

### Skills to Use Later
- `superpowers:writing-plans` — Once spec is complete, create implementation plan
- `superpowers:using-git-worktrees` — Isolate implementation work
- `frontend-design:frontend-design` — When building the dashboard UI
- `superpowers:test-driven-development` — For backend implementation

---

## Raw Notes

- Replay parsing cost is negligible — be generous with free tier limits
- Pareto distribution expected for coach usage (most users = few cents, power users = lots)
- Subscription chosen reluctantly — per-replay pricing doesn't work because coach needs aggregate data
- Discord/Steam OAuth reduces friction — meet players where they are
- Extended thinking on Opus 4.5 is intentional — want genuinely thoughtful coaching
