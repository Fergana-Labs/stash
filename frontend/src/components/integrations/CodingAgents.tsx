"use client";

import CopyableCommandBlock from "@/components/CopyableCommandBlock";

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

/** Coding agents connect by running one command, which finds every agent on
 *  the machine and wires its hooks. There is deliberately no per-agent
 *  connected/disconnected state: the uploaded `agent_name` is whatever the
 *  user named their agent, not which harness produced it, so claiming
 *  "Claude Code: connected" would be a guess dressed as a fact. */
export default function CodingAgents({ agentNames }: { agentNames: string[] }) {
  return (
    <div className="flex flex-col gap-4">
      <div className="rounded-xl border border-border bg-surface p-5">
        <h3 className="text-[14px] font-semibold text-foreground">
          One command wires up every agent on your machine
        </h3>
        <p className="mt-1 max-w-2xl text-[13px] text-muted-foreground">
          The installer signs you in, finds the coding agents you already have, and turns on
          session recording. From then on their transcripts land in your stash, and they can read
          everything else in it.
        </p>
        <div className="mt-3">
          <CopyableCommandBlock commands={INSTALL_COMMAND} />
        </div>
        {agentNames.length > 0 && (
          <p className="mt-3 text-[12.5px] text-muted-foreground">
            Sending sessions now:{" "}
            <span className="text-foreground">{agentNames.join(", ")}</span>
          </p>
        )}
      </div>

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
        {CODING_AGENTS.map((agent) => (
          <div
            key={agent.binary}
            className="flex flex-col gap-1 rounded-xl border border-border bg-surface px-4 py-3.5"
          >
            <div className="text-[13.5px] font-medium text-foreground">{agent.name}</div>
            <code className="font-mono text-[11.5px] text-muted-foreground">{agent.binary}</code>
          </div>
        ))}
      </div>
    </div>
  );
}
