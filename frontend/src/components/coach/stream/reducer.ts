import type { AspEvent } from "@/lib/coach/asp";

export type Message = { role: "assistant" | "user"; content: string };

export type StreamAction = AspEvent | { type: "user_message"; text: string };

export type StreamState = {
  messages: Message[];
  thinking: string;
  toolStatus: string | null;
  error: string | null;
};

export const initialState: StreamState = {
  messages: [],
  thinking: "",
  toolStatus: null,
  error: null,
};

export function reducer(
  state: StreamState = initialState,
  event: StreamAction,
): StreamState {
  if (event.type === "user_message") {
    return {
      ...state,
      thinking: "",
      toolStatus: null,
      error: null,
      messages: [
        ...state.messages,
        { role: "user" as const, content: event.text },
      ],
    };
  }
  if (event.type === "text") {
    const last = state.messages[state.messages.length - 1];
    const messages =
      last && last.role === "assistant"
        ? [
            ...state.messages.slice(0, -1),
            { role: "assistant" as const, content: last.content + event.text },
          ]
        : [...state.messages, { role: "assistant" as const, content: event.text }];
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
  if (event.type === "message_stop") {
    return { ...state, toolStatus: null };
  }
  return state;
}
