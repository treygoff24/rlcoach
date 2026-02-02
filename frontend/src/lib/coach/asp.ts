export type AspEvent =
  | { type: "ack" }
  | { type: "thinking"; text: string }
  | { type: "text"; text: string }
  | { type: "tool"; tool_use_id: string; name: string; input: Record<string, unknown> }
  | { type: "tool_result"; tool_use_id: string; content: unknown }
  | { type: "message_stop"; stop_reason: string }
  | { type: "error"; message: string };
