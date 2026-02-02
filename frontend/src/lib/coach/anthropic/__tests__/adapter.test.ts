import { mapSdkEvent } from "../adapter";

it("maps deltas to ASP events", () => {
  const events = mapSdkEvent({
    type: "content_block_delta",
    delta: { type: "text_delta", text: "hi" },
    index: 0,
  } as any);
  expect(events[0].type).toBe("text");
});
