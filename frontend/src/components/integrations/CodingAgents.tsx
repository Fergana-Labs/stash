"use client";

import CopyableCommandBlock from "@/components/CopyableCommandBlock";
import { MCP_CLIENT_CONFIG } from "@/components/integrations/OutputSurfaces";

// The agents `stash install` wires up — the same list the CLI walks
// (_SUPPORTED_AGENTS in cli/main.py). Keep the two in step: an agent listed
// here that the CLI can't wire is a promise the product doesn't keep.
export const CODING_AGENTS = [
  { name: "Claude Code", binary: "claude" },
  { name: "Codex", binary: "codex" },
  { name: "Cursor", binary: "cursor-agent" },
  { name: "OpenCode", binary: "opencode" },
  { name: "Gemini CLI", binary: "gemini" },
  { name: "OpenClaw", binary: "openclaw" },
  { name: "Hermes", binary: "hermes" },
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
    blurb: "Its sessions land in your stash as transcripts, searchable like anything else.",
    title: (name: string) => `Record ${name} sessions`,
    description:
      "One command turns on session recording for every coding agent on your machine, this one included.",
  },
  out: {
    blurb: "Give it read access to everything in your stash while it works.",
    title: (name: string) => `Give ${name} access`,
    description: "Two ways in, depending on what the agent speaks.",
  },
} as const;

export function agentDialogBody(agent: CodingAgent, direction: "in" | "out") {
  return (
    <div className="flex min-w-0 flex-col gap-3">
      <CopyableCommandBlock commands={INSTALL_COMMAND} />
      {direction === "in" ? (
        <p className="text-[12.5px] text-muted-foreground">
          The installer signs you in, looks for{" "}
          <code className="font-mono text-[11.5px] text-foreground">{agent.binary}</code> on your
          PATH, and hooks it so every session it runs is uploaded when it ends.
        </p>
      ) : (
        <>
          <p className="text-[12.5px] text-muted-foreground">
            The installer adds Stash&apos;s commands to{" "}
            <code className="font-mono text-[11.5px] text-foreground">{agent.binary}</code>&apos;s
            context, so it can search and read your stash mid-session.
          </p>
          <div className="text-[12px] font-medium text-dim">
            Or, if it speaks MCP, point it at the Stash server
          </div>
          <CopyableCommandBlock commands={MCP_CLIENT_CONFIG} />
        </>
      )}
    </div>
  );
}
