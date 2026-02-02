# Code Review: Anthropic SDK Refactor

**Branch:** `codex/anthropic-sdk-refactor`
**Plan:** `docs/plans/2026-02-02-rlcoach-anthropic-sdk-refactor.md`
**Date:** 2026-02-02
**Reviewer:** Claude Opus 4.5

---

## Executive Summary

This refactor moves AI coach orchestration from the Python backend to a Next.js API route using the `@anthropic-ai/sdk`, implementing a "preflight-stream-record" pattern for token budget management. The architecture is sound and the implementation follows the plan closely. However, **TypeScript compilation fails** with 38+ errors, blocking deployment. Several spec violations and type safety issues need addressing before merge.

**Verdict: REVISE** — Fix blocking issues before merge.

---

## Critical Issues (Must Fix)

### 1. TypeScript Compilation Failures (BLOCKING)

**Files:** Multiple frontend files
**Impact:** CI/CD pipeline blocked, cannot build or deploy

The frontend fails `npm run typecheck` with 38+ errors:

```
src/app/api/coach/chat/route.ts(94,11): error TS2353: 'signal' does not exist in type 'MessageCreateParamsBase'
src/app/api/coach/chat/route.ts(101,55): error TS2339: Property 'usage' does not exist on type 'RawMessageStartEvent'
src/lib/coach/anthropic/adapter.ts(24,9): error TS2322: Type 'unknown' is not assignable to type 'Record<string, unknown>'
src/lib/coach/anthropic/adapter.ts(29,56): error TS2339: Property 'stop_reason' does not exist on type 'RawMessageStopEvent'
```

**Root Cause:** SDK types don't match implementation assumptions.

**Fix Required:**
1. Verify `@anthropic-ai/sdk` version compatibility
2. Use correct event types from SDK (`MessageStreamEvent` subunions)
3. For `signal`, check SDK docs — may need to pass via different mechanism
4. For `usage` tracking, access via `streamResponse.finalMessage()` usage instead of raw events
5. For `stop_reason`, the event type may be `message_delta` with `stop_reason` field, not `message_stop`

---

### 2. Missing Jest Type Definitions (BLOCKING)

**Files:** All `*.test.ts` files
**Impact:** Test suite unusable

```
error TS2582: Cannot find name 'describe'. Try `npm i --save-dev @types/jest`
error TS2304: Cannot find name 'expect'
error TS2304: Cannot find name 'jest'
```

**Fix Required:**
```bash
npm i --save-dev @types/jest
```
Also add `"types": ["jest"]` to `tsconfig.json` compilerOptions, or create separate `tsconfig.test.json`.

---

### 3. Unsafe Type Coercion in Adapter

**File:** `frontend/src/lib/coach/anthropic/adapter.ts:24`
**Lines:** 19-26

```typescript
if (event.type === "content_block_start" && event.content_block?.type === "tool_use") {
  return [{
    type: "tool",
    tool_use_id: event.content_block.id,
    name: event.content_block.name,
    input: event.content_block.input,  // ERROR: unknown -> Record<string, unknown>
  }];
}
```

**Issue:** `event.content_block.input` is `unknown` per SDK types, but directly assigned to `Record<string, unknown>`.

**Fix Required:** Add runtime validation:
```typescript
const input = event.content_block.input;
const safeInput = (typeof input === 'object' && input !== null)
  ? input as Record<string, unknown>
  : {};
return [{ type: "tool", ..., input: safeInput }];
```

---

### 4. Reducer Type Mismatch

**File:** `frontend/src/components/coach/stream/reducer.ts:40`

```typescript
const messages = last && last.role === "assistant"
  ? [...state.messages.slice(0, -1), { role: "assistant", content: last.content + event.text }]
  : [...state.messages, { role: "assistant", content: event.text }];
```

**Issue:** Object literal `{ role: "assistant" }` infers `role: string`, not `role: "assistant"`.

**Fix Required:** Add `as const` or explicit type:
```typescript
{ role: "assistant" as const, content: ... }
```

---

### 5. useReducer Missing Initial State

**File:** `frontend/src/components/coach/stream/useASPStream.ts:7`

```typescript
const [state, dispatch] = useReducer(reducer, undefined);
```

**Issue:** Passing `undefined` as initial state causes type error. The `reducer` function has default parameter but React's `useReducer` signature expects explicit initial state.

**Fix Required:**
```typescript
const initialState: State = { messages: [], thinking: "", toolStatus: null, error: null };
const [state, dispatch] = useReducer(reducer, initialState);
```

---

### 6. Duplicate Timezone Normalization (Bug)

**File:** `src/rlcoach/services/coach/budget.py:82-86`

```python
reset_at = user.token_budget_reset_at
if reset_at is not None and reset_at.tzinfo is None:
    reset_at = reset_at.replace(tzinfo=timezone.utc)
if reset_at is not None and reset_at.tzinfo is None:  # DUPLICATE!
    reset_at = reset_at.replace(tzinfo=timezone.utc)
```

**Issue:** Lines 84-86 are exact duplicates of 82-84. Copy-paste error.

**Fix Required:** Delete lines 84-86.

---

### 7. Coach Page Implicit `any` Types

**File:** `frontend/src/app/(dashboard)/coach/page.tsx:275`

```typescript
{messages.map((message, index) => (
```

**Issue:** `message` and `index` have implicit `any` type due to type inference failure from reducer state.

**Fix Required:** After fixing reducer types, this should resolve. Alternatively, add explicit types:
```typescript
{messages.map((message: Message, index: number) => (
```

---

## Spec Violations (Should Fix)

### 8. Thinking Token Budget Incorrect

**File:** `frontend/src/app/api/coach/chat/route.ts:93`
**Plan Reference:** Task 7, line 595

**Plan specifies:**
> `EXTENDED_THINKING_BUDGET = 32_000` (in budget.py:18)

**Implementation:**
```typescript
thinking: { type: "enabled", budget_tokens: 2048 },
```

**Impact:** Extended thinking severely constrained at 2K vs spec's 32K.

**Fix Required:**
```typescript
thinking: { type: "enabled", budget_tokens: 32000 },
```
Or use env var: `Number(process.env.EXTENDED_THINKING_BUDGET || 32000)`

---

### 9. No Session History Truncation

**File:** `src/rlcoach/api/routers/coach.py:202-215`
**Plan Reference:** Architecture section

**Plan specifies:**
> "Truncate conversation history to fit 16K input limit"

**Implementation:** Loads ALL previous messages without truncation:
```python
previous_messages = (
    db.query(CoachMessage)
    .filter(CoachMessage.session_id == session.id)
    .order_by(CoachMessage.created_at)
    .all()
)
```

**Impact:** Long conversations will exceed context window, causing API errors.

**Fix Required:** Implement sliding window (last N turns) or token-based truncation:
```python
# Keep last 20 messages to stay within 16K input budget
previous_messages = (
    db.query(CoachMessage)
    .filter(CoachMessage.session_id == session.id)
    .order_by(CoachMessage.created_at.desc())
    .limit(20)
    .all()
)[::-1]  # Reverse to chronological order
```

---

### 10. Thinking Tokens Not Tracked

**File:** `frontend/src/app/api/coach/chat/route.ts:101-106`
**Plan Reference:** Budget integrity section

**Implementation only tracks input/output tokens:**
```typescript
if (event.type === "message_start" && event.usage) {
  totalTokens += event.usage.input_tokens || 0;
}
if (event.type === "message_delta" && event.usage) {
  totalTokens += event.usage.output_tokens || 0;
}
```

**Issue:** No tracking of `thinking_tokens` despite `CoachSession` model having `thinking_tokens` column (implied by the schema).

**Plan states:** "Extended thinking: 32K budget (not counted against user)"

**Fix Required:** Track separately for analytics:
```typescript
let thinkingTokens = 0;
// In the event loop:
if (event.type === "message_delta" && event.usage?.thinking_tokens) {
  thinkingTokens += event.usage.thinking_tokens;
}
```

---

## Warnings (Recommended Fixes)

### 11. Potential Race Condition in Token Reservation

**File:** `src/rlcoach/api/routers/coach.py:162-245`

**Flow:**
1. Line 162: `select(User).where(User.id == user.id).with_for_update()` — acquires row lock
2. Line 200: `release_expired_reservations()` — releases lock (commits)
3. Line 239: `reserve_tokens()` — attempts to reserve but lock already released

**Issue:** Between `release_expired_reservations()` commit and `reserve_tokens()` call, concurrent requests could both pass budget check.

**Recommendation:** Keep transaction open through reservation:
```python
# Don't commit in release_expired_reservations, just delete rows
# Let the outer transaction handle atomicity
```

---

### 12. No Tool Name Validation

**File:** `frontend/src/app/api/coach/chat/route.ts:154`

```typescript
const result = await executeTool(token, tool.name, tool.input);
```

**Issue:** Claude could hallucinate tool names. No validation against `tools` schema.

**Fix Required:**
```typescript
const validToolNames = new Set(tools.map((t: { name: string }) => t.name));
if (!validToolNames.has(tool.name)) {
  throw new Error(`Unknown tool: ${tool.name}`);
}
```

---

### 13. Weak Error Handling in Tool Execution

**File:** `frontend/src/app/api/coach/chat/route.ts:165-177`

```typescript
} catch (error) {
  const errorPayload = { error: "Tool execution failed" };
  // ...
}
```

**Issue:** Generic error message loses debugging context.

**Recommendation:**
```typescript
} catch (error) {
  console.error(`Tool ${tool.name} failed:`, error);
  const errorPayload = {
    error: "Tool execution failed",
    tool: tool.name,
    details: error instanceof Error ? error.message : "Unknown error"
  };
}
```

---

### 14. Missing Abort Signal Check Before Tool Calls

**File:** `frontend/src/app/api/coach/chat/route.ts:151-179`

**Issue:** `request.signal` passed to Anthropic SDK, but not checked before `executeTool` calls.

**Impact:** If client disconnects mid-stream, tool execution continues.

**Fix Required:**
```typescript
if (request.signal?.aborted) {
  throw new DOMException("Aborted", "AbortError");
}
const result = await executeTool(token, tool.name, tool.input);
```

---

### 15. Tool Results Not Sanitized

**File:** `src/rlcoach/api/routers/coach.py:286-296`

**Current sanitization:**
- User messages: 10K chars max
- Assistant messages: 50K chars max
- Tool results: **No sanitization**

**Impact:** Large tool results could bypass storage limits.

**Fix Required:** Sanitize tool result blocks in `chat_record`:
```python
for block in content_blocks:
    if block.get("type") == "tool_result":
        content = block.get("content")
        if isinstance(content, str) and len(content) > 50000:
            block["content"] = content[:50000] + "...[truncated]"
```

---

### 16. Hardcoded Model Fallback

**File:** `frontend/src/app/api/coach/chat/route.ts:88`

```typescript
model: process.env.COACH_MODEL_ID || "claude-opus-4-5-20250514",
```

**Issue:** Fallback hardcodes a model version that will become outdated.

**Recommendation:** Remove fallback, require env var:
```typescript
const modelId = process.env.COACH_MODEL_ID;
if (!modelId) {
  throw new Error("COACH_MODEL_ID environment variable required");
}
```

---

### 17. Free Preview Flag Not Surfaced in UI

**File:** `frontend/src/app/api/coach/chat/route.ts:74`

The `is_free_preview` flag is sent in the `ack` event but the UI only sets internal state. Consider showing a banner: "This is your free preview message."

---

## Suggestions (Nice to Have)

### 18. Token Reconciliation Logging

**File:** `src/rlcoach/services/coach/budget.py:239`

```python
delta = tokens_used - reservation.estimated_tokens
```

**Suggestion:** Log when delta exceeds threshold for estimation accuracy analysis:
```python
if abs(delta) > 500:
    logger.info(f"Token estimation delta: {delta} (estimated={reservation.estimated_tokens}, actual={tokens_used})")
```

---

### 19. Budget Estimation Ignores Tool Results

**File:** `src/rlcoach/services/coach/budget.py:304-331`

`estimate_request_tokens()` doesn't account for tool results in context. Multi-turn tool conversations will be underestimated.

**Suggestion:** Add parameter for tool result count:
```python
def estimate_request_tokens(
    message_length: int,
    history_messages: int = 0,
    include_tools: bool = True,
    tool_result_count: int = 0,
) -> int:
    # ... existing code ...
    tool_result_tokens = tool_result_count * 200  # ~200 tokens per result
    return message_tokens + history_tokens + overhead + output_estimate + tool_result_tokens
```

---

### 20. No Retry Logic for Transient Tool Failures

**File:** `frontend/src/app/api/coach/chat/route.ts:153-177`

Single tool failure aborts the conversation turn. Consider exponential backoff retry (1 retry):
```typescript
const executeWithRetry = async (tool: ToolCall) => {
  try {
    return await executeTool(token, tool.name, tool.input);
  } catch (firstError) {
    await new Promise(r => setTimeout(r, 500));
    return await executeTool(token, tool.name, tool.input);
  }
};
```

---

## Positive Observations

1. **Clean Architecture:** Preflight-stream-record pattern is well-designed for streaming with budget control
2. **Security:** Proper tenant scoping (`user_id` checks in all endpoints)
3. **Budget Management:** Reservation system prevents overspending during concurrent streams
4. **Content Storage:** `content_json` allows rich content while preserving `content` text fallback
5. **Migrations:** Proper Alembic migrations with upgrade AND downgrade paths
6. **Error Recovery:** Abort endpoint handles client disconnects gracefully
7. **Type Safety (Backend):** Pydantic models provide strong typing for all endpoints
8. **Documentation:** `docs/api.md` updated with all new endpoints
9. **Environment Config:** `.env.example` includes `ANTHROPIC_API_KEY`, `COACH_MODEL_ID`, `COACH_MAX_STEPS`

---

## Test Coverage Gaps

| Area | Status | Notes |
|------|--------|-------|
| `/api/v1/coach/tools/execute` error cases | Missing | Need tests for unknown tools, failed execution |
| `/api/v1/coach/chat/abort` with partial messages | Missing | Test partial message storage |
| Multi-step tool loop scenarios | Missing | Test MAX_STEPS enforcement |
| Budget reservation expiry during stream | Missing | Test 5-min TTL behavior |
| Frontend adapter event mapping | Has tests | But tests fail to compile |
| Reducer state transitions | Has tests | But tests fail to compile |

---

## Files Summary

### Files with Critical Issues
| File | Issues |
|------|--------|
| `frontend/src/app/api/coach/chat/route.ts` | SDK types, signal, usage |
| `frontend/src/lib/coach/anthropic/adapter.ts` | Type safety, stop_reason |
| `frontend/src/components/coach/stream/reducer.ts` | Role type inference |
| `frontend/src/components/coach/stream/useASPStream.ts` | Initial state |
| `src/rlcoach/services/coach/budget.py` | Duplicate code |

### Files with Spec Violations
| File | Issue |
|------|-------|
| `frontend/src/app/api/coach/chat/route.ts:93` | Thinking budget 2K vs 32K |
| `src/rlcoach/api/routers/coach.py:202` | No history truncation |

### Files Needing Test Fixes
| File | Fix Needed |
|------|------------|
| `frontend/src/app/api/coach/chat/route.test.ts` | @types/jest |
| `frontend/src/lib/coach/anthropic/__tests__/adapter.test.ts` | @types/jest |
| `frontend/src/lib/coach/__tests__/backend.test.ts` | @types/jest |
| `frontend/src/components/coach/stream/reducer.test.ts` | @types/jest |

---

## Recommended Merge Checklist

**Before Merge (Blocking):**
- [ ] Fix TypeScript compilation errors (Critical #1-5, 7)
- [ ] Fix duplicate timezone check (Critical #6)
- [ ] Install `@types/jest` (Critical #2)

**Before Merge (High Priority):**
- [ ] Increase thinking budget to 32K (Spec #8)
- [ ] Add session history truncation (Spec #9)
- [ ] Add tool name validation (Warning #12)

**Post-Merge Follow-ups:**
- [ ] Add thinking token tracking (Spec #10)
- [ ] Fix race condition in reservation (Warning #11)
- [ ] Add token reconciliation logging (Suggestion #18)
- [ ] Add comprehensive integration tests

---

## Appendix: TypeScript Error Summary

```
Total Errors: 38

By Category:
- Jest type definitions: 20 errors
- SDK type mismatches: 6 errors
- Reducer type inference: 4 errors
- useReducer signature: 2 errors
- Coach page any types: 2 errors
- Unknown type coercion: 2 errors
- stop_reason property: 2 errors
```
