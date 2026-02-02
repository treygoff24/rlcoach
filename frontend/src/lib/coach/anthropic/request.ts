import type {
  MessageParam,
  Tool,
} from "@anthropic-ai/sdk/resources/messages";

export type CoachStreamRequest = {
  model: string;
  max_tokens: number;
  system: string;
  messages: MessageParam[];
  tools?: Tool[];
  thinking?: {
    type: "enabled";
    budget_tokens: number;
  };
};
