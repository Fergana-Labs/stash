"use client";

import { useState } from "react";
import { Pencil } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { rmRenameTraceSource } from "@/lib/api";
import { Field } from "./rm-ui";
import { errorMessage } from "./rm-text";

export default function TraceSourceNameDialog({ sourceId, name, onRenamed }: {
  sourceId: string; name: string; onRenamed: (name: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const [value, setValue] = useState(name);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  async function save() {
    setSaving(true); setError(null);
    try {
      const result = await rmRenameTraceSource(sourceId, value.trim());
      onRenamed(result.source_name);
      setOpen(false);
    } catch (err) { setError(errorMessage(err)); }
    finally { setSaving(false); }
  }
  return <Dialog open={open} onOpenChange={(next) => { if (!saving) { setOpen(next); setValue(name); setError(null); } }}>
    <DialogTrigger asChild><Button variant="ghost" size="icon-xs" aria-label="Rename source"><Pencil /></Button></DialogTrigger>
    <DialogContent className="sm:max-w-md">
      <DialogHeader>
        <DialogTitle>Rename source</DialogTitle>
        <DialogDescription>This name applies to existing and future traces with this source ID.</DialogDescription>
      </DialogHeader>
      <div className="text-xs text-muted-foreground">Source ID <code className="ml-2 break-all text-foreground">{sourceId}</code></div>
      <Field label="Source name"><Input value={value} onChange={(e) => setValue(e.target.value)} maxLength={120} disabled={saving} placeholder="e.g. Henry’s Codex" /></Field>
      {error && <p role="alert" className="m-0 text-xs text-red-600">{error}</p>}
      <DialogFooter>
        <Button variant="outline" onClick={() => setOpen(false)} disabled={saving}>Cancel</Button>
        <Button onClick={() => void save()} disabled={saving || !value.trim()}>{saving ? "Saving…" : "Save"}</Button>
      </DialogFooter>
    </DialogContent>
  </Dialog>;
}
