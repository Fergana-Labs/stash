"use client";

import { useState } from "react";
import { Plus } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { ApiError, createMcpServer } from "@/lib/api";

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

/** The add-a-server form, shown in the dialog behind the "Custom MCP server"
 *  box. Registering one hands it to your cloud agent before every turn. */
export default function AddServerForm({ onAdded }: { onAdded: () => void }) {
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
