import { useReducer } from "react";

import type { StreamAction } from "./reducer";
import { reducer } from "./reducer";

export function useASPStream() {
  const [state, dispatch] = useReducer(reducer, undefined);
  const handleEvent = (event: StreamAction) => dispatch(event);
  return { state, handleEvent };
}
