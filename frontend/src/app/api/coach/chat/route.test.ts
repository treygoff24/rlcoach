const mockChatPreflight = jest.fn().mockResolvedValue({
  session_id: "session-1",
  budget_remaining: 1000,
  is_free_preview: false,
  history: [],
  system_message: "system",
  estimated_tokens: 100,
  reservation_id: "reservation-1",
});

const mockGetToolSchema = jest.fn().mockResolvedValue({ tools: [] });
const mockExecuteTool = jest.fn();
const mockChatRecord = jest.fn().mockResolvedValue({ recorded: true });
const mockChatAbort = jest.fn().mockResolvedValue({ aborted: true });

jest.mock("@/lib/coach/backend", () => ({
  chatPreflight: (...args: unknown[]) => mockChatPreflight(...args),
  getToolSchema: (...args: unknown[]) => mockGetToolSchema(...args),
  executeTool: (...args: unknown[]) => mockExecuteTool(...args),
  chatRecord: (...args: unknown[]) => mockChatRecord(...args),
  chatAbort: (...args: unknown[]) => mockChatAbort(...args),
}));

const streamMock = {
  async *[Symbol.asyncIterator]() {
    yield { type: "message_stop", stop_reason: "end_turn" };
  },
  finalMessage: async () => ({
    content: [{ type: "text", text: "hi" }],
    stop_reason: "end_turn",
    usage: {
      input_tokens: 1,
      output_tokens: 1,
      cache_creation_input_tokens: 0,
      cache_read_input_tokens: 0,
    },
  }),
};

const mockStream = jest.fn(() => streamMock);

jest.mock("@/lib/coach/anthropic/client", () => ({
  anthropicClient: {
    messages: {
      stream: (..._args: unknown[]) => mockStream(),
    },
  },
}));

jest.mock("@/lib/coach/anthropic/adapter", () => ({
  mapSdkEvent: jest.fn(() => []),
}));

jest.mock("@/lib/auth", () => ({
  auth: jest.fn().mockResolvedValue({ accessToken: "test-token" }),
}));

import { TextEncoder } from "util";

if (typeof (global as any).TransformStream === "undefined") {
  (global as any).TransformStream = class {
    readable = {};
    writable = {
      getWriter: () => ({
        write: async () => {},
        close: async () => {},
      }),
    };
  };
}

if (typeof (global as any).TextEncoder === "undefined") {
  (global as any).TextEncoder = TextEncoder;
}

if (typeof (global as any).Response === "undefined") {
  class MockHeaders {
    private map: Map<string, string>;

    constructor(init?: Record<string, string>) {
      this.map = new Map(Object.entries(init || {}));
    }

    get(name: string) {
      return this.map.get(name) ?? this.map.get(name.toLowerCase()) ?? null;
    }
  }

  class MockResponse {
    headers: MockHeaders;

    constructor(_body?: unknown, init?: { headers?: Record<string, string> }) {
      this.headers = new MockHeaders(init?.headers);
    }
  }

  (global as any).Response = MockResponse;
}

import { POST } from "./route";

describe("coach chat route", () => {
  it("returns a streaming response", async () => {
    process.env.COACH_MODEL_ID = "claude-test";
    const request = {
      json: async () => ({ message: "hi" }),
      headers: {
        get: (name: string) =>
          name.toLowerCase() === "authorization" ? "Bearer test" : null,
      },
      signal: undefined,
    } as unknown as Request;
    const response = await POST(request);
    expect(response.headers.get("Content-Type")).toContain(
      "text/event-stream",
    );
  });
});
