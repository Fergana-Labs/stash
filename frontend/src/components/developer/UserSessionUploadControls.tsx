"use client";

import { MoreHorizontal, X } from "lucide-react";
import { useState } from "react";

import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { uploadTranscript } from "@/lib/api";

// Hand this user a session by uploading its .jsonl transcript. Behind a "…"
// menu: sessions normally arrive from the product's backend, so uploading
// one by hand is the unexpected path.
export default function UserSessionUploadControls({
  externalUserId,
  onAdded,
}: {
  externalUserId: string;
  onAdded: () => void;
}) {
  const [formOpen, setFormOpen] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const [sessionId, setSessionId] = useState("");
  const [agentName, setAgentName] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  function pickFile(picked: File) {
    setFile(picked);
    // The filename stem is the natural session id; editable for collisions.
    if (!sessionId.trim()) setSessionId(picked.name.replace(/\.jsonl(\.gz)?$/i, ""));
  }

  async function upload() {
    if (!file) return;
    setBusy(true);
    setError("");
    try {
      const result = await uploadTranscript(
        file,
        sessionId.trim(),
        agentName.trim(),
        undefined,
        externalUserId,
      );
      if (result.skipped) {
        setError(`Nothing imported: ${result.reason}.`);
        return;
      }
      setFile(null);
      setSessionId("");
      setAgentName("");
      setFormOpen(false);
      onAdded();
    } catch (cause) {
      if (!(cause instanceof Error)) throw cause;
      setError(cause.message);
    } finally {
      setBusy(false);
    }
  }

  if (!formOpen) {
    return (
      <div className="flex justify-end">
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <button
              type="button"
              aria-label="Session actions"
              className="cursor-pointer rounded p-1.5 text-muted-foreground hover:bg-raised hover:text-foreground"
            >
              <MoreHorizontal className="h-4 w-4" />
            </button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            <DropdownMenuItem onClick={() => setFormOpen(true)}>
              Upload a session transcript
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    );
  }

  return (
    <div className="mt-4 rounded border border-border bg-surface px-5 py-4">
      <div className="flex items-start justify-between">
        <div className="text-[14.5px] text-foreground">Upload a session transcript</div>
        <button
          type="button"
          aria-label="Close"
          onClick={() => setFormOpen(false)}
          className="cursor-pointer rounded p-1 text-muted-foreground hover:bg-raised hover:text-foreground"
        >
          <X className="h-4 w-4" />
        </button>
      </div>
      <p className="mt-1 text-[13px] leading-6 text-muted-foreground">
        A <span className="font-mono text-[12px]">.jsonl</span>{" "}
        transcript lands in this user&apos;s sessions exactly as if their agent had streamed it.
      </p>
      <div className="mt-3 space-y-2">
        <input
          type="file"
          accept=".jsonl,.gz"
          data-testid="user-transcript-input"
          onChange={(event) => {
            const picked = event.target.files?.[0];
            if (picked) pickFile(picked);
          }}
          disabled={busy}
          className="w-full text-[12px] text-foreground file:mr-3 file:cursor-pointer file:rounded-md file:border file:border-border file:bg-background file:px-3 file:py-1.5 file:text-[12px] file:font-medium file:text-foreground"
        />
        <div className="flex items-center gap-2">
          <input
            value={sessionId}
            onChange={(event) => setSessionId(event.target.value)}
            placeholder="Session id"
            className="w-full rounded-md border border-border bg-background px-2 py-1.5 font-mono text-[12px] text-foreground placeholder:font-sans placeholder:text-muted-foreground"
            disabled={busy}
          />
          <input
            value={agentName}
            onChange={(event) => setAgentName(event.target.value)}
            placeholder="Agent name (e.g. support-bot)"
            className="w-full rounded-md border border-border bg-background px-2 py-1.5 text-[12px] text-foreground placeholder:text-muted-foreground"
            disabled={busy}
          />
          <button
            type="button"
            onClick={() => void upload()}
            disabled={busy || !file || sessionId.trim() === "" || agentName.trim() === ""}
            className="shrink-0 cursor-pointer rounded-md border border-border px-3 py-1.5 text-[12px] font-medium text-foreground hover:bg-raised disabled:opacity-60"
          >
            {busy ? "Uploading..." : "Upload"}
          </button>
        </div>
      </div>
      {error && <div className="mt-2 text-[12.5px] text-error">{error}</div>}
    </div>
  );
}
