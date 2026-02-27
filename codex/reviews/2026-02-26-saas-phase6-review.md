# SaaS Phase 6 Final Code Review
**Date:** 2026-02-26  
**Reviewer:** Codex sub-agent  
**Scope:** Post Phase 1–5 review of SaaS-critical files  
**Reference:** SAAS_FIXES_PLAN.md (Phases 1–5 all marked complete)

---

## Summary

Phases 1–5 fixes are substantially correct. The SaaS loop (OAuth → bootstrap → upload → process → dashboard) is wired end-to-end. Quality gates reportedly pass (503 tests, ruff clean, black clean). However, **5 issues** were found ranging from a 500-triggering Pydantic bug to a GDPR compliance gap. The system should **not ship without addressing at least items 1, 2, and 3 below.**

---

## File-by-File Review

---

### `src/rlcoach/api/app.py`
**Checks:** DB init, SAAS_MODE routing, CORS, security

**No issues found.**

- ✅ DATABASE_URL checked first; falls back to config/in-memory correctly.
- ✅ CLI routers excluded when `SAAS_MODE=true` or `ENVIRONMENT=production`.
- ✅ Safety net: if production env detected without SAAS_MODE, it force-sets SAAS_MODE and logs CRITICAL — good fail-secure behavior.
- ✅ CORS origins read from `CORS_ORIGINS` env var (comma-separated), with sane dev defaults.
- ✅ Health endpoint checks DB and Redis independently; reports degraded (not unhealthy) on Redis miss.

---

### `src/rlcoach/api/auth.py`
**Checks:** JWT validation, auth bypass, secret handling, optional user

**No issues found.**

- ✅ JWT decoded with `algorithms=[ALGORITHM]` — algorithm pinning prevents alg=none attacks.
- ✅ `ExpiredSignatureError` caught separately from generic `InvalidTokenError` — correct error messages.
- ✅ `NEXTAUTH_SECRET` fails loudly at runtime if missing (RuntimeError).
- ✅ `get_current_user` fetches user from DB and raises 401 if not found — token can't reference a deleted user.
- ✅ `get_current_user_optional`: The `db: ... = None` default looks unusual but FastAPI resolves dependencies before invoking, so the actual `db` is always injected when `authorization` is not None. Works correctly in practice.
- ✅ `ProUser` / `AuthenticatedUser` / `OptionalUser` type aliases make dependency injection ergonomic and hard to misuse.

---

### `src/rlcoach/api/routers/users.py`
**Checks:** Bootstrap endpoint, benchmarks schema, auth on all routes

#### Issue 1 — BUG (HIGH): `SelfComparisonMetric.change_pct` typed `float`, can be `None` → 500
**Location:** Line 1134 (`change_pct: float`) and line 1266 (`change_pct=... if change_pct is not None else None`)

```python
# SelfComparisonMetric model:
change_pct: float          # ← non-optional

# In add_metric():
change_pct = (change / prev * 100) if prev != 0 else None   # ← can be None
...
change_pct=round(change_pct, 1) if change_pct is not None else None,  # ← passes None
```

When `prev == 0` (user has no previous-period games), `change_pct` is `None`. Pydantic v2 rejects `None` for a non-optional `float` field and raises `ValidationError` → **HTTP 500** on `/api/v1/users/me/compare/self`. Confirmed reproducible with Pydantic v2.

**Fix:** Change `change_pct: float` → `change_pct: float | None` in `SelfComparisonMetric`.

---

#### Issue 2 — MINOR (MEDIUM): `BOOTSTRAP_SECRET` unset silently allows all bootstrap requests
**Location:** `_verify_bootstrap_signature()`, line ~113

```python
if not secret:
    logger.warning("BOOTSTRAP_SECRET not set - bootstrap requests unverified")
    return True   # ← allows unauthenticated access
```

If `BOOTSTRAP_SECRET` is accidentally omitted from the production `.env`, the unauthenticated `/bootstrap` endpoint accepts any request from anywhere — including forged user creation. The warning is logged but doesn't block the request.

**Fix:** In SaaS/production mode, return `False` (reject) instead of `True` when secret is not set. Use `ENVIRONMENT` or `SAAS_MODE` env to determine strictness:
```python
if not secret:
    if os.getenv("SAAS_MODE", "false").lower() in ("true", "1"):
        logger.error("BOOTSTRAP_SECRET not set in SaaS mode — rejecting request")
        return False
    logger.warning("BOOTSTRAP_SECRET not set — accepting (dev only)")
    return True
```

---

#### Other observations (no action required)
- ✅ Benchmarks endpoint uses correct column names: `bcpm`, `time_supersonic_s` — Phase 4.1 fix confirmed.
- ✅ `ALLOWED_PROVIDERS` allowlist enforced on bootstrap.
- ✅ `hmac.new(secret.encode(), payload.encode(), hashlib.sha256)` — valid Python `hmac` API (confirmed with test run).
- ✅ All PATCH/DELETE/GET routes require `AuthenticatedUser` — no missing auth decorators.
- ⚠️ `cancel_at_period_end=False` hardcoded in `get_subscription` — acknowledged TODO pending Stripe webhook. Acceptable for launch if Stripe subscription management isn't GA yet.

---

### `src/rlcoach/api/routers/replays.py`
**Checks:** Upload auth, persistence, path traversal, size limits

**No issues found.**

- ✅ Auth enforced on all endpoints (`AuthenticatedUser` dependency).
- ✅ Rate limiting on upload (10/min) and a backpressure check (queue length + disk usage).
- ✅ Streaming file read — memory usage bounded to 64KB chunk size regardless of file size.
- ✅ Path traversal prevention: `_is_path_within_directory()` with `os.sep` suffix prevents prefix-match false positives.
- ✅ UUID validation on `upload_id` in delete endpoint.
- ✅ SHA256 computed in streaming pass — no double-read.
- ✅ File ownership enforced in all queries: `UploadedReplay.user_id == user.id`.
- ✅ 50MB limit standardized across early Content-Length check and streaming check.
- ✅ Magic bytes validation: checks for `TAGame` marker in first 1000 bytes.
- ✅ Duplicate detection by SHA256 per-user.
- Minor: If an exception occurs *after* `shutil.move` (during DB commit), the file is orphaned at the final `upload_dir` path. It would persist until the cleanup_temp_files Celery task runs or until the user deletes the upload via the API. Low severity, acceptable.

---

### `src/rlcoach/api/auth.py`
*(Covered above — no issues found)*

---

### `src/rlcoach/worker/tasks.py`
**Checks:** Replay processing, DB persistence, file paths, error handling

**No issues found.**

- ✅ Output file naming is correct: replay is saved as `{upload_id}.replay`, CLI writes `{replay_path.stem}.json` = `{upload_id}.json`. The worker's expected path `output_dir / f"{upload_id}.json"` matches. (Confirmed by tracing `cli.py` line 559: `out_file = out_dir / (replay_path.stem + ".json")`.)
- ✅ `write_report_saas` called before `UserReplay` creation (Phase 3.2 FK fix confirmed).
- ✅ `ReplayExistsError` caught and treated as success — user replay still linked.
- ✅ `SoftTimeLimitExceeded` handled: rollback, re-query upload, mark failed.
- ✅ Error messages sanitized: paths, passwords, API keys redacted before DB storage.
- ✅ UUID validation on `upload_id` before any DB or file operations.
- ✅ Storage path validated against upload dir before file access.
- ✅ Memory limit set via `resource.setrlimit` in subprocess preexec — good isolation.
- ✅ `session.merge(user_replay)` handles the unique constraint (`uq_user_replay`) gracefully.
- ✅ `completed_partial` status set when parsing succeeded but persistence failed — user gets actionable error.

---

### `src/rlcoach/db/writer.py`
**Checks:** Schema correctness, player upsert, SaaS write path

**No issues found.**

- ✅ Column names verified against `models.py`:
  - `bcpm` ✓, `time_supersonic_s` ✓, `time_zero_boost_s` ✓, `time_full_boost_s` ✓
  - `time_offensive_third_s` ✓, `time_middle_third_s` ✓, `time_defensive_third_s` ✓
  - `wavedash_count`, `halfflip_count`, `speedflip_count`, `aerial_count`, `flip_cancel_count` ✓
  - `challenge_wins/losses/neutral` ✓, `kickoffs_participated`, `kickoff_first_touches` ✓
- ✅ `write_report_saas` does NOT require `IdentityConfig` — correct for SaaS mode.
- ✅ Player `is_me` resolved via OAuth account linking (`_resolve_player_from_accounts`), then falls back to display name matching (`_resolve_player_from_user_profile`).
- ✅ Duplicate replay check by both `replay_id` and `file_hash` — solid dedup.
- ✅ All DB operations wrapped in try/except with rollback on failure.
- ✅ `session.get(Player, pid)` used for PK lookup (efficient) before falling back to session.add.
- ✅ Result logic (`WIN`/`LOSS`/`DRAW`) uses uppercase consistently (Phase 4.3 fix confirmed).

---

### `src/rlcoach/api/routers/dashboard.py`
**Checks:** Real data, auth, schema

#### Issue 3 — BUG (LOW): `date.today()` uses server local timezone, not UTC
**Location:** Line 23

```python
today = date.today()   # uses server's local timezone
```

All replay timestamps are stored in UTC (`played_at_utc`). The `play_date` column is computed from UTC. If the server timezone ≠ UTC, the "today's stats" section may show wrong results (e.g., showing yesterday's games as today's at midnight UTC).

**Fix:**
```python
from datetime import datetime, timezone
today = datetime.now(timezone.utc).date()
```

---

#### Other observations
- ✅ Auth enforced via `AuthenticatedUser`.
- ✅ All queries scoped to `user.id` via `UserReplay` subquery — no data leakage across users.
- ✅ Real data from DB — no mock data.
- ✅ `PlayerGameStats.is_me` filter applied correctly.

---

### `src/rlcoach/api/routers/gdpr.py`
**Checks:** Schema, auth, in-memory storage

#### Issue 4 — BUG (HIGH): GDPR removal requests stored in-memory — lost on restart/scale-out
**Location:** Module-level `_removal_requests: dict[str, dict] = {}`

```python
_removal_requests: dict[str, dict] = {}
```

In production with multiple Gunicorn workers or container restarts, each worker has its own `_removal_requests` dict. A request submitted to worker A cannot be retrieved or processed by worker B. A container restart wipes all pending requests. This means GDPR requests silently vanish — the user receives a confirmation message but the request is never processed. This is a **compliance gap** under GDPR Article 17 (right to erasure within 30 days).

**Fix:** Persist removal requests to the database. Add a `GdprRemovalRequest` table (or reuse an existing audit log table) with columns: `id`, `email`, `identifier`, `identifier_type`, `reason`, `status`, `submitted_at`, `processed_at`, `affected_count`. This is a lightweight schema change.

---

#### Issue 5 — SECURITY (MEDIUM): Admin endpoint lacks role check — any user can process GDPR requests
**Location:** `process_removal_request()`, line ~196

```python
@router.post("/removal-request/{request_id}/process")
async def process_removal_request(
    request_id: str,
    user: AuthenticatedUser,   # ← requires auth, but no role check
    db: ...
```

Any authenticated user can call this endpoint and anonymize any player's display name. A user could abuse this to rename opponents in their replays.

**Fix:** Add an admin check. Since there's no admin role in the User model currently, use an environment variable allowlist as a short-term fix:
```python
ADMIN_USER_IDS = set(os.getenv("ADMIN_USER_IDS", "").split(","))
if user.id not in ADMIN_USER_IDS:
    raise HTTPException(status_code=403, detail="Admin access required")
```
Longer-term: add `is_admin: bool` to the User model.

---

#### Other observations
- ✅ Rate limiting on `/removal-request` by email.
- ✅ `identifier_type` validated against allowlist.
- ✅ Email validated with regex before use.
- ✅ `player_identifier` sanitized (strip, length check, dangerous char removal).
- ✅ Schema: `Player.player_id`, `Player.display_name`, `PlayerGameStats.player_id` all match `models.py`.
- ✅ `ilike` without `%` wildcards = exact case-insensitive match for display_name. Correct.
- ⚠️ `_generate_request_id` includes `date.isoformat()` — the same user submitting two requests in one day gets the same `request_id`. Idempotent by design but could suppress legitimate re-submissions. Low severity.

---

## Issues Summary

| # | Severity | File | Issue |
|---|----------|------|-------|
| 1 | **HIGH** | `routers/users.py` | `SelfComparisonMetric.change_pct: float` rejects `None` → 500 when prev period is empty |
| 2 | **MEDIUM** | `routers/users.py` | `BOOTSTRAP_SECRET` unset silently allows all bootstrap requests in production |
| 3 | **LOW** | `routers/dashboard.py` | `date.today()` uses server local timezone instead of UTC |
| 4 | **HIGH** | `routers/gdpr.py` | GDPR requests stored in-memory — lost on restart/multi-worker deploy |
| 5 | **MEDIUM** | `routers/gdpr.py` | Admin GDPR process endpoint has no role guard — any user can call it |

---

## Verdict: **Needs Work**

### Blocking (must fix before launch)
1. **Issue 1** — Fix `SelfComparisonMetric.change_pct: float | None`. 2-line fix. Causes HTTP 500 in a common case (new users with only one period of data).
2. **Issue 4** — Persist GDPR requests to database. Without this, the 30-day GDPR compliance guarantee cannot be met. Required before EU users touch the product.

### Should Fix (pre-launch)
3. **Issue 5** — Add admin guard to GDPR process endpoint. Short-term: env var allowlist. Without this any user can anonymize any player name.
4. **Issue 2** — Fail-secure bootstrap when `BOOTSTRAP_SECRET` is unset in SaaS mode. Prevents silent auth bypass from misconfigured deploy.

### Can Defer Post-Launch
5. **Issue 3** — `date.today()` → `datetime.now(timezone.utc).date()` in dashboard. Only affects users in UTC-offset timezones near midnight. Low impact, easy fix.

### Not Required to Ship
- Hardcoded `cancel_at_period_end=False` (Stripe subscription not GA yet)
- Orphaned file on late upload failure (cleanup task handles it)

Once Issues 1, 2, 4, 5 are fixed: **Ship it.**
