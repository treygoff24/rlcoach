import { reducer } from "./reducer";

test("handles tool + thinking events", () => {
  const state = reducer(undefined, { type: "thinking", text: "..." } as any);
  expect(state.thinking).toContain("...");
});
