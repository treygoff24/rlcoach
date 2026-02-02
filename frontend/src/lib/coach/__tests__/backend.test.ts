import { getToolSchema } from "../backend";

describe("backend client", () => {
  beforeEach(() => {
    global.fetch = jest.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ tools: [] }),
    }) as jest.Mock;
  });

  afterEach(() => {
    jest.resetAllMocks();
  });

  it("fetches tool schema", async () => {
    await expect(getToolSchema("test-token")).resolves.toHaveProperty("tools");
    expect(global.fetch).toHaveBeenCalled();
  });
});
