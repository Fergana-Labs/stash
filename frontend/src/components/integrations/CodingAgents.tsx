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

type Agent = (typeof CODING_AGENTS)[number];

/** Coding agents connect by running one command, which finds every agent on
 *  the machine and wires its hooks. There is deliberately no per-agent
 *  connected/disconnected state: the uploaded `agent_name` is whatever the
 *  user named their agent, not which harness produced it, so claiming
 *  "Claude Code: connected" would be a guess dressed as a fact. */
export default function CodingAgents({ agentNames }: { agentNames: string[] }) {
  const [open, setOpen] = useState<Agent | null>(null);

  return (
    <div className="flex flex-col gap-3">
      {agentNames.length > 0 && (
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
              Its transcripts land in your stash, and it reads everything else in there while it
              works.
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
            <DialogTitle>Connect {open?.name}</DialogTitle>
            <DialogDescription>
              One command wires up every coding agent on your machine, this one included.
            </DialogDescription>
          </DialogHeader>
          <div className="flex min-w-0 flex-col gap-3">
            <CopyableCommandBlock commands={INSTALL_COMMAND} />
            <p className="text-[12.5px] text-muted-foreground">
              The installer signs you in, looks for{" "}
              <code className="font-mono text-[11.5px] text-foreground">{open?.binary}</code> on your
              PATH, and turns on session recording for it. Run it again any time you add another
              agent.
            </p>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
