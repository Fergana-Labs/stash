"use client";

import { Check, MoreHorizontal, Pencil, Trash2, X } from "lucide-react";
import { FormEvent, useState } from "react";

import { useConfirm } from "@/components/ConfirmDialog";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { deleteUser, updateUser } from "@/lib/api";
import type { EndUser } from "@/lib/types";

export default function UserActions({ user, onChanged }: { user: EndUser; onChanged: () => void }) {
  const confirm = useConfirm();
  const [renaming, setRenaming] = useState(false);
  const [name, setName] = useState(user.name);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function rename(event: FormEvent) {
    event.preventDefault();
    const nextName = name.trim();
    if (!nextName) return;
    setBusy(true);
    setError("");
    try {
      await updateUser(user.id, { name: nextName });
      setRenaming(false);
      onChanged();
    } catch (cause) {
      if (!(cause instanceof Error)) throw cause;
      setError(cause.message);
    } finally {
      setBusy(false);
    }
  }

  async function remove() {
    const approved = await confirm({
      title: `Delete ${user.name}?`,
      body: "Their private wiki and connected sources will be deleted. Historical sessions and uploaded files stay in the workspace without a user assigned.",
      confirmLabel: "Delete user",
    });
    if (!approved) return;
    setBusy(true);
    setError("");
    try {
      await deleteUser(user.id);
      onChanged();
    } catch (cause) {
      if (!(cause instanceof Error)) throw cause;
      setError(cause.message);
    } finally {
      setBusy(false);
    }
  }

  if (renaming) {
    return (
      <form onSubmit={(event) => void rename(event)} className="flex items-center gap-1.5">
        <input
          aria-label={`Name for ${user.name}`}
          value={name}
          onChange={(event) => setName(event.target.value)}
          disabled={busy}
          autoFocus
          className="w-44 rounded-md border border-border bg-background px-2 py-1 text-[12px] text-foreground"
        />
        <button
          type="submit"
          aria-label="Save name"
          disabled={busy || name.trim() === ""}
          className="cursor-pointer rounded p-1.5 text-muted-foreground hover:bg-raised hover:text-foreground disabled:opacity-50"
        >
          <Check className="h-3.5 w-3.5" />
        </button>
        <button
          type="button"
          aria-label="Cancel rename"
          onClick={() => {
            setName(user.name);
            setError("");
            setRenaming(false);
          }}
          className="cursor-pointer rounded p-1.5 text-muted-foreground hover:bg-raised hover:text-foreground"
        >
          <X className="h-3.5 w-3.5" />
        </button>
        {error && <span className="max-w-40 truncate text-[12px] text-error">{error}</span>}
      </form>
    );
  }

  return (
    <div className="flex items-center gap-1.5">
      {error && <span className="max-w-40 truncate text-[12px] text-error">{error}</span>}
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <button
            type="button"
            aria-label={`Actions for ${user.name}`}
            disabled={busy}
            className="cursor-pointer rounded p-1.5 text-muted-foreground hover:bg-raised hover:text-foreground disabled:opacity-50"
          >
            <MoreHorizontal className="h-4 w-4" />
          </button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end">
          <DropdownMenuItem onClick={() => setRenaming(true)}>
            <Pencil /> Rename
          </DropdownMenuItem>
          <DropdownMenuItem variant="destructive" onClick={() => void remove()}>
            <Trash2 /> Delete
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
    </div>
  );
}
