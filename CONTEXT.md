# rlcoach Context — SaaS Build

**Last Updated**: 2026-01-03
**Current Phase**: Phase 1 Ready

## Protocol Reminder

Follow `AUTONOMOUS_BUILD_CLAUDE.md`:
1. Call Codex at checkpoints (after spec, after plan, after each phase, when stuck)
2. Update CONTEXT.md after each phase
3. Commit often with descriptive messages
4. No blocking on user input during build

**Quality gates:**
```bash
source .venv/bin/activate
PYTHONPATH=src pytest -q
ruff check src/
black --check src/
```

## Build Context

**Type**: Full product build (CLI -> SaaS)
**Spec location**: `docs/plans/2026-01-03-rlcoach-saas-design.md`
**Plan location**: `IMPLEMENTATION_PLAN.md`

## What We're Building

**rlcoach SaaS** — Subscription-based Rocket League coaching platform:
- Free tier: Unlimited replay uploads, full dashboard (7 pages, 7 tabs)
- Pro tier ($10/mo): AI coach powered by Claude Opus 4.5 with extended thinking

**Tech Stack**: Next.js + FastAPI + PostgreSQL + Stripe + Cloudflare on Hetzner

## Implementation Phases

| Phase | Name | Status |
|-------|------|--------|
| 1 | Infrastructure Foundation | **READY TO START** |
| 2 | PostgreSQL Database & Migration | Pending |
| 3 | Authentication & Authorization | Pending |
| 4 | Replay Upload & Processing | Pending |
| 5 | Dashboard Frontend | Pending |
| 6 | Stripe Payments & Subscription | Pending |
| 7 | AI Coach | Pending |
| 8 | Polish, Testing & Launch | Pending |

**Critical Path**: Infrastructure -> Database -> Auth -> Upload -> Dashboard -> AI Coach

Phase 6 (Payments) can run parallel to Phase 5 after Phase 3 completes.

## Codex Checkpoints

- [x] After drafting spec — Approved (fixed unit economics, auth architecture, compliance)
- [x] After drafting implementation plan — Approved (fixed tenant scoping, schema, cascades)
- [ ] After completing Phase 1
- [ ] After completing Phase 2
- [ ] ...after each phase...
- [ ] Before declaring build complete

## Previous Work (Complete)

### Mechanics Detection (Dec 2025)
All 12 mechanics implemented and tested:
- Flip reset, ceiling shot, musty flick, double touch
- Wavedash, flip cancel, fast aerial, air dribble
- Flick, dribble, skim, psycho
- 393 tests passing

## Next Action

**Begin Phase 1: Infrastructure Foundation**
1. Provision Hetzner AX41-NVMe server
2. Configure Cloudflare (DNS, SSL, rate limiting)
3. Install Docker and Docker Compose
4. Create Dockerfiles (Next.js, FastAPI, worker)
5. Set up nginx reverse proxy
6. Secrets management
7. CI/CD pipeline (GitHub Actions)
8. Backup infrastructure (pg_dump + Backblaze B2)

See `IMPLEMENTATION_PLAN.md` Phase 1 for full task list.
