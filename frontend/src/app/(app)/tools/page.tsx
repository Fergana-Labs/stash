"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Globe, Plus, Terminal, Wrench } from "lucide-react";
import { toast } from "sonner";
import { useBreadcrumbs } from "@/components/BreadcrumbContext";
import { useAuth } from "@/hooks/useAuth";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
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
      setName("");
      setCommand("");
      setUrl("");
      setHeaderLines("");
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
      className="rounded-lg border border-border bg-surface p-4"
      onSubmit={(e) => {
        e.preventDefault();
        void submit();
      }}
    >
      <h2 className="text-sm font-semibold">Add an MCP server</h2>
      <div className="mt-3 flex flex-col gap-3">
        <Input
          aria-label="Server name"
          placeholder="Name (e.g. linear)"
          value={name}
          onChange={(e) => setName(e.target.value)}
        />
        <div className="flex gap-1 rounded-md bg-muted p-1 self-start" role="radiogroup">
          {(["http", "stdio"] as const).map((t) => (
            <button
              key={t}
              type="button"
              role="radio"
              aria-checked={transport === t}
              onClick={() => setTransport(t)}
              className={`rounded px-3 py-1 text-xs font-medium ${
                transport === t
                  ? "bg-surface text-foreground shadow-sm"
                  : "text-muted-foreground"
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
      </div>
    </form>
  );
}

function ServerRow({ server, onRemoved }: { server: McpServer; onRemoved: () => void }) {
  const [removing, setRemoving] = useState(false);

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

  const headerKeys = Object.keys(server.headers);
  return (
    <li className="flex items-center gap-3 rounded-lg border border-border bg-surface px-4 py-3">
      {server.transport === "stdio" ? (
        <Terminal className="h-4 w-4 shrink-0 text-muted-foreground" />
      ) : (
        <Globe className="h-4 w-4 shrink-0 text-muted-foreground" />
      )}
      <div className="min-w-0 flex-1">
        <div className="text-sm font-medium">{server.name}</div>
        <div className="truncate text-xs text-muted-foreground">
          {server.transport === "stdio" ? server.command : server.url}
          {headerKeys.length > 0 && ` · headers: ${headerKeys.join(", ")}`}
        </div>
      </div>
      <Button variant="ghost" size="sm" onClick={() => void remove()} disabled={removing}>
        Remove
      </Button>
    </li>
  );
}

export default function ToolsPage() {
  const router = useRouter();
  const { user, loading } = useAuth();
  const [servers, setServers] = useState<McpServer[] | null>(null);

  useBreadcrumbs([{ label: "Tools" }], "tools");

  const refresh = useCallback(async () => {
    try {
      setServers(await listMcpServers());
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Failed to load MCP servers");
    }
  }, []);

  useEffect(() => {
    if (!loading && !user) router.push("/login");
  }, [user, loading, router]);

  useEffect(() => {
    if (user) void refresh();
  }, [user, refresh]);

  if (loading || !user) return null;

  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto flex max-w-2xl flex-col gap-6 p-6">
        <div>
          <h1 className="flex items-center gap-2 text-base font-semibold">
            <Wrench className="h-4 w-4" />
            Tools
          </h1>
          <p className="mt-1 text-sm text-muted-foreground">
            MCP servers registered here are available to your cloud agent, and installable locally
            with <code className="text-xs">stash tools install</code>.
          </p>
        </div>

        {servers !== null && servers.length === 0 && (
          <p className="text-sm text-muted-foreground">No MCP servers yet — add one below.</p>
        )}
        {servers !== null && servers.length > 0 && (
          <ul className="flex flex-col gap-2">
            {servers.map((s) => (
              <ServerRow key={s.id} server={s} onRemoved={() => void refresh()} />
            ))}
          </ul>
        )}

        <AddServerForm onAdded={() => void refresh()} />
      </div>
    </div>
  );
}
