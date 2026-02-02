import { useReducer } from "react";

import type { StreamAction } from "./reducer";
import { initialState, reducer } from "./reducer";

export function useASPStream() {
  const [state, dispatch] = useReducer(reducer, initialState);
  const handleEvent = (event: StreamAction) => dispatch(event);
  return { state, handleEvent };
}
