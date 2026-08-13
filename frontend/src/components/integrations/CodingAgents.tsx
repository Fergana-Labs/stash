"use client";

import { useState } from "react";
import { Bot } from "lucide-react";

import CopyableCommandBlock from "@/components/CopyableCommandBlock";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";

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

const INSTALL_COMMAND = `bash -c "$(curl -fsSL https://joinstash.ai/install)"`;

const MCP_CLIENT_CONFIG = `{
  "mcpServers": {
    "stash": { "command": "stash-mcp" }
  }
}`;

type Agent = (typeof CODING_AGENTS)[number];

// A coding agent is two integrations wearing one name — it writes transcripts
// in and reads the stash back out — so it's listed under each direction with
// the half that applies. One install command serves both, which is why the
// dialogs differ in what they explain rather than what they run.
const COPY = {
  in: {
    blurb: "Its sessions land in your stash as transcripts, searchable like anything else.",
    dialogTitle: (name: string) => `Record ${name} sessions`,
    dialogDescription: "One command turns on session recording for every coding agent on your machine, this one included.",
    note: (binary: string) => (
      <>
        The installer signs you in, looks for <code className="font-mono text-[11.5px] text-foreground">{binary}</code>{" "}
        on your PATH, and hooks it so every session it runs is uploaded when it ends.
      </>
    ),
  },
  out: {
    blurb: "Give it read access to everything in your stash while it works.",
    dialogTitle: (name: string) => `Give ${name} access`,
    dialogDescription: "Two ways in, depending on what the agent speaks.",
    note: (binary: string) => (
      <>
        The installer adds Stash&apos;s commands to{" "}
        <code className="font-mono text-[11.5px] text-foreground">{binary}</code>&apos;s context, so
        it can search and read your stash mid-session.
      </>
    ),
  },
} as const;

/** The coding agents Stash can wire up, one card each. Rendered once per
 *  direction: under Inputs they're where transcripts come from, under Outputs
 *  they're something you hand the stash to. There is deliberately no per-agent
 *  connected state — the uploaded `agent_name` is whatever the user named
 *  their agent, not which harness produced it, so "Claude Code: connected"
 *  would be a guess dressed as a fact. */
export default function CodingAgents({
  direction,
  agentNames = [],
}: {
  direction: "in" | "out";
  agentNames?: string[];
}) {
  const [open, setOpen] = useState<Agent | null>(null);
  const copy = COPY[direction];

  return (
    <div className="flex flex-col gap-3">
      {direction === "in" && agentNames.length > 0 && (
        <p className="text-[12.5px] text-muted-foreground">
          Sending sessions now: <span className="text-foreground">{agentNames.join(", ")}</span>
        </p>
      )}

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {CODING_AGENTS.map((agent) => (
          <div
            key={agent.binary}
            className="flex flex-col gap-2.5 rounded-xl border border-border bg-surface p-4"
          >
            <div className="flex items-center gap-2.5">
              <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md bg-raised">
                <Bot className="h-4 w-4 text-dim" />
              </span>
              <button
                type="button"
                onClick={() => setOpen(agent)}
                className="truncate text-left text-[14px] font-medium text-foreground hover:underline"
              >
                {agent.name}
              </button>
            </div>

            <p className="min-h-[34px] text-[12.5px] leading-snug text-muted-foreground">
              {copy.blurb}
            </p>

            <Button
              size="sm"
              variant="secondary"
              className="self-start"
              onClick={() => setOpen(agent)}
            >
              Set up
            </Button>
          </div>
        ))}
      </div>

      <Dialog open={open !== null} onOpenChange={(v) => !v && setOpen(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{open && copy.dialogTitle(open.name)}</DialogTitle>
            <DialogDescription>{copy.dialogDescription}</DialogDescription>
          </DialogHeader>
          <div className="flex min-w-0 flex-col gap-3">
            <CopyableCommandBlock commands={INSTALL_COMMAND} />
            <p className="text-[12.5px] text-muted-foreground">{open && copy.note(open.binary)}</p>
            {direction === "out" && (
              <>
                <div className="text-[12px] font-medium text-dim">
                  Or, if it speaks MCP, point it at the Stash server
                </div>
                <CopyableCommandBlock commands={MCP_CLIENT_CONFIG} />
              </>
            )}
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
