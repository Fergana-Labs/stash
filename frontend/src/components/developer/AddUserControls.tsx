"use client";

import { useState } from "react";

import { createUser } from "@/lib/api";

// Manual user creation, for setting a user up before their product's backend
// has uploaded a session — the first upload with this user_id lands on them.
export default function AddUserControls({ onAdded }: { onAdded: () => void }) {
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
      onAdded();
    } catch (cause) {
      if (!(cause instanceof Error)) throw cause;
      setError(cause.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mb-4 rounded border border-border bg-surface px-5 py-4">
      <div className="text-[14.5px] text-foreground">Add a user</div>
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
