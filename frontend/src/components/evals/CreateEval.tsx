"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { inputClass } from "@/components/workbench/workbench-ui";
import { errorMessage } from "@/components/reward-models/rm-text";
import { imCreate } from "@/lib/intuition-api";

export default function CreateEval({ onCreated }: { onCreated: (id: string) => void }) {
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  return <form aria-label="Create eval" className="max-w-2xl space-y-4 py-4" onSubmit={async (event) => {
    event.preventDefault(); if (busy || !name.trim()) return;
    setBusy(true); setError("");
    try { const result = await imCreate({ name: name.trim(), description, output_type: "choice", labels: [{ id: "good", description: "Meets the user's expectations" }, { id: "bad", description: "Needs correction" }] }); onCreated(result.model.id); }
    catch (e) { setError(errorMessage(e)); } finally { setBusy(false); }
  }}>
    <h2 className="text-base font-semibold">What should this eval judge?</h2>
    <label className="block space-y-1 text-xs"><span>Name</span><input className={inputClass} value={name} maxLength={160} required disabled={busy} onChange={(e) => setName(e.target.value)} placeholder="Slide quality, support replies, safe actions…" /></label>
    <label className="block space-y-1 text-xs"><span>What does good look like?</span><textarea className={inputClass} rows={5} value={description} maxLength={6000} disabled={busy} onChange={(e) => setDescription(e.target.value)} placeholder="Describe what matters, paste user interview notes, or explain what to avoid." /></label>
    <p className="text-xs text-muted-foreground">Next, add good and bad examples. We’ll calibrate a decision model and check it on an example held aside.</p>
    {error && <p role="alert" className="text-xs text-destructive">{error}</p>}
    <Button size="sm" disabled={busy || !name.trim()}>{busy ? "Creating…" : "Continue to examples"}</Button>
  </form>;
}
