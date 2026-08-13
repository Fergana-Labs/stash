"use client";

import Link from "next/link";
import { useEffect, useState, type ReactNode } from "react";
import { Braces, SquareTerminal, Waypoints } from "lucide-react";

import CopyableCommandBlock from "@/components/CopyableCommandBlock";

// `stash-mcp` is a console script (pyproject.toml: stash-mcp =
// "cli.mcp_server:main"), speaking stdio and reading the CLI's stored config —
// so a client needs no key of its own, only a machine where `stash signin` has
// run. Deliberately no tool count anywhere here: it drifts every time
// cli/mcp_server.py gains a tool, and a stale number is worse than no number.
export const MCP_CLIENT_CONFIG = `{
  "mcpServers": {
    "stash": { "command": "stash-mcp" }
  }
}`;

export const CLI_SETUP = `uv tool install stashai\nstash signin`;

const CLI_USAGE = `stash search "org isolation"\nstash vfs "ls /"\nstash vfs "cat '/files/spec.md'"`;

export function Step({ n, children }: { n: number; children: ReactNode }) {
  return <div className="text-[12px] font-medium text-dim">{n}. {children}</div>;
}

/** The API steps depend on where the app is served from, so they're a
 *  component rather than a constant. */
function ApiSteps() {
  // The app proxies /api/v1 to the backend, so its own origin is the correct
  // base for every deployment — hardcoding api.joinstash.ai would hand
  // self-hosters a URL that isn't theirs.
  const [origin, setOrigin] = useState("");
  useEffect(() => setOrigin(window.location.origin), []);

  return (
    <div className="flex min-w-0 flex-col gap-3">
      <Step n={1}>Mint a key</Step>
      <Link href="/settings" className="text-[12.5px] font-medium text-brand-600 hover:underline">
        Settings → API keys &amp; sessions →
      </Link>
      <Step n={2}>Call it</Step>
      <CopyableCommandBlock
        commands={`curl -H "Authorization: Bearer <your-key>" \\\n  ${origin || "https://your-stash"}/api/v1/me/vitals`}
      />
    </div>
  );
}

export type OutputSurface = {
  key: string;
  name: string;
  icon: typeof Waypoints;
  blurb: string;
  keywords: string;
  body: ReactNode;
};

/** The ways an agent or a script reads a stash. Each is one box on the
 *  Integrations grid; the setup lives in its dialog. */
export const OUTPUT_SURFACES: OutputSurface[] = [
  {
    key: "mcp",
    name: "MCP server",
    icon: Waypoints,
    blurb: "Point any MCP client at your stash — Claude Desktop, Cursor, anything that speaks MCP.",
    keywords: "mcp model context protocol claude desktop cursor stash-mcp",
    body: (
      <div className="flex min-w-0 flex-col gap-3">
        <Step n={1}>Install the CLI and sign in</Step>
        <CopyableCommandBlock commands={CLI_SETUP} />
        <Step n={2}>Add it to your client&apos;s MCP config</Step>
        <CopyableCommandBlock commands={MCP_CLIENT_CONFIG} />
        <p className="text-[12.5px] text-muted-foreground">
          The server reads the CLI&apos;s stored credentials, so the client needs no key of its own.
          It exposes search, the VFS, your sources, sessions, and the Memory wiki as tools.
        </p>
      </div>
    ),
  },
  {
    key: "cli",
    name: "CLI",
    icon: SquareTerminal,
    blurb: "Read and write your stash from any terminal or script — the same commands your agents use.",
    keywords: "cli terminal shell command line stash search vfs",
    body: (
      <div className="flex min-w-0 flex-col gap-3">
        <Step n={1}>Install and sign in</Step>
        <CopyableCommandBlock commands={CLI_SETUP} />
        <Step n={2}>Read anything</Step>
        <CopyableCommandBlock commands={CLI_USAGE} />
        <p className="text-[12.5px] text-muted-foreground">
          <code className="font-mono">stash --help</code> lists the rest.
        </p>
      </div>
    ),
  },
  {
    key: "api",
    name: "HTTP API",
    icon: Braces,
    blurb: "Everything the app can do, over HTTP, authenticated with an API key.",
    keywords: "api http rest curl key token",
    body: <ApiSteps />,
  },
];
