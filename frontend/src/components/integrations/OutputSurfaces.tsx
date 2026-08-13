"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import CopyableCommandBlock from "@/components/CopyableCommandBlock";

// `stash-mcp` is a console script (pyproject.toml: stash-mcp =
// "cli.mcp_server:main"), speaking stdio and reading the CLI's stored config —
// so a client needs no key of its own, only a machine where `stash signin` has
// run. Deliberately no tool count here: it drifts every time cli/mcp_server.py
// gains a tool, and a stale number in the UI is worse than no number.
const MCP_CLIENT_CONFIG = `{
  "mcpServers": {
    "stash": { "command": "stash-mcp" }
  }
}`;

const CLI_SETUP = `uv tool install stashai\nstash signin`;

const CLI_USAGE = `stash search "org isolation"\nstash vfs "ls /"\nstash vfs "cat '/files/spec.md'"`;

function OutputCard({
  title,
  blurb,
  children,
  footer,
}: {
  title: string;
  blurb: string;
  children: React.ReactNode;
  footer?: React.ReactNode;
}) {
  return (
    <div className="flex flex-col gap-3 rounded-xl border border-border bg-surface p-5">
      <div>
        <h3 className="text-[14px] font-semibold text-foreground">{title}</h3>
        <p className="mt-1 max-w-2xl text-[13px] text-muted-foreground">{blurb}</p>
      </div>
      {children}
      {footer}
    </div>
  );
}

/** The ways an agent reads a stash: MCP, the CLI, and the HTTP API. These are
 *  setup instructions rather than connect buttons — the thing being configured
 *  lives on the user's machine, not on our side. */
export default function OutputSurfaces() {
  // The app proxies /api/v1 to the backend, so its own origin is the correct
  // base for every deployment — hardcoding api.joinstash.ai would hand
  // self-hosters a URL that isn't theirs.
  const [origin, setOrigin] = useState("");
  useEffect(() => setOrigin(window.location.origin), []);

  return (
    <div className="flex flex-col gap-3">
      <OutputCard
        title="MCP server"
        blurb="Point any MCP client at your stash — Claude Desktop, Cursor, anything that speaks MCP. It exposes search, the VFS, your sources, sessions, and the Memory wiki as tools."
      >
        <div className="flex flex-col gap-2">
          <div className="text-[12px] font-medium text-dim">1. Install the CLI and sign in</div>
          <CopyableCommandBlock commands={CLI_SETUP} />
          <div className="mt-1 text-[12px] font-medium text-dim">
            2. Add it to your client&apos;s MCP config
          </div>
          <CopyableCommandBlock commands={MCP_CLIENT_CONFIG} />
          <p className="text-[12px] text-muted-foreground">
            The server reads the CLI&apos;s stored credentials, so the client needs no key of its
            own.
          </p>
        </div>
      </OutputCard>

      <OutputCard
        title="CLI"
        blurb="Read and write your stash from any terminal or script. The same commands your coding agents use."
      >
        <CopyableCommandBlock commands={CLI_USAGE} />
      </OutputCard>

      <OutputCard
        title="HTTP API"
        blurb="Everything the app can do, over HTTP, authenticated with an API key."
        footer={
          <Link href="/settings" className="text-[12.5px] font-medium text-brand-600 hover:underline">
            Manage API keys in Settings →
          </Link>
        }
      >
        <CopyableCommandBlock
          commands={`curl -H "Authorization: Bearer <your-key>" \\\n  ${origin || "https://your-stash"}/api/v1/me/vitals`}
        />
      </OutputCard>
    </div>
  );
}
