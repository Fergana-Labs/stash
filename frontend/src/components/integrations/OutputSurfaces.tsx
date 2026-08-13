"use client";

import Link from "next/link";
import { useEffect, useState, type ReactNode } from "react";
import { Braces, SquareTerminal, Waypoints } from "lucide-react";

import CopyableCommandBlock from "@/components/CopyableCommandBlock";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";

// `stash-mcp` is a console script (pyproject.toml: stash-mcp =
// "cli.mcp_server:main"), speaking stdio and reading the CLI's stored config —
// so a client needs no key of its own, only a machine where `stash signin` has
// run. Deliberately no tool count anywhere here: it drifts every time
// cli/mcp_server.py gains a tool, and a stale number is worse than no number.
const MCP_CLIENT_CONFIG = `{
  "mcpServers": {
    "stash": { "command": "stash-mcp" }
  }
}`;

const CLI_SETUP = `uv tool install stashai\nstash signin`;

const CLI_USAGE = `stash search "org isolation"\nstash vfs "ls /"\nstash vfs "cat '/files/spec.md'"`;

type Surface = {
  key: string;
  label: string;
  icon: typeof Waypoints;
  blurb: string;
  /** What the dialog shows once you pick this way out. */
  steps: ReactNode;
};

function Step({ n, children }: { n: number; children: ReactNode }) {
  return (
    <div className="flex flex-col gap-1.5">
      <div className="text-[12px] font-medium text-dim">
        {n}. {children}
      </div>
    </div>
  );
}

export const OUTPUT_SURFACES: Surface[] = [
  {
    key: "mcp",
    label: "MCP server",
    icon: Waypoints,
    blurb: "Point any MCP client at your stash — Claude Desktop, Cursor, anything that speaks MCP.",
    steps: (
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
    label: "CLI",
    icon: SquareTerminal,
    blurb: "Read and write your stash from any terminal or script — the same commands your agents use.",
    steps: (
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
    label: "HTTP API",
    icon: Braces,
    blurb: "Everything the app can do, over HTTP, authenticated with an API key.",
    steps: null,
  },
];

/** The API card's steps depend on where the app is served from, so they're
 *  built at render rather than baked into the constant above. */
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

/** One way out, as a card that matches the source cards on the inputs side.
 *  The setup lives behind the click instead of unfurled on the page — the
 *  inputs side doesn't print an OAuth flow inline either. */
function SurfaceCard({ surface, onOpen }: { surface: Surface; onOpen: () => void }) {
  const Icon = surface.icon;
  return (
    <div className="flex flex-col gap-2.5 rounded-xl border border-border bg-surface p-4">
      <div className="flex items-center gap-2.5">
        <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md bg-raised">
          <Icon className="h-4 w-4 text-dim" />
        </span>
        <button
          type="button"
          onClick={onOpen}
          className="truncate text-left text-[14px] font-medium text-foreground hover:underline"
        >
          {surface.label}
        </button>
      </div>

      <p className="min-h-[34px] text-[12.5px] leading-snug text-muted-foreground">
        {surface.blurb}
      </p>

      <Button size="sm" variant="secondary" className="self-start" onClick={onOpen}>
        Set up
      </Button>
    </div>
  );
}

export default function OutputSurfaces() {
  const [open, setOpen] = useState<Surface | null>(null);

  return (
    <>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {OUTPUT_SURFACES.map((s) => (
          <SurfaceCard key={s.key} surface={s} onOpen={() => setOpen(s)} />
        ))}
      </div>

      <Dialog open={open !== null} onOpenChange={(v) => !v && setOpen(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{open?.label}</DialogTitle>
            <DialogDescription>{open?.blurb}</DialogDescription>
          </DialogHeader>
          {open?.key === "api" ? <ApiSteps /> : open?.steps}
        </DialogContent>
      </Dialog>
    </>
  );
}
