# RLCoach Anthropic SDK Refactor Implementation Plan

**Goal:** Hard‑refactor the Coach feature to use the stable `@anthropic-ai/sdk` Messages API end‑to‑end, with streaming and tool use handled in the Next.js API route and the Python backend reduced to tool/session persistence only.

**Architecture:** All LLM orchestration moves to `frontend/src/app/api/coach/chat/route.ts` using the Anthropic TypeScript SDK and an ASP v2‑style event stream. The FastAPI backend exposes tool schema, tool execution, chat preflight, and message recording endpoints. The legacy backend `/api/v1/coach/chat` endpoint and all Python Anthropic usage are removed. UI consumes the stream via a reducer + hook. Full turn content (including `tool_use` and `tool_result` blocks) is persisted so future turns retain tool context. Token reservations are explicit, expiring, and reconciled to avoid drift. Abort paths release reservations and optionally store partial history.

**Tech Stack:** Next.js (App Router), TypeScript, `@anthropic-ai/sdk` (Messages API), FastAPI (Python), SQLAlchemy, SSE/streaming.

---

## Decisions Locked In

1. **SDK choice:** Use the stable `@anthropic-ai/sdk` (Messages API). No Agent SDK v2 preview.
2. **Streaming UX:** Coach UI will consume ASP v2 streaming events (no buffered JSON response path).
3. **Clean cutover:** Remove the legacy backend LLM endpoint and all Python Anthropic usage. No compatibility shims.
4. **Safety controls:** Enforce loop caps, abort handling, and error propagation in the streaming orchestrator.
5. **History fidelity:** Persist full structured content blocks so tool outputs remain in context.
6. **Budget integrity:** Token reservations are tracked and auto‑expired to prevent permanent budget loss.

---

### Task 1: Add Coach Tool Schema + Execution API (Backend)

**Parallel:** no
**Blocked by:** none
**Owned files:** `src/rlcoach/api/routers/coach.py`, `src/rlcoach/services/coach/prompts.py`, `src/rlcoach/services/coach/tools.py`, `tests/api/test_coach_tools_api.py`

**Files:**
- Modify: `src/rlcoach/api/routers/coach.py`
- Modify: `src/rlcoach/services/coach/prompts.py`
- Modify: `src/rlcoach/services/coach/tools.py`
- Create: `tests/api/test_coach_tools_api.py`

**Step 1: Write the failing tests**
```python
# tests/api/test_coach_tools_api.py
from fastapi.testclient import TestClient


def test_tools_schema_returns_tools(client: TestClient):
    response = client.get("/api/v1/coach/tools/schema")
    assert response.status_code == 200
    data = response.json()
    assert "tools" in data
    assert any(tool["name"] == "get_rank_benchmarks" for tool in data["tools"])
```

**Step 2: Run test to verify it fails**
Run: `source .venv/bin/activate && PYTHONPATH=src pytest tests/api/test_coach_tools_api.py -q`
Expected: FAIL with 404 on `/api/v1/coach/tools/schema`.

**Step 3: Write minimal implementation**
```python
# src/rlcoach/api/routers/coach.py
from pydantic import BaseModel


class ToolExecuteRequest(BaseModel):
    tool_name: str
    tool_input: dict


@router.get("/api/v1/coach/tools/schema")
async def get_coach_tool_schema():
    return {"tools": get_tool_descriptions()}


@router.post("/api/v1/coach/tools/execute")
async def execute_coach_tool(
    request: ToolExecuteRequest,
    user=Depends(get_current_user),
    db=Depends(get_db),
):
    result_json = await execute_tool(
        tool_name=request.tool_name,
        tool_input=request.tool_input,
        user_id=user.id,
        db=db,
    )
    return {"tool_name": request.tool_name, "result": json.loads(result_json)}
```

**Step 4: Ensure tool schema generation is Anthropic‑free and sanitized**
- If `get_tool_descriptions()` or schema helpers import `anthropic` types, refactor to standard Pydantic JSON schemas or raw dicts before removing the Python dependency.
- Strip Pydantic metadata that can confuse strict JSON schema consumers (e.g., `title`, `allOf`).

**Step 5: Run test to verify it passes**
Run: `source .venv/bin/activate && PYTHONPATH=src pytest tests/api/test_coach_tools_api.py -q`
Expected: PASS.

**Step 6: Commit (optional)**
Only if requested.

---

### Task 2: Persist Structured Coach Messages (DB + API)

**Parallel:** no
**Blocked by:** Task 1
**Owned files:** `src/rlcoach/db/models.py`, `migrations/versions/*`, `src/rlcoach/api/routers/coach.py`, `tests/api/test_coach_history.py`

**Files:**
- Modify: `src/rlcoach/db/models.py`
- Create: `migrations/versions/*_coach_messages_content_json.py`
- Modify: `src/rlcoach/api/routers/coach.py`
- Create: `tests/api/test_coach_history.py`

**Step 1: Write the failing tests**
```python
# tests/api/test_coach_history.py
from fastapi.testclient import TestClient


def test_session_messages_include_content_blocks(client: TestClient):
    response = client.get("/api/v1/coach/sessions/test-session/messages")
    assert response.status_code in {200, 404}
```

**Step 2: Run test to verify it fails**
Run: `source .venv/bin/activate && PYTHONPATH=src pytest tests/api/test_coach_history.py -q`
Expected: FAIL (endpoints not yet updated).

**Step 3: Add a JSON column for content blocks**
```python
# src/rlcoach/db/models.py
class CoachMessage(Base):
    ...
    content = Column(Text, nullable=False)
    content_json = Column(Text, nullable=True)  # JSON list of content blocks
```

Create an Alembic migration to add `content_json` to `coach_messages` and backfill existing rows with `[{"type":"text","text": content}]` where possible.

**Step 4: Update session message retrieval to include content blocks**
```python
# src/rlcoach/api/routers/coach.py
# get_session_messages should return content_blocks parsed from content_json
# and fall back to [{"type": "text", "text": content}] when missing.
```

**Step 5: Run test to verify it passes**
Run: `source .venv/bin/activate && PYTHONPATH=src pytest tests/api/test_coach_history.py -q`
Expected: PASS.

**Step 6: Commit (optional)**
Only if requested.

---

### Task 3: Add Token Reservation Tracking (Backend)

**Parallel:** no
**Blocked by:** Task 2
**Owned files:** `src/rlcoach/db/models.py`, `src/rlcoach/services/coach/budget.py`, `migrations/versions/*`, `tests/api/test_coach_budget_reservations.py`

**Files:**
- Modify: `src/rlcoach/db/models.py`
- Modify: `src/rlcoach/services/coach/budget.py`
- Create: `migrations/versions/*_coach_token_reservations.py`
- Create: `tests/api/test_coach_budget_reservations.py`

**Step 1: Write the failing tests**
```python
# tests/api/test_coach_budget_reservations.py
from fastapi.testclient import TestClient


def test_reservation_expires_and_releases_budget(client: TestClient):
    # Simulate reservation creation and expiry
    assert True
```

**Step 2: Run test to verify it fails**
Run: `source .venv/bin/activate && PYTHONPATH=src pytest tests/api/test_coach_budget_reservations.py -q`
Expected: FAIL (reservation helpers missing).

**Step 3: Add reservation model**
```python
# src/rlcoach/db/models.py
class CoachTokenReservation(Base):
    __tablename__ = "coach_token_reservations"

    id = Column(String, primary_key=True, default=_generate_uuid)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    session_id = Column(String, ForeignKey("coach_sessions.id", ondelete="CASCADE"), nullable=False)
    estimated_tokens = Column(Integer, nullable=False)
    created_at = Column(DateTime(timezone=True), default=_utc_now, nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
```

Add Alembic migration to create the table.

**Step 4: Add reservation helpers**
```python
# src/rlcoach/services/coach/budget.py
# reserve_tokens(user, session_id, estimated_tokens, db) -> reservation_id
# release_expired_reservations(user, db)
# finalize_reservation(user, reservation_id, tokens_used, db)
# abort_reservation(user, reservation_id, db) -> releases estimate immediately
```

Reservation policy:
- `reserve_tokens` increments `user.token_budget_used` by `estimated_tokens`.
- `finalize_reservation` applies the delta `(tokens_used - estimated_tokens)`.
- `release_expired_reservations` adds back `estimated_tokens` for expired rows.
- `abort_reservation` releases immediately on client disconnect.
- Use a short expiration window (e.g., 5 minutes) to minimize temporary lockouts.

**Step 5: Run test to verify it passes**
Run: `source .venv/bin/activate && PYTHONPATH=src pytest tests/api/test_coach_budget_reservations.py -q`
Expected: PASS.

**Step 6: Commit (optional)**
Only if requested.

---

### Task 4: Add Chat Preflight + Record + Abort Endpoints and Remove Legacy Chat (Backend)

**Parallel:** no
**Blocked by:** Task 3
**Owned files:** `src/rlcoach/api/routers/coach.py`, `src/rlcoach/services/coach/budget.py`, `pyproject.toml`, `tests/api/test_coach_chat_preflight.py`

**Files:**
- Modify: `src/rlcoach/api/routers/coach.py`
- Modify: `src/rlcoach/services/coach/budget.py`
- Modify: `pyproject.toml`
- Create: `tests/api/test_coach_chat_preflight.py`

**Step 1: Write the failing tests**
```python
# tests/api/test_coach_chat_preflight.py
from fastapi.testclient import TestClient


def test_chat_preflight_creates_session(client: TestClient):
    payload = {"message": "Hi coach!"}
    response = client.post("/api/v1/coach/chat/preflight", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert "session_id" in data
    assert "budget_remaining" in data
    assert "system_message" in data
    assert "history" in data
    assert "reservation_id" in data
```

**Step 2: Run test to verify it fails**
Run: `source .venv/bin/activate && PYTHONPATH=src pytest tests/api/test_coach_chat_preflight.py -q`
Expected: FAIL with 404 on `/api/v1/coach/chat/preflight`.

**Step 3: Implement preflight and record endpoints**
```python
# src/rlcoach/api/routers/coach.py
class ChatPreflightResponse(BaseModel):
    session_id: str
    budget_remaining: int
    is_free_preview: bool
    history: list[dict]
    system_message: str
    estimated_tokens: int
    reservation_id: str


@router.post("/api/v1/coach/chat/preflight", response_model=ChatPreflightResponse)
async def chat_preflight(...):
    # 1) rate limit + message length validation
    # 2) select user FOR UPDATE
    # 3) release_expired_reservations(user) BEFORE budget check
    # 4) reserve_tokens(user, session_id, estimated_tokens)
    # 5) create/find session
    # 6) build history from content_json
    # 7) build system prompt using build_system_prompt(user_notes, player_name)
```

```python
class ChatRecordRequest(BaseModel):
    session_id: str
    reservation_id: str
    messages: list[dict]
    tokens_used: int
    estimated_tokens: int
    is_free_preview: bool


@router.post("/api/v1/coach/chat/record")
async def chat_record(...):
    # 1) store each message with content and content_json
    # 2) update session token totals + message_count
    # 3) finalize_reservation(user, reservation_id, tokens_used)
    # 4) mark free preview used if applicable
```

**Step 4: Add abort endpoint**
```python
class ChatAbortRequest(BaseModel):
    session_id: str
    reservation_id: str
    partial_messages: list[dict] | None = None


@router.post("/api/v1/coach/chat/abort")
async def chat_abort(...):
    # 1) optionally store partial messages (if provided)
    # 2) abort_reservation(user, reservation_id)
    # 3) return {"aborted": True}
```

**Step 5: Verify global Anthropic usage before removal**
Run: `rg "\bimport anthropic\b|\bfrom anthropic\b" src` and ensure only the coach legacy code references it.

**Step 6: Remove legacy chat + Python Anthropic usage**
- Delete `/api/v1/coach/chat` endpoint.
- Remove `_get_coach_response` and any Anthropic client code.
- Remove `anthropic` from `pyproject.toml`.

**Step 7: Run test to verify it passes**
Run: `source .venv/bin/activate && PYTHONPATH=src pytest tests/api/test_coach_chat_preflight.py -q`
Expected: PASS.

**Step 8: Commit (optional)**
Only if requested.

---

### Task 5: Add ASP v2 Types + Anthropic SDK Adapter (Frontend)

**Parallel:** no
**Blocked by:** Task 4
**Owned files:** `frontend/package.json`, `frontend/src/lib/coach/asp.ts`, `frontend/src/lib/coach/anthropic/client.ts`, `frontend/src/lib/coach/anthropic/request.ts`, `frontend/src/lib/coach/anthropic/adapter.ts`, `frontend/src/lib/coach/anthropic/__tests__/adapter.test.ts`

**Files:**
- Modify: `frontend/package.json`
- Create: `frontend/src/lib/coach/asp.ts`
- Create: `frontend/src/lib/coach/anthropic/client.ts`
- Create: `frontend/src/lib/coach/anthropic/request.ts`
- Create: `frontend/src/lib/coach/anthropic/adapter.ts`
- Create: `frontend/src/lib/coach/anthropic/__tests__/adapter.test.ts`

**Step 1: Write the failing test**
```ts
// frontend/src/lib/coach/anthropic/__tests__/adapter.test.ts
import { mapSdkEvent } from "../adapter";

it("maps deltas to ASP events", () => {
  const events = mapSdkEvent({ type: "content_block_delta", delta: { type: "text_delta", text: "hi" }, index: 0 } as any);
  expect(events[0].type).toBe("text");
});
```

**Step 2: Run test to verify it fails**
Run: `cd frontend && npm run test -- adapter.test.ts`
Expected: FAIL because `mapSdkEvent` and adapter module are missing.

**Step 3: Write minimal implementation (including SDK dependency)**
```ts
// frontend/package.json
// Add: "@anthropic-ai/sdk": "^0.39.0" (or latest stable)
```

```ts
// frontend/src/lib/coach/anthropic/client.ts
import Anthropic from "@anthropic-ai/sdk";

export const anthropicClient = new Anthropic({
  apiKey: process.env.ANTHROPIC_API_KEY,
  maxRetries: 2,
});
```

```ts
// frontend/src/lib/coach/asp.ts
export type AspEvent =
  | { type: "ack" }
  | { type: "thinking"; text: string }
  | { type: "text"; text: string }
  | { type: "tool"; tool_use_id: string; name: string; input: Record<string, unknown> }
  | { type: "tool_result"; tool_use_id: string; content: unknown }
  | { type: "message_stop"; stop_reason: string }
  | { type: "error"; message: string };
```

```ts
// frontend/src/lib/coach/anthropic/adapter.ts
import type { MessageStreamEvent } from "@anthropic-ai/sdk/resources/messages";
import type { AspEvent } from "../asp";

export function mapSdkEvent(event: MessageStreamEvent): AspEvent[] {
  if (event.type === "content_block_delta" && event.delta?.type === "text_delta") {
    return [{ type: "text", text: event.delta.text }];
  }
  if (event.type === "content_block_delta" && event.delta?.type === "thinking_delta") {
    return [{ type: "thinking", text: event.delta.thinking }];
  }
  if (event.type === "content_block_start" && event.content_block?.type === "tool_use") {
    return [{ type: "tool", tool_use_id: event.content_block.id, name: event.content_block.name, input: event.content_block.input }];
  }
  if (event.type === "message_stop") {
    return [{ type: "message_stop", stop_reason: event.stop_reason }];
  }
  return [];
}
```

**Step 4: Run test to verify it passes**
Run: `cd frontend && npm run test -- adapter.test.ts`
Expected: PASS.

**Step 5: Commit (optional)**
Only if requested.

---

### Task 6: Add Backend Bridge for Tool Execution + Preflight (Frontend)

**Parallel:** no
**Blocked by:** Task 5
**Owned files:** `frontend/src/lib/coach/backend.ts`, `frontend/src/lib/coach/tool-execution.ts`, `frontend/src/lib/coach/__tests__/backend.test.ts`

**Files:**
- Create: `frontend/src/lib/coach/backend.ts`
- Create: `frontend/src/lib/coach/tool-execution.ts`
- Create: `frontend/src/lib/coach/__tests__/backend.test.ts`

**Step 1: Write the failing test**
```ts
// frontend/src/lib/coach/__tests__/backend.test.ts
import { getToolSchema } from "../backend";

it("fetches tool schema", async () => {
  await expect(getToolSchema("test-token")).resolves.toHaveProperty("tools");
});
```

**Step 2: Run test to verify it fails**
Run: `cd frontend && npm run test -- backend.test.ts`
Expected: FAIL because `getToolSchema` is missing.

**Step 3: Write minimal implementation**
```ts
// frontend/src/lib/coach/backend.ts
const BACKEND_URL = process.env.BACKEND_URL || "http://localhost:8000";

export async function getToolSchema(token: string) {
  const response = await fetch(`${BACKEND_URL}/api/v1/coach/tools/schema`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!response.ok) throw new Error("Tool schema fetch failed");
  return response.json();
}

export async function executeTool(
  token: string,
  toolName: string,
  toolInput: Record<string, unknown>,
) {
  const response = await fetch(`${BACKEND_URL}/api/v1/coach/tools/execute`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({ tool_name: toolName, tool_input: toolInput }),
  });
  if (!response.ok) throw new Error("Tool execution failed");
  return response.json();
}

export async function chatPreflight(token: string, payload: { message: string; session_id?: string; replay_id?: string }) {
  const response = await fetch(`${BACKEND_URL}/api/v1/coach/chat/preflight`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify(payload),
  });
  if (!response.ok) throw new Error("Preflight failed");
  return response.json();
}

export async function chatRecord(token: string, payload: { session_id: string; reservation_id: string; messages: Array<{ role: string; content_blocks: unknown[]; content_text?: string }>; tokens_used: number; estimated_tokens: number; is_free_preview: boolean }) {
  const response = await fetch(`${BACKEND_URL}/api/v1/coach/chat/record`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify(payload),
  });
  if (!response.ok) throw new Error("Record failed");
  return response.json();
}

export async function chatAbort(token: string, payload: { session_id: string; reservation_id: string; partial_messages?: Array<{ role: string; content_blocks: unknown[]; content_text?: string }> }) {
  const response = await fetch(`${BACKEND_URL}/api/v1/coach/chat/abort`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify(payload),
  });
  if (!response.ok) throw new Error("Abort failed");
  return response.json();
}
```

**Step 4: Run test to verify it passes**
Run: `cd frontend && npm run test -- backend.test.ts`
Expected: PASS.

**Step 5: Commit (optional)**
Only if requested.

---

### Task 7: Replace Next.js Chat Route with Anthropic Streaming + Tool Loop

**Parallel:** no
**Blocked by:** Task 6
**Owned files:** `frontend/src/app/api/coach/chat/route.ts`, `frontend/src/app/api/coach/chat/route.test.ts`

**Files:**
- Modify: `frontend/src/app/api/coach/chat/route.ts`
- Create: `frontend/src/app/api/coach/chat/route.test.ts`

**Step 1: Write the failing test**
```ts
// frontend/src/app/api/coach/chat/route.test.ts
import { POST } from "./route";

it("returns a streaming response", async () => {
  const request = new Request("http://localhost/api/coach/chat", {
    method: "POST",
    body: JSON.stringify({ message: "hi" }),
    headers: { Authorization: "Bearer test" },
  });
  const response = await POST(request);
  expect(response.headers.get("Content-Type")).toContain("text/event-stream");
});
```

**Step 2: Run test to verify it fails**
Run: `cd frontend && npm run test -- route.test.ts`
Expected: FAIL because route still returns JSON.

**Step 3: Write minimal implementation (agentic loop)**
```ts
// frontend/src/app/api/coach/chat/route.ts
import { anthropicClient } from "@/lib/coach/anthropic/client";
import { mapSdkEvent } from "@/lib/coach/anthropic/adapter";
import { getToolSchema, executeTool, chatPreflight, chatRecord, chatAbort } from "@/lib/coach/backend";

export const dynamic = "force-dynamic";
export const maxDuration = 300;

const MAX_STEPS = Number(process.env.COACH_MAX_STEPS || 10);

export async function POST(request: Request) {
  const { message, session_id, replay_id } = await request.json();
  const token = request.headers.get("authorization")?.replace("Bearer ", "") || "";

  const preflight = await chatPreflight(token, { message, session_id, replay_id });
  if (preflight.budget_remaining <= 0) {
    return new Response(JSON.stringify({ error: "Budget exhausted" }), { status: 402 });
  }

  const { tools } = await getToolSchema(token);

  const stream = new TransformStream();
  const writer = stream.writable.getWriter();
  const encoder = new TextEncoder();

  const sendEvent = async (event: unknown) => {
    await writer.write(encoder.encode(`data: ${JSON.stringify(event)}\n\n`));
  };

  (async () => {
    let pendingUserMessage = message;

    try {
      let messages = [...preflight.history, { role: "user", content: [{ type: "text", text: message }] }];
      let finalText = "";
      let finalThinking = "";
      let totalTokens = 0;

      for (let step = 0; step < MAX_STEPS; step += 1) {
        const streamResponse = anthropicClient.messages.stream({
          model: process.env.COACH_MODEL_ID || "claude-opus-4-5-20250514",
          max_tokens: 8192,
          system: preflight.system_message,
          messages,
          tools,
          thinking: { type: "enabled", budget_tokens: 2048 },
          signal: request.signal,
        });

        const toolCalls: { id: string; name: string; input: Record<string, unknown> }[] = [];

        for await (const event of streamResponse) {
          if (event.type === "message_start" && event.usage) {
            totalTokens += (event.usage.input_tokens || 0);
          }
          if (event.type === "message_delta" && event.usage) {
            totalTokens += (event.usage.output_tokens || 0);
          }

          for (const aspEvent of mapSdkEvent(event)) {
            await sendEvent(aspEvent);
            if (aspEvent.type === "text") finalText += aspEvent.text;
            if (aspEvent.type === "thinking") finalThinking += aspEvent.text;
            if (aspEvent.type === "tool") toolCalls.push({ id: aspEvent.tool_use_id, name: aspEvent.name, input: aspEvent.input });
          }
        }

        const finalMessage = await streamResponse.finalMessage();

        if (toolCalls.length === 0) {
          await chatRecord(token, {
            session_id: preflight.session_id,
            reservation_id: preflight.reservation_id,
            messages: [
              { role: "user", content_blocks: [{ type: "text", text: pendingUserMessage }], content_text: pendingUserMessage },
              { role: "assistant", content_blocks: finalMessage.content, content_text: finalText },
            ],
            tokens_used: totalTokens,
            estimated_tokens: preflight.estimated_tokens,
            is_free_preview: preflight.is_free_preview,
          });
          await sendEvent({ type: "message_stop", stop_reason: "end_turn" });
          await writer.close();
          return;
        }

        const toolResults = await Promise.all(
          toolCalls.map(async (tool) => {
            try {
              const result = await executeTool(token, tool.name, tool.input);
              await sendEvent({ type: "tool_result", tool_use_id: tool.id, content: result.result });
              return { type: "tool_result", tool_use_id: tool.id, content: result.result };
            } catch (error) {
              const errorPayload = { error: "Tool execution failed" };
              await sendEvent({ type: "tool_result", tool_use_id: tool.id, content: errorPayload });
              return { type: "tool_result", tool_use_id: tool.id, content: errorPayload };
            }
          })
        );

        await chatRecord(token, {
          session_id: preflight.session_id,
          reservation_id: preflight.reservation_id,
          messages: [
            { role: "user", content_blocks: [{ type: "text", text: pendingUserMessage }], content_text: pendingUserMessage },
            { role: "assistant", content_blocks: finalMessage.content, content_text: finalText },
            { role: "user", content_blocks: toolResults, content_text: "" },
          ],
          tokens_used: totalTokens,
          estimated_tokens: preflight.estimated_tokens,
          is_free_preview: false,
        });

        pendingUserMessage = "";
        messages = [...messages, { role: "assistant", content: finalMessage.content }, { role: "user", content: toolResults }];
      }

      await sendEvent({ type: "error", message: "Tool loop exceeded MAX_STEPS" });
      await writer.close();
    } catch (error) {
      await chatAbort(token, {
        session_id: preflight.session_id,
        reservation_id: preflight.reservation_id,
        partial_messages: pendingUserMessage
          ? [{ role: "user", content_blocks: [{ type: "text", text: pendingUserMessage }], content_text: pendingUserMessage }]
          : undefined,
      });

      if ((error as Error).name === "AbortError") {
        await sendEvent({ type: "error", message: "Client disconnected" });
      } else {
        await sendEvent({ type: "error", message: "Coach stream error" });
      }
      await writer.close();
    }
  })();

  return new Response(stream.readable, {
    headers: {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache",
      Connection: "keep-alive",
    },
  });
}
```

**Step 4: Run test to verify it passes**
Run: `cd frontend && npm run test -- route.test.ts`
Expected: PASS.

**Step 5: Commit (optional)**
Only if requested.

---

### Task 8: Update Coach UI to Consume Streaming Events

**Parallel:** no
**Blocked by:** Task 7
**Owned files:** `frontend/src/components/coach/stream/reducer.ts`, `frontend/src/components/coach/stream/useASPStream.ts`, `frontend/src/app/(dashboard)/coach/page.tsx`, `frontend/src/components/coach/stream/reducer.test.ts`

**Files:**
- Create: `frontend/src/components/coach/stream/reducer.ts`
- Create: `frontend/src/components/coach/stream/useASPStream.ts`
- Modify: `frontend/src/app/(dashboard)/coach/page.tsx`
- Create: `frontend/src/components/coach/stream/reducer.test.ts`

**Step 1: Write the failing test**
```ts
// frontend/src/components/coach/stream/reducer.test.ts
import { reducer } from "./reducer";

test("handles tool + thinking events", () => {
  const state = reducer(undefined, { type: "thinking", text: "..." } as any);
  expect(state.thinking).toContain("...");
});
```

**Step 2: Run test to verify it fails**
Run: `cd frontend && npm run test -- reducer.test.ts`
Expected: FAIL because reducer does not exist.

**Step 3: Write minimal implementation**
```ts
// frontend/src/components/coach/stream/reducer.ts
import type { AspEvent } from "@/lib/coach/asp";

type State = {
  messages: { role: "assistant" | "user"; content: string }[];
  thinking: string;
  toolStatus: string | null;
  error: string | null;
};

const initialState: State = { messages: [], thinking: "", toolStatus: null, error: null };

export function reducer(state: State = initialState, event: AspEvent): State {
  if (event.type === "text") {
    const last = state.messages[state.messages.length - 1];
    const messages = last && last.role === "assistant"
      ? [...state.messages.slice(0, -1), { role: "assistant", content: last.content + event.text }]
      : [...state.messages, { role: "assistant", content: event.text }];
    return { ...state, messages };
  }
  if (event.type === "thinking") {
    return { ...state, thinking: state.thinking + event.text };
  }
  if (event.type === "tool") {
    return { ...state, toolStatus: `Running ${event.name}...` };
  }
  if (event.type === "tool_result") {
    return { ...state, toolStatus: null };
  }
  if (event.type === "error") {
    return { ...state, error: event.message };
  }
  return state;
}
```

```ts
// frontend/src/components/coach/stream/useASPStream.ts
import { useReducer } from "react";
import { reducer } from "./reducer";
import type { AspEvent } from "@/lib/coach/asp";

export function useASPStream() {
  const [state, dispatch] = useReducer(reducer, undefined);
  const handleEvent = (event: AspEvent) => dispatch(event);
  return { state, handleEvent };
}
```

**Step 4: Run test to verify it passes**
Run: `cd frontend && npm run test -- reducer.test.ts`
Expected: PASS.

**Step 5: Commit (optional)**
Only if requested.

---

### Task 9: Update Env + Docs for New Flow

**Parallel:** no
**Blocked by:** Task 8
**Owned files:** `.env.example`, `docs/api.md`, `frontend/.env.local`

**Files:**
- Modify: `.env.example`
- Modify: `docs/api.md`
- Modify: `frontend/.env.local` (dev convenience)

**Step 1: Write the failing test**
```python
# tests/test_env_example.py

def test_env_example_includes_anthropic_key():
    content = open(".env.example", encoding="utf-8").read()
    assert "ANTHROPIC_API_KEY" in content
    assert "COACH_MODEL_ID" in content
    assert "COACH_MAX_STEPS" in content
```

**Step 2: Run test to verify it fails**
Run: `source .venv/bin/activate && PYTHONPATH=src pytest tests/test_env_example.py -q`
Expected: FAIL until `.env.example` is updated.

**Step 3: Write minimal implementation**
```env
# .env.example
ANTHROPIC_API_KEY=sk-ant-...
COACH_MODEL_ID=claude-opus-4-5-20250514
COACH_MAX_STEPS=10
BACKEND_URL=http://localhost:8000
```

Update `docs/api.md` to remove `/api/v1/coach/chat` and add:
- `GET /api/v1/coach/tools/schema`
- `POST /api/v1/coach/tools/execute`
- `POST /api/v1/coach/chat/preflight`
- `POST /api/v1/coach/chat/record`
- `POST /api/v1/coach/chat/abort`

Document that `ANTHROPIC_API_KEY` must be available to the Next.js server runtime (Vercel/Docker env), not only `.env.local`.

**Step 4: Run test to verify it passes**
Run: `source .venv/bin/activate && PYTHONPATH=src pytest tests/test_env_example.py -q`
Expected: PASS.

**Step 5: Commit (optional)**
Only if requested.
