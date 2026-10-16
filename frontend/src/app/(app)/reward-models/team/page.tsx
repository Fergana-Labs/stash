"use client";

import { useMemo, useState } from "react";
import { Check, Search, Share2 } from "lucide-react";
import { toast } from "sonner";
import { useBreadcrumbs } from "@/components/BreadcrumbContext";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { RmPage } from "@/components/reward-models/rm-ui";
import { cn } from "@/lib/utils";
import { ME, MY_AGENTS, TEAM_MODELS, TEAMMATES, type TeamRewardModel } from "./team-models-data";

const FILTERS = [
  { value: "team", label: "From teammates" },
  { value: "mine", label: "Yours" },
  { value: "all", label: "All" },
] as const;
type Filter = (typeof FILTERS)[number]["value"];

const SORTS = [
  { value: "agreement", label: "Agreement" },
  { value: "updated", label: "Last changed" },
  { value: "agents", label: "Most used" },
] as const;
type Sort = (typeof SORTS)[number]["value"];

const actionClass = "h-[26px] gap-1.5 rounded-[4px] border-border bg-background px-2 text-[11px] font-normal shadow-none [&_svg]:size-3";

function relativeTime(iso: string): string {
  const days = Math.floor((Date.now() - new Date(iso).getTime()) / 86_400_000);
  if (days <= 0) return "today";
  if (days === 1) return "yesterday";
  if (days < 30) return `${days} days ago`;
  return new Date(iso).toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

function Owner({ id }: { id: string }) {
  const person = TEAMMATES[id];
  return (
    <span className="flex h-5 items-center gap-2">
      <span aria-hidden="true" className="flex size-5 shrink-0 items-center justify-center rounded-full bg-raised text-[9px] leading-none font-semibold text-dim">{person.initials}</span>
      <span className="truncate">{id === ME ? "You" : person.name}</span>
    </span>
  );
}

function Agreement({ model }: { model: TeamRewardModel }) {
  const pct = Math.round(model.agreement * 100);
  return (
    <div className="flex h-5 items-center justify-end gap-2" title={`Agreed with people on ${Math.round(model.agreement * model.heldOut)} of ${model.heldOut} held-out examples`}>
      <span className="hidden h-1 w-14 overflow-hidden rounded-full bg-raised sm:block" aria-hidden="true">
        <span className={cn("block h-full rounded-full", pct >= 85 ? "bg-foreground/70" : "bg-foreground/35")} style={{ width: `${pct}%` }} />
      </span>
      <span className="w-9 text-right font-medium tabular-nums">{pct}%</span>
      <span className="w-14 text-right text-muted-foreground tabular-nums">of {model.heldOut}</span>
    </div>
  );
}

export default function TeamRewardModelsPage() {
  useBreadcrumbs([{ label: "Team reward models" }], "reward-models");
  const [models, setModels] = useState(TEAM_MODELS);
  const [filter, setFilter] = useState<Filter>("team");
  const [sort, setSort] = useState<Sort>("agreement");
  const [query, setQuery] = useState("");
  const [selectedId, setSelectedId] = useState<string>(TEAM_MODELS.find((m) => m.ownerId !== ME)!.id);
  const [adopting, setAdopting] = useState<TeamRewardModel | null>(null);
  const [sharing, setSharing] = useState(false);

  const visible = useMemo(() => {
    const q = query.trim().toLowerCase();
    return models
      .filter((m) => filter === "all" || (filter === "mine" ? m.ownerId === ME : m.ownerId !== ME))
      .filter((m) => !q || `${m.name} ${m.description} ${TEAMMATES[m.ownerId].name} ${m.agents.join(" ")}`.toLowerCase().includes(q))
      .sort((a, b) =>
        sort === "agreement" ? b.agreement - a.agreement
          : sort === "agents" ? b.agents.length - a.agents.length
            : b.updatedAt.localeCompare(a.updatedAt));
  }, [models, filter, sort, query]);

  const selected = visible.find((m) => m.id === selectedId) ?? visible[0] ?? null;
  const unshared = models.filter((m) => m.ownerId === ME && !m.shared);

  const adopt = (model: TeamRewardModel, agents: string[]) => {
    setModels((all) => all.map((m) => (m.id === model.id ? { ...m, agents: [...m.agents.filter((a) => !MY_AGENTS.includes(a)), ...agents] } : m)));
    setAdopting(null);
    toast.success(agents.length ? `${model.name} now scores ${agents.join(", ")}` : `${model.name} no longer scores your agents`);
  };

  const share = (ids: string[]) => {
    setModels((all) => all.map((m) => (ids.includes(m.id) ? { ...m, shared: true } : m)));
    setSharing(false);
    toast.success(ids.length === 1 ? "Shared with your team" : `Shared ${ids.length} reward models with your team`);
  };

  return (
    <RmPage
      wide
      title="Team reward models"
      description="Graders your teammates have built"
      actions={<Button size="xs" variant="outline" className={actionClass} onClick={() => setSharing(true)}><Share2 />Share yours</Button>}
    >
      <div className="mb-3 flex flex-wrap items-center gap-3">
        <div role="tablist" aria-label="Whose reward models" className="flex rounded-[5px] border border-border p-0.5">
          {FILTERS.map((f) => (
            <button
              key={f.value}
              role="tab"
              aria-selected={filter === f.value}
              onClick={() => setFilter(f.value)}
              className={cn("rounded-[3px] px-2.5 py-1 text-[12px] transition-colors", filter === f.value ? "bg-raised font-medium text-foreground" : "text-muted-foreground hover:text-foreground")}
            >
              {f.label}
            </button>
          ))}
        </div>
        <label className="flex h-[30px] w-64 items-center gap-2 rounded-[5px] border border-border px-2">
          <Search className="size-3 text-muted-foreground" aria-hidden="true" />
          <input aria-label="Search reward models" placeholder="Search by name, owner, or agent…" value={query} onChange={(e) => setQuery(e.target.value)} className="min-w-0 flex-1 bg-transparent text-xs outline-none placeholder:text-muted-foreground" />
        </label>
        <label className="ml-auto flex items-center gap-1.5 text-xs text-muted-foreground">
          Sort by
          <select value={sort} onChange={(e) => setSort(e.target.value as Sort)} className="h-[30px] rounded-[5px] border border-border bg-background px-1.5 text-xs text-foreground">
            {SORTS.map((s) => <option key={s.value} value={s.value}>{s.label}</option>)}
          </select>
        </label>
      </div>

      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_320px]">
        <div className="overflow-x-auto rounded border border-border">
          <table aria-label="Team reward models" className="w-full min-w-[680px] text-left text-xs">
            <thead className="border-b border-border bg-surface/60 text-muted-foreground">
              <tr className="h-8 [&>th]:px-3 [&>th]:font-medium [&>th]:whitespace-nowrap">
                <th>Reward model</th>
                <th>Owner</th>
                <th className="text-right" title="How often the model's verdict matched a person's on held-out examples">Agreement</th>
                <th className="text-right">Agents</th>
                <th className="text-right">Last changed</th>
              </tr>
            </thead>
            <tbody>
              {visible.map((m) => {
                const active = selected?.id === m.id;
                return (
                  <tr
                    key={m.id}
                    aria-selected={active}
                    onClick={() => setSelectedId(m.id)}
                    className={cn("h-9 cursor-pointer border-b border-border leading-5 last:border-b-0 [&>td]:px-3 [&>td]:align-middle", active ? "bg-surface" : "hover:bg-surface/60")}
                  >
                    <td className="whitespace-nowrap">
                      <button className="text-left font-medium text-foreground" onClick={() => setSelectedId(m.id)}>{m.name}</button>
                      {m.ownerId === ME && !m.shared && <span className="ml-2 text-[11px] text-muted-foreground">Only you</span>}
                    </td>
                    <td className="w-32 whitespace-nowrap"><Owner id={m.ownerId} /></td>
                    <td className="w-40"><Agreement model={m} /></td>
                    <td className="w-16 text-right tabular-nums">{m.agents.length || <span className="text-muted-foreground">—</span>}</td>
                    <td className="w-24 whitespace-nowrap text-right text-muted-foreground">{relativeTime(m.updatedAt)}</td>
                  </tr>
                );
              })}
              {!visible.length && (
                <tr><td colSpan={5} className="px-3 py-10 text-center text-muted-foreground">
                  {query ? "No reward models match that search." : filter === "mine" ? "You haven't built a reward model yet." : "No teammate has shared a reward model yet."}
                </td></tr>
              )}
            </tbody>
          </table>
        </div>

        {selected && <ModelDetail model={selected} onAdopt={() => setAdopting(selected)} onShare={() => share([selected.id])} />}
      </div>

      {adopting && <AdoptDialog model={adopting} onClose={() => setAdopting(null)} onSave={(agents) => adopt(adopting, agents)} />}
      <ShareDialog open={sharing} models={unshared} onClose={() => setSharing(false)} onShare={share} />
    </RmPage>
  );
}

function ModelDetail({ model, onAdopt, onShare }: { model: TeamRewardModel; onAdopt: () => void; onShare: () => void }) {
  const mine = model.ownerId === ME;
  const myUsing = model.agents.filter((a) => MY_AGENTS.includes(a));
  const others = model.agents.filter((a) => !MY_AGENTS.includes(a));
  const agreed = Math.round(model.agreement * model.heldOut);
  return (
    <aside aria-label={model.name} className="self-start rounded border border-border p-4 text-xs lg:sticky lg:top-0">
      <h2 className="m-0 text-[14px] font-semibold text-foreground">{model.name}</h2>
      <div className="mt-1.5 text-muted-foreground"><Owner id={model.ownerId} /></div>
      <p className="mt-3 leading-relaxed text-dim">{model.description}</p>

      <dl className="mt-4 grid gap-3 border-t border-border pt-4">
        <div>
          <dt className="text-muted-foreground">Agreement with people</dt>
          <dd className="mt-0.5 text-[18px] font-semibold tabular-nums text-foreground">{Math.round(model.agreement * 100)}%</dd>
          <dd className="text-muted-foreground">{agreed} of {model.heldOut} held-out examples</dd>
        </div>
        <div>
          <dt className="text-muted-foreground">Scores {model.agents.length === 1 ? "1 agent" : `${model.agents.length} agents`}</dt>
          <dd className="mt-1 flex flex-wrap gap-1">
            {model.agents.length === 0 && <span className="text-muted-foreground">Not used by any agent yet</span>}
            {myUsing.map((a) => <span key={a} className="tag tag-human" title="Your agent">{a}</span>)}
            {others.map((a) => <span key={a} className="tag tag-muted">{a}</span>)}
          </dd>
        </div>
        <div>
          <dt className="text-muted-foreground">Last changed {relativeTime(model.updatedAt)}</dt>
          <dd className="mt-0.5 text-dim">{model.lastChange}</dd>
        </div>
      </dl>

      <div className="mt-4 flex flex-wrap gap-2 border-t border-border pt-4">
        {mine && !model.shared
          ? <Button size="sm" onClick={onShare}><Share2 />Share with team</Button>
          : <Button size="sm" variant={myUsing.length ? "outline" : "default"} onClick={onAdopt}>
              {myUsing.length ? <><Check />Used by {myUsing.length === 1 ? "1 of your agents" : `${myUsing.length} of your agents`}</> : "Use for my agents"}
            </Button>}
        {mine && model.shared && <span className="self-center text-muted-foreground">Shared with your team</span>}
      </div>
    </aside>
  );
}

function AdoptDialog({ model, onClose, onSave }: { model: TeamRewardModel; onClose: () => void; onSave: (agents: string[]) => void }) {
  const [picked, setPicked] = useState(() => new Set(model.agents.filter((a) => MY_AGENTS.includes(a))));
  const toggle = (agent: string) => setPicked((s) => { const n = new Set(s); if (n.has(agent)) n.delete(agent); else n.add(agent); return n; });
  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Use {model.name}</DialogTitle>
          <DialogDescription>Pick which of your agents this reward model scores. {TEAMMATES[model.ownerId].name} keeps ownership; you get their updates automatically.</DialogDescription>
        </DialogHeader>
        <fieldset className="grid gap-1">
          <legend className="sr-only">Your agents</legend>
          {MY_AGENTS.map((agent) => (
            <label key={agent} className="flex items-center gap-2 rounded px-2 py-1.5 text-[13px] hover:bg-surface">
              <input type="checkbox" checked={picked.has(agent)} onChange={() => toggle(agent)} />
              {agent}
            </label>
          ))}
        </fieldset>
        <DialogFooter>
          <Button variant="outline" size="sm" onClick={onClose}>Cancel</Button>
          <Button size="sm" onClick={() => onSave(MY_AGENTS.filter((a) => picked.has(a)))}>Save</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function ShareDialog({ open, models, onClose, onShare }: { open: boolean; models: TeamRewardModel[]; onClose: () => void; onShare: (ids: string[]) => void }) {
  const [picked, setPicked] = useState<Set<string>>(new Set());
  const toggle = (id: string) => setPicked((s) => { const n = new Set(s); if (n.has(id)) n.delete(id); else n.add(id); return n; });
  return (
    <Dialog open={open} onOpenChange={(o) => { if (!o) { setPicked(new Set()); onClose(); } }}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Share with your team</DialogTitle>
          <DialogDescription>Teammates can see shared reward models and use them for their agents. Only you can change them.</DialogDescription>
        </DialogHeader>
        {models.length === 0
          ? <p className="text-[13px] text-muted-foreground">All of your reward models are already shared.</p>
          : <fieldset className="grid gap-1">
              <legend className="sr-only">Your unshared reward models</legend>
              {models.map((m) => (
                <label key={m.id} className="flex items-center gap-2 rounded px-2 py-1.5 text-[13px] hover:bg-surface">
                  <input type="checkbox" checked={picked.has(m.id)} onChange={() => toggle(m.id)} />
                  <span className="flex-1">{m.name}</span>
                  <span className="text-xs text-muted-foreground tabular-nums">{Math.round(m.agreement * 100)}% agreement</span>
                </label>
              ))}
            </fieldset>}
        <DialogFooter>
          <Button variant="outline" size="sm" onClick={onClose}>Cancel</Button>
          {models.length > 0 && <Button size="sm" disabled={!picked.size} onClick={() => { onShare([...picked]); setPicked(new Set()); }}>Share</Button>}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
