"use client";

import CopyableCommandBlock from "@/components/CopyableCommandBlock";
import {
  ClaudeCodeIcon,
  CodexIcon,
  CursorIcon,
  GeminiCliIcon,
  HermesIcon,
  OpenClawIcon,
  OpenCodeIcon,
} from "@/components/integrations/BrandIcons";

// The agents `stash install` wires up — the same list the CLI walks
// (_SUPPORTED_AGENTS in cli/main.py). Keep the two in step: an agent listed
// here that the CLI can't wire is a promise the product doesn't keep.
export const CODING_AGENTS = [
  { name: "Claude Code", binary: "claude", icon: <ClaudeCodeIcon /> },
  { name: "Codex", binary: "codex", icon: <CodexIcon /> },
  { name: "Cursor", binary: "cursor-agent", icon: <CursorIcon /> },
  { name: "OpenCode", binary: "opencode", icon: <OpenCodeIcon /> },
  { name: "Gemini CLI", binary: "gemini", icon: <GeminiCliIcon /> },
  { name: "OpenClaw", binary: "openclaw", icon: <OpenClawIcon /> },
  { name: "Hermes", binary: "hermes", icon: <HermesIcon /> },
];

export type CodingAgent = (typeof CODING_AGENTS)[number];

const INSTALL_COMMAND = `bash -c "$(curl -fsSL https://joinstash.ai/install)"`;

// A coding agent is two integrations wearing one name — it writes transcripts
// in and reads the stash back out — so it gets a box per direction with the
// half that applies. One install command serves both, which is why the two
// dialogs differ in what they explain rather than what they run. There is
// deliberately no per-agent connected state: the uploaded `agent_name` is
// whatever the user named their agent, not which harness produced it, so
// "Claude Code: connected" would be a guess dressed as a fact.
export const AGENT_COPY = {
  in: {
    label: (name: string) => `${name} transcripts`,
    blurb: (name: string) => `Add ${name} transcripts to your Stash.`,
    title: (name: string) => `Record ${name} sessions`,
    description:
      "One command turns on session recording for every coding agent on your machine, this one included.",
  },
  out: {
    label: (name: string) => `${name} access`,
    blurb: (name: string) => `Give ${name} read access to your Stash.`,
    title: (name: string) => `Give ${name} access`,
    description:
      "One command gives every coding agent on your machine read access, this one included.",
  },
} as const;

/** One command, both directions. The MCP route to a stash is its own box
 *  under Outputs — repeating it inside every agent dialog turned one answer
 *  into a choice the user has no basis to make. */
export function agentDialogBody() {
  return (
    <div className="flex min-w-0 flex-col gap-3">
      <CopyableCommandBlock commands={INSTALL_COMMAND} />
    </div>
  );
}
