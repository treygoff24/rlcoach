# Implementation Plan: rlcoach SaaS

**Status:** Ready for implementation
**Spec:** docs/plans/2026-01-03-rlcoach-saas-design.md
**Created:** 2026-01-03

---

## Overview

Transform the existing rlcoach Python CLI tool into a SaaS product with:
- Next.js frontend with 7-page dashboard
- PostgreSQL database (migrate from SQLite)
- OAuth authentication (Discord, Steam, Google, Epic)
- Stripe payments ($10/month Pro tier)
- AI coach powered by Claude Opus 4.5 with extended thinking
- Single Hetzner server deployment

**Existing Assets:**
- Complete replay parsing pipeline (Rust + Python)
- 12+ mechanics detection algorithms
- Analysis modules (boost, positioning, movement, xG, etc.)
- FastAPI skeleton with routers (games, dashboard, analysis, players)
- SQLite database models (need PostgreSQL migration)

**Critical Path:** Infrastructure -> Auth -> Database -> Upload -> Dashboard -> AI Coach

---

## Phase 1: Infrastructure Foundation

**Goal:** Establish production-ready infrastructure on Hetzner with proper CI/CD, secrets management, and deployment pipeline.

**Depends on:** None

**Estimated Effort:** L (1-2 weeks)

### Tasks

- [x] **1.1 Provision Hetzner Server** (Documentation created; actual provisioning is manual)
  - Description: Set up AX41-NVMe or similar (6-core Ryzen, 64GB RAM, 512GB NVMe)
  - Files: N/A (infrastructure)
  - Technical approach:
    - Ubuntu 22.04 LTS
    - SSH key authentication only
    - UFW firewall (80, 443 only)
    - Fail2ban for SSH protection
  - Acceptance criteria: Server accessible via SSH, firewall configured

- [x] **1.2 Configure Cloudflare** (Documentation created; actual setup is manual)
  - Description: DNS, SSL, CDN, DDoS protection, rate limiting
  - Files: N/A (DNS configuration)
  - Technical approach:
    - Add domain to Cloudflare
    - Enable Full (strict) SSL mode
    - Enable "Always Use HTTPS"
    - Cache static assets
    - **Rate limiting rules:**
      - Upload endpoint: 100 req/hour per IP
      - Auth endpoints: 10 req/min per IP
      - API endpoints: 1000 req/min per IP
    - Configure page rules for static asset caching
  - Acceptance criteria: Domain resolves, HTTPS works, rate limiting active

- [x] **1.3 Install Docker and Docker Compose**
  - Description: Container runtime for all services
  - Files: Create `docker-compose.yml`, `docker-compose.prod.yml`
  - Technical approach:
    - Docker for consistent deployments
    - Compose for multi-service orchestration
    - Separate dev and prod compose files
  - Acceptance criteria: `docker compose up` starts all services

- [x] **1.4 Create Dockerfiles**
  - Description: Container images for Next.js, FastAPI, worker
  - Files to create:
    - `frontend/Dockerfile`
    - `backend/Dockerfile`
    - `worker/Dockerfile`
  - Technical approach:
    - Multi-stage builds for smaller images
    - Non-root users in containers
    - Health checks in each image
  - Acceptance criteria: All images build, containers start and pass health checks

- [x] **1.5 Set Up nginx Reverse Proxy**
  - Description: Route traffic to Next.js (which proxies API calls to FastAPI)
  - Files to create: `nginx/nginx.conf`, `nginx/Dockerfile`
  - Technical approach:
    - ALL traffic -> Next.js (port 3000)
    - Next.js API routes (`/api/v1/*`) proxy to FastAPI internally
    - FastAPI NOT exposed to internet (only localhost:8000)
    - Stripe webhook: `/api/stripe/webhook` -> Next.js -> FastAPI
    - WebSocket via Next.js proxy
    - **Why:** Single origin (no CORS), Next.js handles JWT refresh, simpler security
  - Acceptance criteria: All routes via Next.js, FastAPI not directly accessible

- [x] **1.6 Secrets Management**
  - Description: Secure handling of API keys and credentials
  - Files to create: `.env.example`, `scripts/rotate-secrets.sh`
  - Technical approach:
    - Environment variables via Docker secrets or `.env`
    - Never commit secrets to git
    - Document all required secrets in `.env.example`
  - Required secrets:
    ```
    DATABASE_URL
    NEXTAUTH_SECRET
    NEXTAUTH_URL
    DISCORD_CLIENT_ID / DISCORD_CLIENT_SECRET
    STEAM_API_KEY
    GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET
    STRIPE_SECRET_KEY
    STRIPE_WEBHOOK_SECRET
    STRIPE_PUBLISHABLE_KEY
    ANTHROPIC_API_KEY
    BACKBLAZE_KEY_ID / BACKBLAZE_APPLICATION_KEY
    ```
  - Acceptance criteria: App starts with all secrets loaded, no secrets in git

- [x] **1.7 CI/CD Pipeline**
  - Description: Automated testing and deployment
  - Files to create: `.github/workflows/ci.yml`, `.github/workflows/deploy.yml`
  - Technical approach:
    - CI: Run tests, lint, type checks on every PR
    - CD: Deploy to production on merge to main
    - Use GitHub Actions
  - Acceptance criteria: PRs run CI, merges auto-deploy

- [x] **1.8 Backup Infrastructure**
  - Description: Daily PostgreSQL backups to Backblaze B2
  - Files to create: `scripts/backup.sh`, `scripts/restore.sh`
  - Technical approach:
    - Cron job: `pg_dump` at 3 AM UTC daily
    - Compress and encrypt before upload
    - Retain 30 days of backups
    - Test restore procedure
  - Acceptance criteria: Backups run daily, restore tested successfully

### Phase Verification
- [x] Server accessible via HTTPS at production domain (config ready, actual server manual)
- [x] All containers start and pass health checks (Dockerfiles with health checks created)
- [x] CI pipeline runs on test PR (GitHub Actions workflows created)
- [x] Backup script executes successfully (scripts/backup.sh created)
- [x] Secrets not exposed in logs or git (.env.example created, .gitignore updated)

### Risks/Decisions
- **Decision:** Server sizing - start with AX41-NVMe, monitor usage, upgrade if needed
- **Risk:** Hetzner availability - have Vultr/DO as backup plan
- **Decision:** Container orchestration - Docker Compose for simplicity, not K8s

---

## Phase 2: PostgreSQL Database & Migration

**Goal:** Migrate from SQLite to PostgreSQL with proper schema for multi-tenant SaaS.

**Depends on:** Phase 1 (infrastructure)

**Estimated Effort:** M (3-5 days)

### Tasks

- [ ] **2.1 Design PostgreSQL Schema**
  - Description: Adapt existing models for PostgreSQL, add SaaS-specific tables
  - Files to modify: `src/rlcoach/db/models.py`
  - Files to create: `migrations/versions/001_initial_schema.py`
  - Technical approach:
    - Keep existing tables: Replay, Player, PlayerGameStats, DailyStats, Benchmark
    - Add new tables: User, OAuthAccount, Session (NextAuth), VerificationToken (NextAuth), CoachSession, CoachMessage, CoachNote, UserReplay, UploadedReplay
    - Note: Subscription/token data stored as fields on User table (subscription_tier, token_budget_used, etc.)
    - Use Alembic for migrations
    - Add proper indexes for query patterns
  - New tables:
    ```python
    class User(Base):
        id: UUID (primary key)
        email: str (nullable, unique)
        display_name: str
        avatar_url: str (nullable)
        subscription_tier: "free" | "pro"
        subscription_status: "active" | "past_due" | "canceled" | null
        stripe_customer_id: str (nullable)
        stripe_subscription_id: str (nullable)
        subscription_period_end: datetime (nullable)
        token_budget_used: int (default 0)
        token_budget_reset_at: datetime
        created_at: datetime
        updated_at: datetime

    class OAuthAccount(Base):
        id: UUID (primary key)
        user_id: UUID (FK -> User)
        provider: str  # discord, steam, google, epic
        provider_account_id: str
        linked_at: datetime
        (unique: provider + provider_account_id)

    class CoachSession(Base):
        id: UUID (primary key)
        user_id: UUID (FK -> User)
        started_at: datetime
        ended_at: datetime (nullable)
        total_input_tokens: int
        total_output_tokens: int
        total_thinking_tokens: int
        message_count: int

    class CoachMessage(Base):
        id: UUID (primary key)
        session_id: UUID (FK -> CoachSession)
        role: "user" | "assistant"
        content: text
        input_tokens: int (nullable)
        output_tokens: int (nullable)
        thinking_tokens: int (nullable)
        created_at: datetime

    class CoachNote(Base):
        id: UUID (primary key)
        user_id: UUID (FK -> User)
        content: text
        source: "coach" | "user"
        category: str (nullable)  # e.g., "weakness", "strength", "goal"
        created_at: datetime
        updated_at: datetime

    # NextAuth required tables (Auth.js adapter)
    class Session(Base):
        id: UUID (primary key)
        session_token: str (unique, indexed)
        user_id: UUID (FK -> User)
        expires: datetime

    class VerificationToken(Base):
        identifier: str (primary key with token)
        token: str (primary key with identifier, hashed)
        expires: datetime

    class UploadedReplay(Base):
        id: UUID (primary key)
        user_id: UUID (FK -> User)
        replay_id: str (FK -> Replay, nullable after processing)
        filename: str
        file_hash: str
        file_size_bytes: int
        storage_path: str
        status: "pending" | "processing" | "completed" | "failed"
        error_message: text (nullable)
        uploaded_at: datetime
        processed_at: datetime (nullable)

    class UserReplay(Base):
        """Many-to-many join table for replay ownership.
        Allows multiple users to 'own' the same replay (dedup case)
        and one user to own multiple replays (normal case)."""
        id: UUID (primary key)
        user_id: UUID (FK -> User)
        replay_id: str (FK -> Replay)
        ownership_type: "uploaded" | "claimed" | "auto_matched"
        created_at: datetime
        (unique: user_id + replay_id)
    ```
  - Acceptance criteria: Schema documented, Alembic migration written

- [ ] **2.2 Set Up Alembic**
  - Description: Database migration framework
  - Files to create: `alembic.ini`, `migrations/env.py`, `migrations/script.py.mako`
  - Technical approach:
    - Configure Alembic with async PostgreSQL
    - Auto-generate migrations from model changes
    - Include downgrade paths
  - Acceptance criteria: `alembic upgrade head` creates all tables

- [ ] **2.3 Update Database Session Management**
  - Description: PostgreSQL connection pooling and async support
  - Files to modify: `src/rlcoach/db/session.py`
  - Technical approach:
    - Use asyncpg driver
    - SQLAlchemy async engine
    - Connection pooling (min 5, max 20)
    - Health checks on connections
  - Acceptance criteria: Async queries work, pool handles concurrent requests

- [ ] **2.4 Migrate Existing Data Models**
  - Description: Update SQLite-specific code for PostgreSQL compatibility
  - Files to modify:
    - `src/rlcoach/db/models.py` (SQLite-specific indexes)
    - `src/rlcoach/db/writer.py`
    - `src/rlcoach/db/aggregates.py`
  - Technical approach:
    - Replace `sqlite_where` with PostgreSQL partial indexes
    - Update JSON column handling
    - Test all existing queries
  - Acceptance criteria: All 393 existing tests pass with PostgreSQL

- [ ] **2.5 User-Replay Association**
  - Description: Link replays to users via OAuth platform IDs
  - Files to modify: `src/rlcoach/db/models.py`
  - Files to create: `src/rlcoach/services/replay_ownership.py`
  - Technical approach:
    - Replay contains player platform IDs
    - User has linked OAuth accounts with platform IDs
    - Auto-match on upload: if replay contains platform ID matching user's OAuth -> user owns replay
    - Manual claim endpoint for alt accounts
  - Acceptance criteria: Uploaded replays auto-associate with uploader

- [ ] **2.6 Session Detection Logic**
  - Description: Group replays into play sessions
  - Files to create: `src/rlcoach/services/session_detection.py`
  - Technical approach:
    - Replays within 30 minutes = same session
    - Store session_id on each replay
    - Configurable gap threshold per user
  - Acceptance criteria: Replays grouped correctly, threshold is tunable

### Phase Verification
- [ ] PostgreSQL running in Docker container
- [ ] Alembic migrations apply cleanly
- [ ] All existing tests pass against PostgreSQL
- [ ] User table properly linked to replays
- [ ] Session detection groups replays correctly

### Risks/Decisions
- **Decision:** UUID vs serial IDs - use UUIDs for all new tables (no enumeration attacks)
- **Risk:** Data migration from SQLite - this is new SaaS, no existing data to migrate
- **Decision:** JSON columns for flexible data - use JSONB for analytics_data on replays

---

## Phase 3: Authentication & Authorization

**Goal:** Implement NextAuth.js with OAuth providers and JWT-based API authentication.

**Depends on:** Phase 2 (database for user storage)

**Estimated Effort:** M (3-5 days)

### Tasks

- [ ] **3.1 Initialize Next.js Frontend Project**
  - Description: Create Next.js 14+ app with App Router
  - Files to create: `frontend/` directory structure
  - Technical approach:
    - `npx create-next-app@latest frontend --typescript --tailwind --app`
    - Configure path aliases
    - Set up ESLint + Prettier
  - Acceptance criteria: `npm run dev` starts dev server, TypeScript compiles

- [ ] **3.2 Install and Configure NextAuth.js**
  - Description: Authentication with multiple OAuth providers
  - Files to create:
    - `frontend/src/app/api/auth/[...nextauth]/route.ts`
    - `frontend/src/lib/auth.ts`
  - Technical approach:
    - NextAuth v5 (Auth.js)
    - PostgreSQL adapter for session storage
    - JWT strategy for API calls
  - Acceptance criteria: `/api/auth/signin` page renders with all providers

- [ ] **3.3 Configure Discord OAuth**
  - Description: Discord is primary auth for RL community
  - Files to modify: `frontend/src/lib/auth.ts`
  - Technical approach:
    - Create Discord application at discord.com/developers
    - Scopes: `identify`, `email`
    - Store Discord user ID for player matching
  - Acceptance criteria: Discord login works, user ID stored in OAuthAccount

- [ ] **3.4 Configure Steam OAuth**
  - Description: Steam OpenID for PC players
  - Files to modify: `frontend/src/lib/auth.ts`
  - Technical approach:
    - Steam Web API for OpenID
    - Extract Steam64 ID for player matching
  - Acceptance criteria: Steam login works, Steam ID stored

- [ ] **3.5 Configure Google OAuth**
  - Description: Fallback/convenience auth
  - Files to modify: `frontend/src/lib/auth.ts`
  - Technical approach:
    - Google Cloud Console OAuth credentials
    - Scopes: `openid`, `email`, `profile`
  - Acceptance criteria: Google login works

- [ ] **3.6 Configure Epic OAuth (if available)**
  - Description: Epic Games account linking
  - Files to modify: `frontend/src/lib/auth.ts`
  - Technical approach:
    - Epic Games Developer Portal
    - May require partner status - research first
    - If unavailable, skip for V1
  - Acceptance criteria: Epic login works OR documented as V2 feature

- [ ] **3.7 Account Linking Flow**
  - Description: Users can link multiple OAuth providers to one account
  - Files to create:
    - `frontend/src/app/settings/accounts/page.tsx`
    - `frontend/src/components/AccountLinking.tsx`
  - Technical approach:
    - Logged-in user can add additional OAuth providers
    - Platform IDs from all linked accounts used for replay matching
    - Cannot link account already linked to another user
  - Acceptance criteria: User can link Discord + Steam to same account

- [ ] **3.8 FastAPI JWT Middleware**
  - Description: Validate NextAuth JWTs in FastAPI
  - Files to create:
    - `src/rlcoach/api/middleware/auth.py`
    - `src/rlcoach/api/dependencies.py`
  - Technical approach:
    - Verify JWT signature using NEXTAUTH_SECRET
    - Extract user_id, subscription_tier from claims
    - FastAPI dependency: `get_current_user`
    - Return 401 for invalid/expired, 403 for wrong tier
  - Acceptance criteria: Protected endpoints reject invalid tokens

- [ ] **3.9 Subscription Tier Gating**
  - Description: Gate Pro features (AI coach) by subscription tier
  - Files to modify: `src/rlcoach/api/dependencies.py`
  - Technical approach:
    - `require_pro` dependency that checks tier == "pro"
    - Check subscription_status == "active" or within grace period
    - 403 response with upgrade prompt for free users
  - Acceptance criteria: Free users get 403 on AI coach endpoints

- [ ] **3.9.1 Tenant Scoping (Critical Security)**
  - Description: Ensure all queries are scoped to current user
  - Files to create: `src/rlcoach/api/middleware/tenant.py`
  - Files to modify: All API routers
  - Technical approach:
    - Every query MUST filter by user_id from JWT
    - Create `get_user_replays(user_id)` wrapper functions
    - Add user_id to all repository methods as required param
    - FastAPI dependency injects user_id from JWT into all handlers
    - **Critical:** Replay queries, session queries, note queries, usage queries ALL scoped
    - No endpoint should return data from another user
    - Test: user A cannot see user B's replays even with known IDs
  - Acceptance criteria: All endpoints return only current user's data, cross-user access impossible

- [ ] **3.10 Session Management**
  - Description: Handle session lifecycle (refresh, logout)
  - Files to modify: `frontend/src/lib/auth.ts`
  - Technical approach:
    - 15-minute JWT lifetime
    - Silent refresh on API calls
    - 7-day session expiry
    - Logout clears all sessions
  - Acceptance criteria: Sessions persist across browser close, refresh works

- [ ] **3.11 Next.js API Proxy Routes**
  - Description: Proxy API calls from Next.js to FastAPI
  - Files to create:
    - `frontend/src/app/api/v1/[...path]/route.ts`
  - Technical approach:
    - Catch-all route for `/api/v1/*`
    - Add JWT from NextAuth session to Authorization header
    - Forward request to FastAPI (localhost:8000)
    - Handle token refresh if expired
    - Return FastAPI response to client
  - Acceptance criteria: All API calls work through Next.js proxy

- [ ] **3.12 NextAuth Postgres Adapter Configuration**
  - Description: Configure NextAuth to use our PostgreSQL schema
  - Files to modify:
    - `frontend/src/lib/auth.ts`
    - `src/rlcoach/db/models.py`
  - Technical approach:
    - Use @auth/pg-adapter with custom table mapping
    - Map NextAuth's expected tables to our User/OAuthAccount schema:
      - `users` table with NextAuth required fields
      - `accounts` table (our OAuthAccount) with provider fields
      - `sessions` table for session storage
      - `verification_tokens` for email verification (if needed)
    - Ensure id, email, emailVerified fields on User
    - Test: sign in creates user, sessions persist
  - Acceptance criteria: NextAuth adapter works with our PostgreSQL schema

### Phase Verification
- [ ] User can sign up with Discord, Steam, Google
- [ ] User can link multiple accounts
- [ ] JWT tokens validate correctly in FastAPI
- [ ] Pro endpoints reject free users with 403
- [ ] Sessions persist and refresh correctly

### Risks/Decisions
- **Risk:** Epic OAuth availability - research partner requirements, may defer to V2
- **Decision:** JWT lifetime 15 min - balance between security and UX
- **Risk:** Steam OpenID complexity - may need passport-steam or custom implementation

---

## Phase 4: Replay Upload & Processing

**Goal:** Implement drag-drop upload with background processing queue.

**Depends on:** Phase 3 (auth for user association)

**Estimated Effort:** L (1-2 weeks)

### Tasks

- [ ] **4.1 File Upload API Endpoint**
  - Description: Accept .replay file uploads with validation
  - Files to create: `src/rlcoach/api/routers/upload.py`
  - Technical approach:
    - POST `/api/v1/replays/upload`
    - Accept multipart/form-data
    - Validate: file size <= 10MB, magic bytes check for .replay format
    - Rate limit: 100 uploads/hour/user, 50 files/batch
    - Store to temp directory with unique filename
  - Acceptance criteria: Valid uploads accepted, invalid rejected with clear errors

- [ ] **4.2 Upload Progress Tracking**
  - Description: Track upload status per file
  - Files to create:
    - `src/rlcoach/services/upload_tracker.py`
    - Table: UploadedReplay (see Phase 2)
  - Technical approach:
    - Create UploadedReplay record on upload start
    - Status transitions: pending -> processing -> completed/failed
    - Return upload_id for status polling
  - Acceptance criteria: Client can poll upload status

- [ ] **4.3 Background Worker Setup**
  - Description: Celery/RQ worker for async replay processing
  - Files to create:
    - `src/rlcoach/worker/__init__.py`
    - `src/rlcoach/worker/tasks.py`
    - `src/rlcoach/worker/config.py`
  - Technical approach:
    - Redis as message broker
    - One queue: `replay_processing`
    - Worker runs in separate container
    - Concurrency: 4 workers (match CPU cores for parsing)
  - Acceptance criteria: Tasks enqueue and execute in worker container

- [ ] **4.4 Replay Processing Task**
  - Description: Parse replay and store results
  - Files to modify: `src/rlcoach/worker/tasks.py`
  - Technical approach:
    - Subprocess with 30s timeout, 512MB memory limit
    - Call existing pipeline: ingest -> parse -> normalize -> analyze -> report
    - Store parsed JSON to filesystem
    - Update Replay table with results
    - Update UploadedReplay status
    - On failure: store error, mark as failed
  - Acceptance criteria: Replays process end-to-end, failures handled gracefully

- [ ] **4.4.1 Synchronous Preview Processing**
  - Description: Process first N replays synchronously for immediate preview
  - Files to modify: `src/rlcoach/api/routers/upload.py`
  - Technical approach:
    - First 3 replays in batch: process synchronously in request
    - Return preview stats immediately (result, score, key mechanics)
    - Remaining replays: queue for async processing
    - **Why:** Spec requires "immediate preview of key stats as each replay finishes"
    - Timeout: 10s per replay for sync processing
    - If sync times out, fall back to async
  - Acceptance criteria: First 3 replays show stats immediately on upload complete

- [ ] **4.5 Queue Backpressure**
  - Description: Protect system from overload
  - Files to modify: `src/rlcoach/api/routers/upload.py`
  - Technical approach:
    - Check queue length before accepting upload
    - Reject with 503 if queue > 1000 items
    - Return estimated wait time
  - Acceptance criteria: System gracefully rejects uploads when overloaded

- [ ] **4.6 Storage Deduplication**
  - Description: Don't store duplicate replays
  - Files to modify: `src/rlcoach/services/upload_tracker.py`
  - Technical approach:
    - **Primary dedup key:** match_id from replay header (same game = same replay)
    - **Fallback:** SHA256 hash for corrupted headers
    - Check if match_id exists in database
    - If duplicate: link user to existing parsed replay, don't re-parse
    - User still "owns" the replay reference
    - **Why match_id:** Same match uploaded by different players = one parse
  - Acceptance criteria: Duplicate uploads linked to existing replay instantly

- [ ] **4.7 Frontend Upload Component**
  - Description: Drag-drop upload with progress UI
  - Files to create:
    - `frontend/src/components/UploadDropzone.tsx`
    - `frontend/src/hooks/useUpload.ts`
  - Technical approach:
    - react-dropzone for drag-drop
    - Show progress bar per file
    - Display instant preview stats as each replay completes
    - Handle errors gracefully
  - Acceptance criteria: Users can drop files, see progress, see results

- [ ] **4.8 Real-time Progress Updates**
  - Description: WebSocket or polling for upload status
  - Files to create:
    - `src/rlcoach/api/routers/websocket.py` (or polling endpoint)
    - `frontend/src/hooks/useUploadStatus.ts`
  - Technical approach:
    - Option A: WebSocket connection for real-time updates
    - Option B: Poll `/api/v1/replays/{id}/status` every 2 seconds
    - Start with polling (simpler), add WebSocket if needed
  - Acceptance criteria: UI updates as processing completes

- [ ] **4.9 Disk Space Monitoring**
  - Description: Alert and reject when disk fills
  - Files to create: `src/rlcoach/services/disk_monitor.py`
  - Technical approach:
    - Check disk usage on upload
    - Alert at 80% usage
    - Reject uploads at 90% usage
    - Cron job to move old replays to B2 cold storage
  - Acceptance criteria: System alerts on low disk, rejects at threshold

- [ ] **4.10 Cold Storage Migration**
  - Description: Move old replays to Backblaze B2
  - Files to create: `scripts/migrate_to_cold_storage.py`
  - Technical approach:
    - Replays older than 30 days -> upload to B2
    - Update storage_path to B2 URL
    - Delete local copy
    - Fetch from B2 on demand (rare)
  - Acceptance criteria: Old replays accessible from B2

### Phase Verification
- [ ] Upload accepts valid .replay files
- [ ] Invalid files rejected with clear error message
- [ ] Background worker processes queue
- [ ] Duplicate uploads deduplicated
- [ ] Progress UI shows real-time status
- [ ] Disk monitoring alerts work
- [ ] Rate limits enforced

### Risks/Decisions
- **Decision:** Polling vs WebSocket - start with polling, simpler to implement and debug
- **Risk:** Parser memory usage - enforce 512MB limit via subprocess resource limits
- **Decision:** Redis for queue - simple, battle-tested, can switch to RabbitMQ if needed

---

## Phase 5: Dashboard Frontend

**Goal:** Build the 7-page dashboard with beautiful visualizations. This is the marketing funnel.

**Depends on:** Phase 4 (replays must be uploaded and parsed)

**Estimated Effort:** XL (2-3 weeks)

### Tasks

- [ ] **5.1 Design System Setup**
  - Description: Component library and theming
  - Files to create:
    - `frontend/src/components/ui/` (shadcn/ui components)
    - `frontend/src/styles/globals.css` (custom properties)
    - `frontend/tailwind.config.ts`
  - Technical approach:
    - shadcn/ui for base components
    - Custom color palette (dark mode default)
    - Typography scale for hierarchy
    - Consistent spacing system
  - Acceptance criteria: Design system documented, components render correctly

- [ ] **5.2 Layout Shell**
  - Description: App layout with navigation
  - Files to create:
    - `frontend/src/app/layout.tsx`
    - `frontend/src/components/Navbar.tsx`
    - `frontend/src/components/Sidebar.tsx`
  - Technical approach:
    - Sticky header with user avatar, upload button
    - Sidebar navigation for pages
    - Responsive: collapsible on mobile
    - Global upload dropzone overlay
  - Acceptance criteria: Navigation works, responsive on mobile

- [ ] **5.3 Home Page (Hero View)**
  - Description: Mechanics breakdown with rank comparisons + topline stats
  - Files to create:
    - `frontend/src/app/(dashboard)/page.tsx`
    - `frontend/src/components/MechanicsHero.tsx`
    - `frontend/src/components/ToplineStats.tsx`
  - Technical approach:
    - Mechanics breakdown: "47 flip resets - top 3% for Diamond"
    - Visual cards for each mechanic with percentile
    - Topline stats: goals, assists, saves, shots large
    - Secondary stats: boost/100, avg speed, third splits smaller
    - Shareable/screenshot-worthy design
  - API endpoints needed:
    - GET `/api/v1/dashboard/home` - aggregated stats + mechanics + rank percentiles
  - Acceptance criteria: Hero view renders, looks beautiful, shows real data

- [ ] **5.4 Replay List Page**
  - Description: All uploaded replays with sorting/filtering
  - Files to create:
    - `frontend/src/app/(dashboard)/replays/page.tsx`
    - `frontend/src/components/ReplayTable.tsx`
    - `frontend/src/components/ReplayFilters.tsx`
  - Technical approach:
    - Table with columns: date, result, score, map, playlist
    - Sort by date (default), result, score
    - Filter by playlist, date range, result
    - Infinite scroll or pagination
    - Quick stats on hover
  - API endpoints needed:
    - GET `/api/v1/replays?page=&filters=` - paginated replay list
  - Acceptance criteria: Replays display, filters work, performant with 1000+ replays

- [ ] **5.5 Replay Detail Page - Overview Tab**
  - Description: Single game deep dive, overview tab
  - Files to create:
    - `frontend/src/app/(dashboard)/replays/[id]/page.tsx`
    - `frontend/src/components/replay/OverviewTab.tsx`
    - `frontend/src/components/replay/Scoreboard.tsx`
  - Technical approach:
    - Game result header (teams, final score, overtime indicator)
    - Scoreboard with all players
    - Hero stats for current user
    - Quick highlights (best mechanic, notable moments)
  - API endpoints needed:
    - GET `/api/v1/replays/{id}` - full replay data with all tabs
  - Acceptance criteria: Overview displays complete game context

- [ ] **5.6 Replay Detail - Mechanics Tab**
  - Description: Mechanics detection breakdown
  - Files to create:
    - `frontend/src/components/replay/MechanicsTab.tsx`
    - `frontend/src/components/MechanicCard.tsx`
  - Technical approach:
    - Grid of mechanic types with counts
    - Timestamp links to timeline
    - Success rate for applicable mechanics
    - Comparison to user's average
  - Acceptance criteria: All 12+ mechanics display with counts and timestamps

- [ ] **5.7 Replay Detail - Boost Tab**
  - Description: Boost economy visualization
  - Files to create:
    - `frontend/src/components/replay/BoostTab.tsx`
    - `frontend/src/components/BoostChart.tsx`
  - Technical approach:
    - Boost over time line chart
    - Pickup breakdown (big vs small pads)
    - Time at 0 and 100 boost
    - Boost efficiency metrics
    - Starves (pads stolen from opponents)
  - Acceptance criteria: Boost data visualized clearly with charts

- [ ] **5.8 Replay Detail - Positioning Tab**
  - Description: Heatmaps and rotation analysis
  - Files to create:
    - `frontend/src/components/replay/PositioningTab.tsx`
    - `frontend/src/components/Heatmap.tsx`
  - Technical approach:
    - 2D heatmap overlaid on field
    - Third splits visualization
    - Average position indicator
    - Rotation compliance score
    - Distance to ball over time
  - Acceptance criteria: Heatmap renders, shows meaningful patterns

- [ ] **5.9 Replay Detail - Timeline Tab**
  - Description: Interactive event timeline
  - Files to create:
    - `frontend/src/components/replay/TimelineTab.tsx`
    - `frontend/src/components/TimelineEvent.tsx`
  - Technical approach:
    - Horizontal scrollable timeline
    - Events: goals, saves, demos, challenges, mechanics
    - Click to expand moment details
    - Color-coded by event type
    - Zoom controls
  - Acceptance criteria: Timeline interactive, events clickable

- [ ] **5.10 Replay Detail - Defense Tab**
  - Description: Defensive performance metrics
  - Files to create:
    - `frontend/src/components/replay/DefenseTab.tsx`
  - Technical approach:
    - Saves with save type breakdown
    - Clears count and quality
    - Shadow defense time
    - Last defender time percentage
    - Goals conceded as last back
  - Acceptance criteria: Defense metrics displayed clearly

- [ ] **5.11 Replay Detail - Offense Tab**
  - Description: Offensive performance metrics
  - Files to create:
    - `frontend/src/components/replay/OffenseTab.tsx`
    - `frontend/src/components/xGChart.tsx`
  - Technical approach:
    - Shots with xG values
    - Shot map (where shots taken from)
    - Assists and pass quality
    - Pressure time in offensive third
    - Goal conversion vs xG
  - Acceptance criteria: Offensive metrics with xG visualization

- [ ] **5.12 Session History Page**
  - Description: Replays grouped by play session
  - Files to create:
    - `frontend/src/app/(dashboard)/sessions/page.tsx`
    - `frontend/src/components/SessionCard.tsx`
  - Technical approach:
    - Group replays by session (30-min gap)
    - Session card: date, duration, W-L record, key stats
    - Expand to see individual replays
    - Session-level aggregates
  - API endpoints needed:
    - GET `/api/v1/sessions?page=` - paginated sessions with nested replays
  - Acceptance criteria: Sessions group correctly, expandable UI works

- [ ] **5.13 Trends Page**
  - Description: Stats over time with flexible axis
  - Files to create:
    - `frontend/src/app/(dashboard)/trends/page.tsx`
    - `frontend/src/components/TrendChart.tsx`
    - `frontend/src/components/AxisToggle.tsx`
  - Technical approach:
    - Line charts for key metrics over time
    - X-axis toggle: session/time/replay granularity
    - Multi-metric overlay (e.g., goals + assists)
    - Moving average option
    - Date range selector
  - API endpoints needed:
    - GET `/api/v1/trends?metrics=&axis=&range=` - trend data
  - Acceptance criteria: Charts render, axis toggle works, date range filters

- [ ] **5.14 Comparison Page**
  - Description: Rank comparison and self comparison
  - Files to create:
    - `frontend/src/app/(dashboard)/compare/page.tsx`
    - `frontend/src/components/RankComparison.tsx`
    - `frontend/src/components/SelfComparison.tsx`
  - Technical approach:
    - Tab 1: Your stats vs your rank average
    - Radar chart or bar chart comparison
    - Tab 2: This week vs last week
    - Highlight improvements and regressions
    - Show percentile for each metric
  - API endpoints needed:
    - GET `/api/v1/compare/rank` - rank benchmark comparison
    - GET `/api/v1/compare/self?period=` - period over period comparison
  - Acceptance criteria: Both comparison modes work, visualizations clear

- [ ] **5.14.1 Rank Benchmark Data Pipeline**
  - Description: Generate and refresh rank benchmark data
  - Files to create:
    - `src/rlcoach/services/benchmarks.py`
    - `src/rlcoach/worker/tasks/benchmarks.py`
  - Technical approach:
    - **Data source:** Aggregate stats from rlcoach users (anonymized)
    - **Minimum sample:** 100 players per rank before showing comparisons
    - **Gating:** If sample < 100, show "Insufficient data for your rank"
    - **Label:** "Based on X rlcoach users at your rank" (not "all players")
    - Weekly cron job: recompute percentiles per rank
    - Cache percentiles in benchmark table
    - **Bias disclosure:** Self-selection bias noted in UI
  - Acceptance criteria: Benchmarks only show with sufficient sample, refresh weekly

- [ ] **5.15 Settings Page**
  - Description: Profile, linked accounts, preferences
  - Files to create:
    - `frontend/src/app/(dashboard)/settings/page.tsx`
    - `frontend/src/components/settings/ProfileSection.tsx`
    - `frontend/src/components/settings/AccountsSection.tsx`
    - `frontend/src/components/settings/PreferencesSection.tsx`
  - Technical approach:
    - Profile: display name, avatar
    - Linked accounts: show all OAuth, add/remove
    - Preferences: session gap threshold, default playlist filter
    - Data export button
    - Account deletion (soft delete with 30-day grace)
  - Acceptance criteria: All settings functional, account linking works

- [ ] **5.16 Dashboard API Endpoints**
  - Description: Backend APIs for dashboard data
  - Files to create/modify:
    - `src/rlcoach/api/routers/dashboard.py` (enhance existing)
    - `src/rlcoach/api/routers/trends.py`
    - `src/rlcoach/api/routers/compare.py`
    - `src/rlcoach/api/routers/sessions.py`
  - Technical approach:
    - Optimize queries with proper indexes
    - Cache expensive aggregations (rank percentiles)
    - Return data shaped for frontend needs
  - Acceptance criteria: All dashboard pages have data, <500ms response times

### Phase Verification
- [ ] All 7 pages render correctly
- [ ] Data flows from backend to frontend
- [ ] Visualizations are beautiful and informative
- [ ] Pages are responsive (mobile-friendly)
- [ ] Performance: initial load <2s, interactions <200ms
- [ ] Screenshots are shareable quality

### Risks/Decisions
- **Decision:** Chart library - recharts or visx for flexibility
- **Risk:** Heatmap rendering performance - may need canvas/WebGL for large datasets
- **Decision:** Dark mode default - matches RL player preferences
- **Risk:** Design quality - may need design review/iteration

---

## Phase 6: Stripe Payments & Subscription

**Goal:** Implement $10/month Pro tier with Stripe Checkout and billing portal.

**Depends on:** Phase 3 (auth for user identification)

**Estimated Effort:** M (3-5 days)

### Tasks

- [ ] **6.1 Stripe Account Setup**
  - Description: Configure Stripe account and products
  - Files: N/A (Stripe dashboard)
  - Technical approach:
    - Create Stripe account (or use test mode)
    - Create Product: "rlcoach Pro"
    - Create Price: $10/month recurring
    - Configure Customer Portal
    - Get API keys and webhook secret
  - Acceptance criteria: Stripe configured, test payments work

- [ ] **6.2 Checkout Session Creation**
  - Description: API to create Stripe Checkout session
  - Files to create: `src/rlcoach/api/routers/billing.py`
  - Technical approach:
    - POST `/api/v1/billing/checkout` - create checkout session
    - Include user_id in metadata for webhook
    - Redirect to Stripe Checkout
    - Success/cancel URLs back to app
  - Acceptance criteria: Checkout session created, redirects work

- [ ] **6.3 Webhook Handler**
  - Description: Handle Stripe webhook events
  - Files to modify: `src/rlcoach/api/routers/billing.py`
  - Technical approach:
    - POST `/api/stripe/webhook` (note: different path for clarity)
    - Verify signature with STRIPE_WEBHOOK_SECRET
    - Handle events:
      - `checkout.session.completed` -> tier = "pro"
      - `customer.subscription.updated` -> sync status
      - `customer.subscription.deleted` -> tier = "free"
      - `invoice.payment_failed` -> status = "past_due"
    - Idempotent handling (use subscription_id)
  - Acceptance criteria: Webhooks process correctly, database updates

- [ ] **6.4 Billing Portal Link**
  - Description: Link to Stripe self-service portal
  - Files to modify: `src/rlcoach/api/routers/billing.py`
  - Technical approach:
    - POST `/api/v1/billing/portal` - create portal session
    - Redirect user to manage subscription
    - User can cancel, update payment, view invoices
  - Acceptance criteria: Portal link works, user can self-manage

- [ ] **6.5 Subscription Status in JWT**
  - Description: Include tier in JWT for API gating
  - Files to modify: `frontend/src/lib/auth.ts`
  - Technical approach:
    - On token creation/refresh, include subscription_tier
    - 15-minute JWT lifetime ensures tier changes propagate quickly
    - On webhook, database updates immediately
  - Acceptance criteria: JWT includes tier, refresh updates tier

- [ ] **6.6 Upgrade UI**
  - Description: Frontend upgrade prompts and flow
  - Files to create:
    - `frontend/src/components/UpgradePrompt.tsx`
    - `frontend/src/app/(dashboard)/upgrade/page.tsx`
  - Technical approach:
    - Upgrade CTA on AI coach page for free users
    - Feature comparison table
    - Click -> create checkout session -> redirect to Stripe
    - Return to app with confirmation
  - Acceptance criteria: Upgrade flow smooth, conversion-optimized

- [ ] **6.7 Subscription Status UI**
  - Description: Show subscription status in settings
  - Files to modify: `frontend/src/app/(dashboard)/settings/page.tsx`
  - Technical approach:
    - Show current tier (Free/Pro)
    - Show renewal date if Pro
    - "Manage Subscription" button -> Stripe Portal
    - "Upgrade" button if Free
  - Acceptance criteria: Status displays correctly, actions work

- [ ] **6.8 Grace Period Handling**
  - Description: 3-day grace for failed payments
  - Files to modify: `src/rlcoach/api/dependencies.py`
  - Technical approach:
    - Check subscription_status and subscription_period_end
    - If "past_due" but within 3 days of period_end -> allow access
    - After 3 days -> revoke access
    - Send notification email on past_due
  - Acceptance criteria: Grace period works, access revokes after 3 days

### Phase Verification
- [ ] Checkout flow completes successfully
- [ ] Webhooks update database correctly
- [ ] Billing portal accessible
- [ ] JWT includes correct tier
- [ ] Free users cannot access Pro features
- [ ] Grace period works for failed payments

### Risks/Decisions
- **Decision:** Single tier ($10/mo) - keep simple, add tiers later if needed
- **Risk:** Webhook reliability - Stripe retries for 72h, handle idempotently
- **Decision:** No trial period for V1 - free tier is generous enough

---

## Phase 7: AI Coach

**Goal:** Implement Claude Opus 4.5 powered coaching with extended thinking, tools, and session notes.

**Depends on:** Phase 5 (dashboard data for context), Phase 6 (subscription gating)

**Estimated Effort:** XL (2-3 weeks)

### Tasks

- [ ] **7.1 Chat API Infrastructure**
  - Description: Backend for AI coach conversations
  - Files to create:
    - `src/rlcoach/api/routers/coach.py`
    - `src/rlcoach/services/coach/__init__.py`
    - `src/rlcoach/services/coach/session.py`
  - Technical approach:
    - POST `/api/v1/coach/message` - send message, get response
    - Streaming response (SSE or WebSocket)
    - Store messages in CoachMessage table
    - Track token usage per message
  - Acceptance criteria: Messages send and receive, responses stream

- [ ] **7.2 Token Budget Enforcement**
  - Description: Enforce monthly token limits
  - Files to create: `src/rlcoach/services/coach/budget.py`
  - Technical approach:
    - Check token_budget_used before API call
    - Monthly budget: 150K tokens (input + output)
    - Per-request limits: 16K input, 8K output
    - Extended thinking: 32K budget (not counted against user)
    - Soft limit warning at 80%
    - Hard limit rejection at 100%
    - Reset budget on monthly anniversary
  - Acceptance criteria: Limits enforced, warnings shown, reset works

- [ ] **7.3 System Prompt**
  - Description: Craft the coaching personality and instructions
  - Files to create: `src/rlcoach/services/coach/prompts.py`
  - Technical approach:
    - Adaptive personality (reads player tone)
    - Rocket League domain expertise
    - Instructions for using data tools
    - Guidelines for constructive feedback
    - ~2K tokens budget for system prompt
  - Acceptance criteria: Coach responses are helpful and on-brand

- [ ] **7.4 Data Tools Implementation**
  - Description: Tools for coach to access player data
  - Files to create: `src/rlcoach/services/coach/tools.py`
  - Technical approach:
    - `get_recent_games(n)` - last N games with stats
    - `get_stats_by_mode(mode)` - aggregate by playlist
    - `get_stats_by_date_range(start, end)` - session-level analysis
    - `get_rank_benchmarks(rank)` - compare to rank
    - `get_game_details(game_id)` - deep dive one replay
    - Claude tool use format
    - Summarize results if > 4K tokens
  - Acceptance criteria: Tools work, responses use real data

- [ ] **7.5 Session Notes (Coach)**
  - Description: Coach saves observations about player
  - Files to create: `src/rlcoach/services/coach/notes.py`
  - Technical approach:
    - Tool: `save_note(content, category)`
    - Categories: weakness, strength, goal, observation
    - Notes persist across conversations
    - Injected into system prompt on new session
    - Coach decides when to save (not every message)
  - Acceptance criteria: Notes saved, persist, appear in future sessions

- [ ] **7.6 Session Notes (User)**
  - Description: Users can view, add, delete notes
  - Files to create:
    - `src/rlcoach/api/routers/notes.py`
    - `frontend/src/app/(dashboard)/coach/notes/page.tsx`
  - Technical approach:
    - GET `/api/v1/notes` - all user's notes
    - POST `/api/v1/notes` - add user note
    - DELETE `/api/v1/notes/{id}` - delete note
    - User notes marked with source="user"
    - UI shows all notes, allows management
  - Acceptance criteria: Users can manage their notes

- [ ] **7.7 Chat UI**
  - Description: Frontend chat interface
  - Files to create:
    - `frontend/src/app/(dashboard)/coach/page.tsx`
    - `frontend/src/components/coach/ChatInterface.tsx`
    - `frontend/src/components/coach/Message.tsx`
    - `frontend/src/components/coach/ThinkingIndicator.tsx`
  - Technical approach:
    - Message list with user/assistant bubbles
    - Input area with send button
    - Streaming response display
    - Extended thinking indicator (when coach is thinking deeply)
    - Token budget indicator
    - Upgrade prompt for free users
  - Acceptance criteria: Chat UI polished, streaming works

- [ ] **7.8 Structured Review Sessions**
  - Description: Guided coaching workflows
  - Files to create:
    - `frontend/src/components/coach/ReviewSession.tsx`
    - `src/rlcoach/services/coach/review.py`
  - Technical approach:
    - "Review my last session" button
    - Coach walks through: overview -> weaknesses -> improvements -> action items
    - Structured prompts guide the conversation
    - End with concrete practice recommendations
  - Acceptance criteria: Review session flow works end-to-end

- [ ] **7.9 Usage Dashboard**
  - Description: Show token usage and limits
  - Files to create:
    - `frontend/src/components/coach/UsageIndicator.tsx`
    - `src/rlcoach/api/routers/coach.py` (add usage endpoint)
  - Technical approach:
    - GET `/api/v1/coach/usage` - current usage stats
    - Visual: progress bar of budget used
    - Show: used / total, reset date
    - Warning colors at 80%, 100%
  - Acceptance criteria: Usage displays correctly, updates after messages

- [ ] **7.10 Rate Limiting**
  - Description: Prevent abuse beyond token budget
  - Files to modify: `src/rlcoach/services/coach/session.py`
  - Technical approach:
    - Max 10 requests/hour per user
    - Implemented at API level
    - 429 response with retry-after header
    - Separate from token budget (prevents rapid-fire abuse)
  - Acceptance criteria: Rate limits enforced, clear error messages

- [ ] **7.11 Context Management**
  - Description: Efficient use of context window
  - Files to modify: `src/rlcoach/services/coach/session.py`
  - Technical approach:
    - Truncate conversation history to fit 16K input limit
    - Keep most recent turns, summarize older ones
    - Tool results summarized if > 4K tokens
    - System prompt + notes + history must fit
  - Acceptance criteria: Long conversations don't fail, context managed well

### Phase Verification
- [ ] Chat works end-to-end
- [ ] Responses are helpful and use real player data
- [ ] Token budget enforced correctly
- [ ] Notes persist and influence coaching
- [ ] Rate limits prevent abuse
- [ ] Free users see upgrade prompt, cannot chat
- [ ] Extended thinking visible in UI

### Risks/Decisions
- **Decision:** Opus 4.5 with extended thinking - best coaching quality
- **Risk:** Token costs - monitor actual usage, adjust budget/pricing if needed
- **Decision:** Stream responses - better UX than waiting for full response
- **Risk:** Prompt engineering - may need iteration to get coaching quality right

---

## Phase 8: Polish, Testing & Launch

**Goal:** Production hardening, comprehensive testing, and launch preparation.

**Depends on:** All previous phases

**Estimated Effort:** L (1-2 weeks)

### Tasks

- [ ] **8.1 End-to-End Testing**
  - Description: Playwright tests for critical user flows
  - Files to create: `frontend/e2e/` test files
  - Technical approach:
    - Auth flow (signup, login, logout)
    - Upload flow (drop files, see progress, view results)
    - Dashboard navigation (all 7 pages)
    - Subscription flow (checkout, access)
    - Coach flow (send message, receive response)
  - Acceptance criteria: E2E tests pass, cover critical paths

- [ ] **8.2 Load Testing**
  - Description: Verify system handles expected load
  - Files to create: `scripts/load_test.py`
  - Technical approach:
    - Simulate 100 concurrent users
    - 50 uploads/minute
    - 20 coach messages/minute
    - Measure response times, error rates
    - Identify bottlenecks
  - Acceptance criteria: System handles target load, <500ms P95 latency

- [ ] **8.3 Security Audit**
  - Description: Review for security vulnerabilities
  - Files: N/A (audit process)
  - Technical approach:
    - OWASP Top 10 checklist
    - SQL injection testing
    - XSS testing
    - CSRF protection verification
    - Auth bypass attempts
    - Rate limit verification
  - Acceptance criteria: No critical/high vulnerabilities

- [ ] **8.4 Error Handling & Logging**
  - Description: Comprehensive error handling and observability
  - Files to modify: Throughout codebase
  - Technical approach:
    - Structured logging (JSON format)
    - Error tracking (Sentry or similar)
    - Request IDs for tracing
    - Graceful error pages in frontend
    - User-friendly error messages
  - Acceptance criteria: Errors logged, trackable, user-friendly

- [ ] **8.5 Performance Optimization**
  - Description: Optimize slow pages and queries
  - Files to modify: As identified by profiling
  - Technical approach:
    - Profile slow queries, add indexes
    - Optimize frontend bundle size
    - Add caching where beneficial
    - Lazy load heavy components
  - Acceptance criteria: All pages load <2s, interactions <200ms

- [ ] **8.6 Mobile Responsiveness**
  - Description: Ensure dashboard works on mobile
  - Files to modify: Frontend components
  - Technical approach:
    - Test all pages on mobile viewports
    - Fix layout issues
    - Touch-friendly interactions
    - Readable text sizes
  - Acceptance criteria: All pages usable on mobile

- [ ] **8.7 Legal Pages**
  - Description: Terms of Service, Privacy Policy
  - Files to create:
    - `frontend/src/app/terms/page.tsx`
    - `frontend/src/app/privacy/page.tsx`
  - Technical approach:
    - Consult legal template for SaaS
    - Cover data handling, replay processing, AI provider disclosure
    - GDPR compliance (data export, deletion)
    - Cookie consent
  - Acceptance criteria: Legal pages published, consent flows work

- [ ] **8.7.1 ToS Acceptance on Signup**
  - Description: Require Terms acceptance before account creation
  - Files to modify:
    - `frontend/src/components/SignupFlow.tsx`
    - `src/rlcoach/db/models.py` (add tos_accepted_at field)
  - Technical approach:
    - Checkbox: "I agree to Terms of Service and Privacy Policy"
    - Store tos_accepted_at timestamp in User record
    - Block account creation without acceptance
    - Display ToS version accepted
  - Acceptance criteria: Users cannot sign up without accepting ToS

- [ ] **8.7.2 Data Export Backend**
  - Description: Background job to generate user data export
  - Files to create:
    - `src/rlcoach/services/compliance/export.py`
    - `src/rlcoach/worker/tasks/export.py`
  - Technical approach:
    - POST `/api/v1/user/export` triggers background job
    - Job collects: profile, replays metadata (not raw files), parsed stats, coach sessions, coach messages, coach notes
    - **Excludes:** Raw .replay files (too large, user can re-download original from their game)
    - Generate JSON file, store temporarily (signed URL, expires 24h)
    - **Delivery options:**
      - If user has verified email: send email with download link
      - Always: in-app notification with download button in Settings
    - Log export request for audit
  - Acceptance criteria: User can download export from Settings page

- [ ] **8.7.2.1 Email Service Setup**
  - Description: Transactional email for notifications
  - Files to create:
    - `src/rlcoach/services/email.py`
  - Technical approach:
    - Provider: Resend, Postmark, or AWS SES (low volume, cheap)
    - Use cases: data export ready, payment failed, account deletion pending
    - **Email verification:**
      - Discord/Google provide verified emails
      - Steam/Epic may not - prompt user to add verified email
      - Settings page: "Add email for notifications"
    - Template system for consistent branding
  - Acceptance criteria: Emails send, fallback to in-app if no email

- [ ] **8.7.3 Account Deletion Backend**
  - Description: Background job for account deletion with grace period
  - Files to create:
    - `src/rlcoach/services/compliance/deletion.py`
    - `src/rlcoach/worker/tasks/deletion.py`
  - Technical approach:
    - POST `/api/v1/user/delete` sets deletion_requested_at, cancels Stripe
    - User sees "Account scheduled for deletion in 30 days"
    - User can cancel deletion within 30 days
    - Cron job runs daily: delete accounts past 30-day grace
    - **Full data removal (with FK cascades):**
      - Hard delete: user, oauth_accounts, coach_notes, coach_sessions (cascades coach_messages), user_replays, uploaded_replays
      - **Cascade order:** coach_messages -> coach_sessions -> coach_notes -> user_replays -> uploaded_replays -> oauth_accounts -> user
      - Player stats: anonymize player rows where user's platform_id matches
        - Replace display_name with "Deleted User"
        - Remove platform_id reference
        - Keep stats for aggregate benchmarks (anonymized)
      - Replays: remove from UserReplay; if no other owners, delete replay file
    - Log deletion for audit
  - Acceptance criteria: Accounts deleted after 30 days, player stats anonymized, cancelable before

- [ ] **8.7.4 Match Removal Requests (GDPR)**
  - Description: Allow non-uploaders to request match removal
  - Files to create:
    - `src/rlcoach/services/compliance/removal.py`
    - `frontend/src/app/removal-request/page.tsx`
  - Technical approach:
    - Public form: "Request removal of matches containing your platform ID"
    - Verify ownership via OAuth login OR manual review
    - Queue for review, then remove player from match stats
    - Keep replay (redact player), or delete if requested by all players
  - Acceptance criteria: Non-users can request removal of their data

- [ ] **8.8 Landing Page**
  - Description: Marketing landing page
  - Files to create: `frontend/src/app/(marketing)/page.tsx`
  - Technical approach:
    - Hero section with value prop
    - Feature highlights
    - Dashboard screenshots
    - Pricing section
    - CTA to sign up
    - Mobile-first design
  - Acceptance criteria: Landing page converts, showcases product

- [ ] **8.9 Monitoring & Alerting**
  - Description: Production monitoring setup
  - Files to create: `docker/prometheus/`, `docker/grafana/`
  - Technical approach:
    - Prometheus for metrics
    - Grafana dashboards
    - Alerts: error rate > 1%, latency > 1s, disk > 80%, CPU > 80%
    - PagerDuty or Discord webhook for alerts
  - Acceptance criteria: Monitoring dashboards live, alerts configured

- [ ] **8.10 Documentation**
  - Description: User and developer documentation
  - Files to create:
    - `docs/user-guide.md`
    - `docs/api.md`
    - `docs/deployment.md`
  - Technical approach:
    - User guide: how to upload, navigate dashboard, use coach
    - API docs: auto-generated from OpenAPI
    - Deployment docs: how to set up, configure, deploy
  - Acceptance criteria: Docs complete and accurate

- [ ] **8.11 Pre-Launch Checklist**
  - Description: Final verification before launch
  - Files: N/A (checklist)
  - Technical approach:
    - [ ] All tests pass
    - [ ] Stripe webhooks verified in production
    - [ ] Backups tested (restore drill)
    - [ ] SSL certificate valid
    - [ ] Domain DNS propagated
    - [ ] Error tracking configured
    - [ ] Monitoring alerts working
    - [ ] Legal pages published
    - [ ] Support email configured
  - Acceptance criteria: All checklist items complete

### Phase Verification
- [ ] E2E tests pass
- [ ] Load test passes at target capacity
- [ ] Security audit clean
- [ ] Mobile responsive
- [ ] Monitoring live
- [ ] Legal pages published
- [ ] Landing page ready
- [ ] Pre-launch checklist complete

### Risks/Decisions
- **Decision:** Launch scope - may need to trim features if timeline slips
- **Risk:** Unknown unknowns - buffer time for issues discovered during polish
- **Decision:** Soft launch vs big bang - consider beta with select users first

---

## Appendix A: API Endpoint Summary

### Auth (NextAuth handles)
- `GET/POST /api/auth/*` - NextAuth routes

### Replays
- `POST /api/v1/replays/upload` - Upload replay files
- `GET /api/v1/replays` - List user's replays (paginated)
- `GET /api/v1/replays/{id}` - Get replay details
- `DELETE /api/v1/replays/{id}` - Delete replay

### Dashboard
- `GET /api/v1/dashboard/home` - Home page data
- `GET /api/v1/sessions` - Session history
- `GET /api/v1/trends` - Trend data
- `GET /api/v1/compare/rank` - Rank comparison
- `GET /api/v1/compare/self` - Self comparison

### Billing
- `POST /api/v1/billing/checkout` - Create checkout session
- `POST /api/v1/billing/portal` - Create portal session
- `POST /api/stripe/webhook` - Stripe webhooks

### Coach
- `POST /api/v1/coach/message` - Send message to coach
- `GET /api/v1/coach/sessions` - List coaching sessions
- `GET /api/v1/coach/usage` - Get token usage
- `GET /api/v1/notes` - List notes
- `POST /api/v1/notes` - Create note
- `DELETE /api/v1/notes/{id}` - Delete note

### User
- `GET /api/v1/user/profile` - Get profile
- `PATCH /api/v1/user/profile` - Update profile
- `GET /api/v1/user/accounts` - Linked OAuth accounts
- `POST /api/v1/user/export` - Request data export
- `POST /api/v1/user/delete` - Request account deletion

---

## Appendix B: Database Schema Summary

### Existing Tables (adapted for PostgreSQL)
- `replays` - Replay metadata
- `players` - Player profiles
- `player_game_stats` - Per-player-per-game stats
- `daily_stats` - Aggregated daily stats
- `benchmarks` - Rank benchmark data

### New Tables
- `users` - User accounts with subscription info (subscription_tier, token_budget_used fields)
- `oauth_accounts` - Linked OAuth providers (maps to NextAuth "accounts")
- `sessions` - NextAuth session storage
- `verification_tokens` - NextAuth email verification (if needed)
- `user_replays` - Many-to-many replay ownership (uploaded/claimed/auto_matched)
- `uploaded_replays` - Upload tracking and processing status
- `coach_sessions` - AI coach sessions
- `coach_messages` - Individual messages (FK -> coach_sessions, cascades on delete)
- `coach_notes` - Persistent coaching notes

---

## Appendix C: Environment Variables

```bash
# Database
DATABASE_URL=postgresql://user:pass@localhost:5432/rlcoach

# NextAuth
NEXTAUTH_SECRET=<random-32-bytes>
NEXTAUTH_URL=https://rlcoach.gg

# OAuth Providers
DISCORD_CLIENT_ID=
DISCORD_CLIENT_SECRET=
STEAM_API_KEY=
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=

# Stripe
STRIPE_SECRET_KEY=sk_live_...
STRIPE_PUBLISHABLE_KEY=pk_live_...
STRIPE_WEBHOOK_SECRET=whsec_...

# Anthropic
ANTHROPIC_API_KEY=sk-ant-...

# Backblaze
BACKBLAZE_KEY_ID=
BACKBLAZE_APPLICATION_KEY=
BACKBLAZE_BUCKET_NAME=

# Redis
REDIS_URL=redis://localhost:6379

# Monitoring
SENTRY_DSN=
```

---

## Appendix D: Risk Register

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Epic OAuth unavailable | Medium | Low | Defer to V2, document as known gap |
| Token costs exceed revenue | Low | High | Monitor usage, adjust budget/pricing |
| Parser memory issues | Medium | Medium | Subprocess limits, monitoring |
| Hetzner outage | Low | High | Daily backups, documented restore procedure |
| Design quality insufficient | Medium | Medium | Budget for design iteration |
| Stripe webhook failures | Low | Medium | Idempotent handlers, retry logic |
| Extended thinking latency | Medium | Low | Show thinking indicator, set expectations |
| Dashboard performance | Medium | Medium | Profiling, caching, query optimization |

---

## Appendix E: Success Metrics (V1 Targets)

| Metric | Target |
|--------|--------|
| Time to first upload | < 60 seconds from signup |
| Upload processing time | < 5 seconds per replay |
| Dashboard page load | < 2 seconds |
| Coach response time | < 10 seconds (first token) |
| Free -> Pro conversion | > 5% |
| Monthly churn | < 10% |
| Uptime | > 99.5% |
