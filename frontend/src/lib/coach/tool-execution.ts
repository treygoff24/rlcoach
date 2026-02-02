import { executeTool } from "./backend";

export type ToolCall = {
  name: string;
  input: Record<string, unknown>;
};

export async function runTool(
  token: string,
  tool: ToolCall,
): Promise<unknown> {
  const result = await executeTool(token, tool.name, tool.input);
  return result.result;
}
