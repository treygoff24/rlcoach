# RLCoach API Documentation

Base URL: `https://api.rlcoach.gg/api/v1`

## Authentication

All protected endpoints require a JWT token in the Authorization header:

```
Authorization: Bearer <jwt_token>
```

Tokens are obtained through the NextAuth OAuth flow and contain:
- `sub`: User ID
- `email`: User email
- `subscriptionTier`: "free" or "pro"

## Endpoints

### Health

#### GET /health

Health check endpoint for monitoring.

**Response:**
```json
{
  "status": "healthy",
  "service": "rlcoach-backend",
  "version": "0.1.0",
  "timestamp": "2026-01-06T12:00:00Z",
  "checks": {
    "database": "connected",
    "redis": "connected"
  }
}
```

---

### Users

#### GET /users/me

Get current user profile.

**Auth Required:** Yes

**Response:**
```json
{
  "id": "user_123",
  "email": "user@example.com",
  "name": "Player Name",
  "subscription_tier": "free",
  "token_budget": 100000,
  "token_used": 5000,
  "created_at": "2026-01-01T00:00:00Z"
}
```

#### POST /users/me/accept-tos

Record Terms of Service acceptance.

**Auth Required:** Yes

**Request Body:**
```json
{
  "accepted_at": "2026-01-06T12:00:00Z"
}
```

**Response:**
```json
{
  "success": true,
  "accepted_at": "2026-01-06T12:00:00Z"
}
```

#### GET /users/me/export

Export all user data as JSON.

**Auth Required:** Yes

**Response:**
```json
{
  "user": { ... },
  "replays": [ ... ],
  "coach_sessions": [ ... ],
  "coach_messages": [ ... ],
  "notes": [ ... ],
  "exported_at": "2026-01-06T12:00:00Z"
}
```

#### POST /users/me/delete-request

Request account deletion (30-day grace period).

**Auth Required:** Yes

**Response:**
```json
{
  "status": "pending",
  "deletion_scheduled_at": "2026-02-05T12:00:00Z",
  "message": "Account scheduled for deletion in 30 days"
}
```

#### DELETE /users/me/delete-request

Cancel pending account deletion.

**Auth Required:** Yes

**Response:**
```json
{
  "status": "cancelled",
  "message": "Account deletion cancelled"
}
```

---

### Replays

#### POST /replays/upload

Upload a replay file.

**Auth Required:** Yes

**Request:** `multipart/form-data` with `file` field

**Response:**
```json
{
  "id": "replay_abc123",
  "filename": "2026-01-06.replay",
  "status": "processing",
  "sha256": "abc123...",
  "created_at": "2026-01-06T12:00:00Z"
}
```

#### GET /replays

List user's replays.

**Auth Required:** Yes

**Query Parameters:**
- `limit` (int, default 20): Number of replays to return
- `offset` (int, default 0): Pagination offset
- `sort` (string, default "date_desc"): Sort order

**Response:**
```json
{
  "replays": [
    {
      "id": "replay_abc123",
      "filename": "2026-01-06.replay",
      "map": "DFH Stadium",
      "game_mode": "3v3",
      "duration_seconds": 300,
      "status": "ready",
      "created_at": "2026-01-06T12:00:00Z"
    }
  ],
  "total": 42,
  "limit": 20,
  "offset": 0
}
```

#### GET /replays/{id}

Get replay details and analysis.

**Auth Required:** Yes

**Response:**
```json
{
  "id": "replay_abc123",
  "metadata": { ... },
  "analysis": {
    "fundamentals": { ... },
    "boost": { ... },
    "positioning": { ... },
    "mechanics": { ... }
  },
  "players": [ ... ]
}
```

#### DELETE /replays/{id}

Delete a replay.

**Auth Required:** Yes

**Response:**
```json
{
  "success": true,
  "id": "replay_abc123"
}
```

#### GET /replays/library

Get full replay library with metadata.

**Auth Required:** Yes

---

### Coach (Pro Only)

#### GET /coach/tools/schema

Return available coach tool definitions.

**Auth Required:** Yes

**Response:**
```json
{
  "tools": [
    {
      "name": "get_rank_benchmarks",
      "description": "...",
      "input_schema": { "type": "object", "properties": {} }
    }
  ]
}
```

#### POST /coach/tools/execute

Execute a coach tool.

**Auth Required:** Yes

**Request Body:**
```json
{
  "tool_name": "get_rank_benchmarks",
  "tool_input": { "rank": "GC1" }
}
```

**Response:**
```json
{
  "tool_name": "get_rank_benchmarks",
  "result": { "benchmarks": [] }
}
```

#### POST /coach/chat/preflight

Reserve budget and return context for a streaming chat turn.

**Auth Required:** Yes

**Request Body:**
```json
{
  "message": "What should I improve from this game?",
  "session_id": "session_xyz",
  "replay_id": "replay_abc123"
}
```

**Response:**
```json
{
  "session_id": "session_xyz",
  "budget_remaining": 145000,
  "is_free_preview": false,
  "history": [{ "role": "user", "content": [{ "type": "text", "text": "..." }] }],
  "system_message": "You are an expert Rocket League coach...",
  "estimated_tokens": 1200,
  "reservation_id": "reservation_123"
}
```

#### POST /coach/chat/record

Record streamed messages and finalize the token reservation.

**Auth Required:** Yes

**Request Body:**
```json
{
  "session_id": "session_xyz",
  "reservation_id": "reservation_123",
  "messages": [
    { "role": "user", "content_blocks": [{ "type": "text", "text": "..." }] },
    { "role": "assistant", "content_blocks": [{ "type": "text", "text": "..." }] }
  ],
  "tokens_used": 1500,
  "estimated_tokens": 1200,
  "is_free_preview": false
}
```

**Response:**
```json
{ "recorded": true }
```

#### POST /coach/chat/abort

Abort a chat turn and release the reservation (optionally storing partial messages).

**Auth Required:** Yes

**Request Body:**
```json
{
  "session_id": "session_xyz",
  "reservation_id": "reservation_123",
  "partial_messages": [
    { "role": "user", "content_blocks": [{ "type": "text", "text": "..." }] }
  ]
}
```

**Response:**
```json
{ "aborted": true }
```

**Note:** Streaming is orchestrated by the Next.js server route. Ensure
`ANTHROPIC_API_KEY`, `COACH_MODEL_ID`, and `COACH_MAX_STEPS` are set in the
frontend server runtime environment (Vercel/Docker), not just in `.env.local`.

#### GET /coach/sessions

List coaching sessions.

**Auth Required:** Yes (Pro tier)

**Response:**
```json
{
  "sessions": [
    {
      "id": "session_xyz",
      "replay_id": "replay_abc123",
      "message_count": 5,
      "created_at": "2026-01-06T12:00:00Z"
    }
  ]
}
```

#### POST /coach/notes

Save a coaching note.

**Auth Required:** Yes (Pro tier)

**Request Body:**
```json
{
  "replay_id": "replay_abc123",
  "session_id": "session_xyz",
  "content": "Remember to shadow more in 1v1s",
  "source": "assistant"
}
```

---

### Analysis

#### GET /analysis/trends

Get performance trends over time.

**Auth Required:** Optional (returns user-scoped data if authenticated)

**Query Parameters:**
- `period` (string): "7d", "30d", "90d", or "all"

**Response:**
```json
{
  "trends": [
    {
      "date": "2026-01-06",
      "games": 5,
      "avg_score": 450,
      "win_rate": 0.6
    }
  ]
}
```

#### GET /analysis/benchmarks

Get rank benchmarks for comparison.

**Auth Required:** Yes

**Response:**
```json
{
  "rank": "Diamond 2",
  "benchmarks": {
    "avg_score": 380,
    "goals_per_game": 0.8,
    "saves_per_game": 1.2
  }
}
```

---

### GDPR

#### POST /gdpr/removal-request

Submit a data removal request (public endpoint).

**Auth Required:** No

**Request Body:**
```json
{
  "player_identifier": "steam:12345678",
  "identifier_type": "steam_id",
  "email": "requester@example.com",
  "reason": "GDPR erasure request"
}
```

**Response:**
```json
{
  "status": "pending",
  "request_id": "gdpr_abc123",
  "message": "Request submitted. You will be notified at requester@example.com",
  "affected_replays": 5
}
```

---

### Billing

#### POST /billing/create-checkout

Create a Stripe checkout session for Pro upgrade.

**Auth Required:** Yes

**Response:**
```json
{
  "checkout_url": "https://checkout.stripe.com/..."
}
```

#### POST /billing/create-portal

Create a Stripe billing portal session.

**Auth Required:** Yes

**Response:**
```json
{
  "portal_url": "https://billing.stripe.com/..."
}
```

---

## Rate Limits

| Endpoint Category | Limit |
|------------------|-------|
| Upload | 10/minute |
| Coach Chat | 30/minute |
| Notes | 20/minute |
| Benchmarks | 30/minute |
| GDPR Requests | 5/hour |
| Default | 100/minute |

Rate limit headers are included in responses:
- `X-RateLimit-Limit`: Request limit
- `X-RateLimit-Remaining`: Remaining requests
- `X-RateLimit-Reset`: Reset timestamp

## Error Responses

All errors follow this format:

```json
{
  "detail": "Error message here"
}
```

Common status codes:
- `400`: Bad request (validation error)
- `401`: Unauthorized (missing/invalid token)
- `403`: Forbidden (insufficient permissions)
- `404`: Not found
- `429`: Rate limit exceeded
- `500`: Internal server error

## Webhooks

### Stripe Webhook

**POST /stripe/webhook**

Receives Stripe webhook events for subscription management.

Events handled:
- `checkout.session.completed`
- `customer.subscription.updated`
- `customer.subscription.deleted`
- `invoice.payment_failed`
