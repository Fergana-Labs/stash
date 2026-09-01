"use client";

import { MoreHorizontal, X } from "lucide-react";
import { useState } from "react";

import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { createUser } from "@/lib/api";

// Manual user creation, for setting a user up before their product's backend
// has uploaded a session — the first upload with this user_id lands on them.
// Tucked behind a "…" menu: the common path stays upload-driven.
export default function AddUserControls({ onAdded }: { onAdded: () => void }) {
  const [formOpen, setFormOpen] = useState(false);
  const [userId, setUserId] = useState("");
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function add() {
    setBusy(true);
    setError("");
    try {
      await createUser(userId.trim(), name.trim() || undefined);
      setUserId("");
      setName("");
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
      <div className="mb-2 flex justify-end">
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <button
              type="button"
              aria-label="User actions"
              className="cursor-pointer rounded p-1.5 text-muted-foreground hover:bg-raised hover:text-foreground"
            >
              <MoreHorizontal className="h-4 w-4" />
            </button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            <DropdownMenuItem onClick={() => setFormOpen(true)}>Add a user</DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    );
  }

  return (
    <div className="mb-4 rounded border border-border bg-surface px-5 py-4">
      <div className="flex items-start justify-between">
        <div className="text-[14.5px] text-foreground">Add a user</div>
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
        Set a user up before their first session — assign sources or seed their wiki. Uploads
        carrying this <span className="font-mono text-[12px]">user_id</span> land on them.
      </p>
      <div className="mt-3 flex items-center gap-2">
        <input
          value={userId}
          onChange={(event) => setUserId(event.target.value)}
          placeholder="user_id (e.g. org_acme)"
          className="w-full rounded-md border border-border bg-background px-2 py-1.5 font-mono text-[12px] text-foreground placeholder:font-sans placeholder:text-muted-foreground"
          disabled={busy}
        />
        <input
          value={name}
          onChange={(event) => setName(event.target.value)}
          placeholder="Name (optional — defaults to the user_id)"
          className="w-full rounded-md border border-border bg-background px-2 py-1.5 text-[12px] text-foreground placeholder:text-muted-foreground"
          disabled={busy}
        />
        <button
          type="button"
          onClick={() => void add()}
          disabled={busy || userId.trim() === ""}
          className="shrink-0 cursor-pointer rounded-md border border-border px-3 py-1.5 text-[12px] font-medium text-foreground hover:bg-raised disabled:opacity-60"
        >
          {busy ? "Adding..." : "Add user"}
        </button>
      </div>
      {error && <div className="mt-2 text-[12.5px] text-error">{error}</div>}
    </div>
  );
}
