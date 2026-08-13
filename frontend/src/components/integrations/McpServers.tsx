"use client";

import { useCallback, useEffect, useState } from "react";
import { Globe, Plus, SquareTerminal } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  ApiError,
  createMcpServer,
  deleteMcpServer,
  listMcpServers,
  type McpServer,
} from "@/lib/api";

// One "KEY=VALUE" line per header, parsed at submit time.
function parseHeaderLines(raw: string): Record<string, string> {
  const headers: Record<string, string> = {};
  for (const line of raw.split("\n")) {
    const trimmed = line.trim();
    if (!trimmed) continue;
    const eq = trimmed.indexOf("=");
    if (eq <= 0) throw new Error(`Headers must be KEY=VALUE lines; got "${trimmed}"`);
    headers[trimmed.slice(0, eq).trim()] = trimmed.slice(eq + 1).trim();
  }
  return headers;
}

function AddServerForm({ onAdded }: { onAdded: () => void }) {
  const [name, setName] = useState("");
  const [transport, setTransport] = useState<"stdio" | "http">("http");
  const [command, setCommand] = useState("");
  const [url, setUrl] = useState("");
  const [headerLines, setHeaderLines] = useState("");
  const [saving, setSaving] = useState(false);

  async function submit() {
    setSaving(true);
    try {
      const headers = transport === "http" ? parseHeaderLines(headerLines) : {};
      await createMcpServer({
        name: name.trim(),
        transport,
        ...(transport === "stdio" ? { command: command.trim() } : { url: url.trim(), headers }),
      });
      onAdded();
    } catch (e) {
      toast.error(e instanceof ApiError || e instanceof Error ? e.message : "Failed to add server");
    } finally {
      setSaving(false);
    }
  }

  const targetMissing = transport === "stdio" ? !command.trim() : !url.trim();

  return (
    <form
      className="flex min-w-0 flex-col gap-3"
      onSubmit={(e) => {
        e.preventDefault();
        void submit();
      }}
    >
      <Input
        aria-label="Server name"
        placeholder="Name (e.g. linear)"
        value={name}
        onChange={(e) => setName(e.target.value)}
      />
      <div className="flex gap-1 self-start rounded-md bg-muted p-1" role="radiogroup">
        {(["http", "stdio"] as const).map((t) => (
          <button
            key={t}
            type="button"
            role="radio"
            aria-checked={transport === t}
            onClick={() => setTransport(t)}
            className={`rounded px-3 py-1 text-xs font-medium ${
              transport === t ? "bg-surface text-foreground shadow-sm" : "text-muted-foreground"
            }`}
          >
            {t === "http" ? "Remote (HTTP)" : "Local (stdio)"}
          </button>
        ))}
      </div>
      {transport === "stdio" ? (
        <Input
          aria-label="Command"
          placeholder="Command (e.g. npx -y linear-mcp)"
          value={command}
          onChange={(e) => setCommand(e.target.value)}
        />
      ) : (
        <>
          <Input
            aria-label="URL"
            placeholder="URL (e.g. https://mcp.example.com/mcp)"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
          />
          <Textarea
            aria-label="Headers"
            placeholder={"Optional headers, one per line:\nAuthorization=Bearer …"}
            rows={2}
            value={headerLines}
            onChange={(e) => setHeaderLines(e.target.value)}
          />
        </>
      )}
      <Button type="submit" disabled={saving || !name.trim() || targetMissing} className="self-start">
        <Plus className="h-4 w-4" />
        Add server
      </Button>
    </form>
  );
}

/** A registered server, in the same card shape as every other integration. */
function ServerCard({ server, onRemoved }: { server: McpServer; onRemoved: () => void }) {
  const [removing, setRemoving] = useState(false);
  const Icon = server.transport === "stdio" ? SquareTerminal : Globe;
  const headerKeys = Object.keys(server.headers);

  async function remove() {
    setRemoving(true);
    try {
      await deleteMcpServer(server.id);
      onRemoved();
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Failed to remove server");
      setRemoving(false);
    }
  }

  return (
    <div className="flex flex-col gap-2.5 rounded-xl border border-border bg-surface p-4">
      <div className="flex items-center gap-2.5">
        <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md bg-raised">
          <Icon className="h-4 w-4 text-dim" />
        </span>
        <span className="truncate text-[14px] font-medium text-foreground">{server.name}</span>
      </div>

      <p className="min-h-[34px] break-all font-mono text-[11.5px] leading-snug text-muted-foreground">
        {server.transport === "stdio" ? server.command : server.url}
        {headerKeys.length > 0 && ` · headers: ${headerKeys.join(", ")}`}
      </p>

      <Button
        variant="ghost"
        size="sm"
        className="self-start px-2"
        onClick={() => void remove()}
        disabled={removing}
      >
        {removing ? "Removing…" : "Remove"}
      </Button>
    </div>
  );
}

/** The MCP-server registry: servers your cloud agent can call. Cards like
 *  everything else on the page, including the one that adds a new one — the
 *  form lives in its dialog rather than sitting open at the bottom of a grid. */
export default function McpServers({ onCountChange }: { onCountChange: (n: number) => void }) {
  const [servers, setServers] = useState<McpServer[] | null>(null);
  const [adding, setAdding] = useState(false);

  const refresh = useCallback(async () => {
    try {
      const rows = await listMcpServers();
      setServers(rows);
      onCountChange(rows.length);
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Failed to load MCP servers");
    }
  }, [onCountChange]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  return (
    <>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {servers?.map((s) => (
          <ServerCard key={s.id} server={s} onRemoved={() => void refresh()} />
        ))}

        <button
          type="button"
          onClick={() => setAdding(true)}
          className="flex min-h-[124px] flex-col items-center justify-center gap-2 rounded-xl border border-dashed border-border bg-surface/50 p-4 text-muted-foreground transition-colors hover:border-brand-300 hover:text-foreground"
        >
          <Plus className="h-5 w-5" />
          <span className="text-[13px] font-medium">Add a custom server</span>
        </button>
      </div>

      <Dialog open={adding} onOpenChange={setAdding}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Add an MCP server</DialogTitle>
            <DialogDescription>
              Your cloud agent gets it before every turn, alongside the tools Stash gives it
              natively.
            </DialogDescription>
          </DialogHeader>
          <AddServerForm
            onAdded={() => {
              setAdding(false);
              void refresh();
            }}
          />
        </DialogContent>
      </Dialog>
    </>
  );
}
