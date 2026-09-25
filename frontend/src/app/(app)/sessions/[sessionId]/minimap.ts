// Pure mapping for the session minimap: every turn in the full transcript
// becomes one proportional block, toned so the human turns read as landmarks
// against the agent's work.

import type { MessageTurn } from "./transcript";

export type MinimapTone = "human" | "agent" | "faint";

// A session shorter than this fits on a screen or two, where a minimap is
// noise rather than navigation.
export const MINIMAP_MIN_TURNS = 15;

// Human turns are the landmarks the strip exists to surface; agent prose is
// the texture between them; tool calls and the scheduled-run system prompt
// are background. Tool-use events arrive as assistant turns with a tool_name.
export function minimapTone(turn: Pick<MessageTurn, "who" | "toolName">): MinimapTone {
  if (turn.who === "user") return "human";
  if (turn.who === "system") return "faint";
  return turn.toolName ? "faint" : "agent";
}

// Three tones from the app palette: the dedicated human accent, mid gray,
// and the border gray that recedes in both light and dark themes.
export const MINIMAP_TONE_CLASS: Record<MinimapTone, string> = {
  human: "bg-[var(--color-human)]",
  agent: "bg-[var(--color-muted-foreground)]",
  faint: "bg-[var(--color-border)]",
};
