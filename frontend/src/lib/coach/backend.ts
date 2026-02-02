const BACKEND_URL = process.env.BACKEND_URL || "http://localhost:8000";

export async function getToolSchema(token: string) {
  const response = await fetch(`${BACKEND_URL}/api/v1/coach/tools/schema`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!response.ok) {
    throw new Error("Tool schema fetch failed");
  }
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
  if (!response.ok) {
    throw new Error("Tool execution failed");
  }
  return response.json();
}

export async function chatPreflight(
  token: string,
  payload: { message: string; session_id?: string; replay_id?: string },
) {
  const response = await fetch(`${BACKEND_URL}/api/v1/coach/chat/preflight`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    throw new Error("Preflight failed");
  }
  return response.json();
}

export async function chatRecord(
  token: string,
  payload: {
    session_id: string;
    reservation_id: string;
    messages: Array<{
      role: string;
      content_blocks: unknown[];
      content_text?: string;
    }>;
    tokens_used: number;
    thinking_tokens?: number;
    estimated_tokens: number;
    is_free_preview: boolean;
  },
) {
  const response = await fetch(`${BACKEND_URL}/api/v1/coach/chat/record`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    throw new Error("Record failed");
  }
  return response.json();
}

export async function chatAbort(
  token: string,
  payload: {
    session_id: string;
    reservation_id: string;
    partial_messages?: Array<{
      role: string;
      content_blocks: unknown[];
      content_text?: string;
    }>;
  },
) {
  const response = await fetch(`${BACKEND_URL}/api/v1/coach/chat/abort`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    throw new Error("Abort failed");
  }
  return response.json();
}
