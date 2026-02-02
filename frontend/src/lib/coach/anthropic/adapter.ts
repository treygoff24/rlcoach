import type { MessageStreamEvent } from "@anthropic-ai/sdk/resources/messages";

import type { AspEvent } from "../asp";

export function mapSdkEvent(event: MessageStreamEvent): AspEvent[] {
  if (event.type === "content_block_delta" && event.delta?.type === "text_delta") {
    return [{ type: "text", text: event.delta.text }];
  }
  if (
    event.type === "content_block_delta" &&
    event.delta?.type === "thinking_delta"
  ) {
    return [{ type: "thinking", text: event.delta.thinking }];
  }
  if (
    event.type === "content_block_start" &&
    event.content_block?.type === "tool_use"
  ) {
    const input = event.content_block.input;
    const safeInput =
      typeof input === "object" && input !== null
        ? (input as Record<string, unknown>)
        : {};
    return [
      {
        type: "tool",
        tool_use_id: event.content_block.id,
        name: event.content_block.name,
        input: safeInput,
      },
    ];
  }
  if (event.type === "message_delta" && event.delta?.stop_reason) {
    return [{ type: "message_stop", stop_reason: event.delta.stop_reason }];
  }
  return [];
}
