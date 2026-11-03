"use client";

import { useEffect, useRef, useState } from "react";
import { Check, ChevronDown, Copy, Rocket } from "lucide-react";
import { Button } from "@/components/ui/button";
import { errorMessage } from "@/components/reward-models/rm-text";
import { imPromote, type ModelDetail } from "@/lib/intuition-api";
import { cn } from "@/lib/utils";

export const origin = () => (typeof window === "undefined" ? "https://joinstash.ai" : window.location.origin);

export function snippets(id: string, name: string) {
  const base = origin();
  return {
    rest: `curl -s ${base}/api/v1/intuitions/${id}/predict \\
  -H "Authorization: Bearer $STASH_API_KEY" \\
  -H "Content-Type: application/json" \\
  -d '{"item": {"request": "what the agent was asked", "trace": ["the steps it took"], "output": "what it produced"}, "ref": "optional-your-id"}'`,
    mcp: JSON.stringify({ mcpServers: { "stash-intuitions": { type: "http", url: `${base}/mcp/intuitions`, headers: { Authorization: "Bearer <STASH_API_KEY>" } } } }, null, 2),
    agent: `Use my Stash intuition "${name}" (id ${id}) to check work before acting on it.
Connect the MCP server at ${base}/mcp/intuitions with header "Authorization: Bearer $STASH_API_KEY"
(or call POST ${base}/api/v1/intuitions/${id}/predict with {"item": ...}).
Call classify(intuition_id="${id}", item={"request": <what you were asked>, "trace": <the steps you took>, "output": <what you produced>}) and act on the label:
if it flags a problem or confidence is below 0.7, revise and check again, or ask me.
Pass a ref so I can review decisions in the Inbox; never relabel examples yourself.`,
  };
}

export function CopyBlock({ text, label }: { text: string; label: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <div className="relative">
      <pre className="m-0 max-h-56 overflow-auto rounded-md border border-border bg-surface/60 p-2.5 pr-16 font-mono text-[11px] leading-relaxed whitespace-pre-wrap">{text}</pre>
      <Button size="xs" variant="outline" className="absolute top-1.5 right-1.5" aria-label={`Copy ${label}`} onClick={() => void navigator.clipboard?.writeText(text).then(() => { setCopied(true); setTimeout(() => setCopied(false), 1500); })}>
        {copied ? <Check /> : <Copy />}{copied ? "Copied" : "Copy"}
      </Button>
    </div>
  );
}

/** Ship the trained draft, and copy what it takes to call it: REST, MCP, or a prompt for a coding agent. */
export default function UseIt({ detail, onShipped }: { detail: ModelDetail; onShipped: () => void }) {
  const [open, setOpen] = useState(false);
  const [tab, setTab] = useState<"api" | "mcp" | "agent">("agent");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const close = (e: MouseEvent) => { if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false); };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, [open]);

  const draft = detail.draft;
  const shippable = !!draft && !draft.head_stale && !!draft.head;
  const gatePassed = !!draft?.gate?.passed;
  const s = snippets(detail.model.id, detail.model.name);

  async function ship() {
    setBusy(true); setError("");
    try { await imPromote(detail.model.id, !gatePassed); onShipped(); } catch (e) { setError(errorMessage(e)); } finally { setBusy(false); }
  }

  return (
    <div ref={ref} className="relative">
      <Button size="sm" onClick={() => setOpen((v) => !v)} aria-expanded={open}><Rocket />Use it<ChevronDown /></Button>
      {open && (
        <div className="absolute right-0 z-30 mt-1.5 w-[min(30rem,calc(100vw-2rem))] space-y-3 rounded-lg border border-border bg-background p-3.5 shadow-lg">
          <div className="flex items-center gap-2">
            <div className="min-w-0 flex-1 text-[12.5px]">
              {detail.active ? <>Live: <b>v{detail.active.number}</b>{shippable && <span className="text-muted-foreground">, a newer trained version is ready</span>}</> : shippable ? "Trained, not live yet." : "Train it first, then ship."}
            </div>
            {shippable && <Button size="sm" variant={gatePassed ? "default" : "outline"} disabled={busy} onClick={() => void ship()} title={gatePassed ? "Make the trained version live" : "The gate has blocking checks; ship anyway"}>{busy ? "Shipping…" : gatePassed ? `Ship v${draft?.number}` : "Ship anyway"}</Button>}
          </div>
          {error && <p role="alert" className="m-0 text-[11.5px] text-destructive">{error}</p>}
          <div role="tablist" className="flex gap-1 border-b border-border text-[12px]">
            {([["agent", "Coding agent"], ["mcp", "MCP"], ["api", "API"]] as const).map(([id, label]) => (
              <button key={id} role="tab" type="button" aria-selected={tab === id} onClick={() => setTab(id)} className={cn("-mb-px border-b-2 px-2.5 py-1.5", tab === id ? "border-foreground font-medium" : "border-transparent text-muted-foreground")}>{label}</button>
            ))}
          </div>
          {tab === "agent" && <><p className="m-0 text-[12px] text-muted-foreground">Paste into Claude Code, Cursor or any agent, so it checks its work with this intuition.</p><CopyBlock label="agent prompt" text={s.agent} /></>}
          {tab === "mcp" && <><p className="m-0 text-[12px] text-muted-foreground">Add to your MCP config. Tools: classify, inbox, review_prediction, train, and the full build flow.</p><CopyBlock label="MCP config" text={s.mcp} /></>}
          {tab === "api" && <><p className="m-0 text-[12px] text-muted-foreground">Calls the live version. Responses include label, probabilities, confidence and a prediction_id for feedback.</p><CopyBlock label="curl" text={s.rest} /></>}
          <p className="m-0 text-[11px] text-muted-foreground">Needs a Stash API key (Settings → API keys). Every call shows up in the Inbox for review.</p>
        </div>
      )}
    </div>
  );
}
