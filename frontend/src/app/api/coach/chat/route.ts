import { auth } from "@/lib/auth";
import { mapSdkEvent } from "@/lib/coach/anthropic/adapter";
import { anthropicClient } from "@/lib/coach/anthropic/client";
import {
  chatAbort,
  chatPreflight,
  chatRecord,
  executeTool,
  getToolSchema,
} from "@/lib/coach/backend";

export const dynamic = "force-dynamic";
export const maxDuration = 300;

const MAX_STEPS = Number(process.env.COACH_MAX_STEPS || 10);
const DEFAULT_THINKING_BUDGET = 32_000;

const resolveThinkingBudget = () => {
  const raw = process.env.EXTENDED_THINKING_BUDGET;
  if (!raw) return DEFAULT_THINKING_BUDGET;
  const parsed = Number(raw);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : DEFAULT_THINKING_BUDGET;
};

async function resolveAccessToken(request: Request): Promise<string | null> {
  const header = request.headers.get("authorization");
  if (header?.startsWith("Bearer ")) {
    return header.slice("Bearer ".length);
  }
  const session = await auth();
  return session?.accessToken ?? null;
}

export async function POST(request: Request) {
  const modelId = process.env.COACH_MODEL_ID;
  if (!modelId) {
    return new Response(
      JSON.stringify({ error: "COACH_MODEL_ID environment variable required" }),
      { status: 500 },
    );
  }

  const { message, session_id, replay_id } = await request.json();
  const token = await resolveAccessToken(request);

  if (!token) {
    return new Response(JSON.stringify({ error: "Unauthorized" }), { status: 401 });
  }

  const preflight = await chatPreflight(token, {
    message,
    session_id,
    replay_id,
  });

  if (preflight.budget_remaining <= 0) {
    return new Response(JSON.stringify({ error: "Budget exhausted" }), {
      status: 402,
    });
  }

  const { tools } = await getToolSchema(token);

  const stream = new TransformStream();
  const writer = stream.writable.getWriter();
  const encoder = new TextEncoder();
  const thinkingBudget = resolveThinkingBudget();

  const sendEvent = async (event: unknown) => {
    await writer.write(encoder.encode(`data: ${JSON.stringify(event)}\n\n`));
  };

  (async () => {
    const recordMessages: Array<{
      role: string;
      content_blocks: unknown[];
      content_text?: string;
    }> = [
      {
        role: "user",
        content_blocks: [{ type: "text", text: message }],
        content_text: message,
      },
    ];

    try {
      await sendEvent({
        type: "ack",
        session_id: preflight.session_id,
        budget_remaining: preflight.budget_remaining,
        is_free_preview: preflight.is_free_preview,
      });

      let messages = [
        ...preflight.history,
        { role: "user", content: [{ type: "text", text: message }] },
      ];
      let totalTokens = 0;
      let totalThinkingTokens = 0;
      const validToolNames = new Set(
        tools.map((tool: { name: string }) => tool.name),
      );

      for (let step = 0; step < MAX_STEPS; step += 1) {
        let iterationText = "";
        let iterationThinking = "";
        let sawMessageStop = false;

        const streamResponse = anthropicClient.messages.stream(
          {
            model: modelId,
          max_tokens: 8192,
          system: preflight.system_message,
          messages,
          tools,
            thinking: { type: "enabled", budget_tokens: thinkingBudget },
          },
          { signal: request.signal },
        );

        const toolCalls: { id: string; name: string; input: Record<string, unknown> }[] =
          [];

        for await (const event of streamResponse) {
          for (const aspEvent of mapSdkEvent(event)) {
            if (aspEvent.type === "message_stop") {
              sawMessageStop = true;
            }
            await sendEvent(aspEvent);
            if (aspEvent.type === "text") {
              iterationText += aspEvent.text;
            }
            if (aspEvent.type === "thinking") {
              iterationThinking += aspEvent.text;
            }
            if (aspEvent.type === "tool") {
              toolCalls.push({
                id: aspEvent.tool_use_id,
                name: aspEvent.name,
                input: aspEvent.input,
              });
            }
          }
        }

        const finalMessage = await streamResponse.finalMessage();
        totalTokens += finalMessage.usage.input_tokens + finalMessage.usage.output_tokens;
        if (iterationThinking.length > 0) {
          totalThinkingTokens += Math.ceil(iterationThinking.length / 4);
        }

        recordMessages.push({
          role: "assistant",
          content_blocks: finalMessage.content,
          content_text: iterationText,
        });

        if (toolCalls.length === 0) {
          await chatRecord(token, {
            session_id: preflight.session_id,
            reservation_id: preflight.reservation_id,
            messages: recordMessages,
            tokens_used: totalTokens,
            thinking_tokens: totalThinkingTokens,
            estimated_tokens: preflight.estimated_tokens,
            is_free_preview: preflight.is_free_preview,
          });

          if (!sawMessageStop) {
            await sendEvent({
              type: "message_stop",
              stop_reason: finalMessage.stop_reason ?? "end_turn",
            });
          }
          await writer.close();
          return;
        }

        const executeToolWithRetry = async (
          tool: { id: string; name: string; input: Record<string, unknown> },
        ) => {
          const attempt = async () => {
            if (request.signal?.aborted) {
              throw new DOMException("Aborted", "AbortError");
            }
            if (!validToolNames.has(tool.name)) {
              throw new Error(`Unknown tool: ${tool.name}`);
            }
            return executeTool(token, tool.name, tool.input);
          };

          try {
            return await attempt();
          } catch (error) {
            if (error instanceof DOMException && error.name === "AbortError") {
              throw error;
            }
            if (error instanceof Error && error.message.startsWith("Unknown tool")) {
              throw error;
            }
            await new Promise((resolve) => setTimeout(resolve, 500));
            return await attempt();
          }
        };

        const toolResults = await Promise.all(
          toolCalls.map(async (tool) => {
            try {
              const result = await executeToolWithRetry(tool);
              await sendEvent({
                type: "tool_result",
                tool_use_id: tool.id,
                content: result.result,
              });
              return {
                type: "tool_result",
                tool_use_id: tool.id,
                content: result.result,
              };
            } catch (error) {
              if (error instanceof DOMException && error.name === "AbortError") {
                throw error;
              }
              console.error(`Tool ${tool.name} failed`, error);
              const errorPayload = {
                error: "Tool execution failed",
                tool: tool.name,
                details:
                  error instanceof Error ? error.message : "Unknown error",
              };
              await sendEvent({
                type: "tool_result",
                tool_use_id: tool.id,
                content: errorPayload,
              });
              return {
                type: "tool_result",
                tool_use_id: tool.id,
                content: errorPayload,
              };
            }
          }),
        );

        recordMessages.push({
          role: "user",
          content_blocks: toolResults,
          content_text: "",
        });

        messages = [
          ...messages,
          { role: "assistant", content: finalMessage.content },
          { role: "user", content: toolResults },
        ];
      }

      await sendEvent({ type: "error", message: "Tool loop exceeded MAX_STEPS" });
      await writer.close();
    } catch (error) {
      await chatAbort(token, {
        session_id: preflight.session_id,
        reservation_id: preflight.reservation_id,
        partial_messages: recordMessages.length ? recordMessages : undefined,
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
