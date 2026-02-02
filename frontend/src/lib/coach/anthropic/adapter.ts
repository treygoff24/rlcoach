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
    return [
      {
        type: "tool",
        tool_use_id: event.content_block.id,
        name: event.content_block.name,
        input: event.content_block.input,
      },
    ];
  }
  if (event.type === "message_stop") {
    return [{ type: "message_stop", stop_reason: event.stop_reason }];
  }
  return [];
}
