"use client";

import { useState } from "react";
import { ChevronRight, RotateCcw, Rocket } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { errorMessage, relativeTime } from "@/components/reward-models/rm-text";
import { cn } from "@/lib/utils";
import { imDiscardDraft, imPromote, imRestore, imVersion, type Version, type VersionSummary } from "@/lib/intuition-api";
import { num, pct } from "./im-helpers";
import { Callout, ConfirmDialog, Panel, Spinner, useIntuition } from "./im-ui";
import GatePanel from "./GatePanel";
import { QuestionPreview } from "./RubricEditor";
import { HeadTable } from "./WeightsGrid";

const STATUS_TAG: Record<Version["status"], string> = { active: "tag-success", draft: "tag-warning", retired: "tag-muted" };

export default function VersionsTab() {
  const { id, detail, apply, goTo } = useIntuition();
  const { draft, active } = detail;
  const [confirm, setConfirm] = useState<null | "force" | "discard" | { restore: VersionSummary }>(null);
  const [promoting, setPromoting] = useState(false);

  async function promote(force: boolean) {
    setPromoting(true);
    try {
      const next = await imPromote(id, force);
      apply(next);
      toast.success(`v${next.active?.number} is now active`, { description: "Agents and the API are served by it from now on." });
    } catch (e) {
      toast.error(errorMessage(e));
      return false;
    } finally {
      setPromoting(false);
    }
  }

  const gate = draft?.gate ?? null;
  const draftBlocked = !draft ? null : draft.head_stale ? "stale" : !gate ? "unevaluated" : null;

  return (
    <div className="space-y-4">
      {draft ? (
        <Panel
          className="border-yellow-500/40"
          title={
            <span className="flex items-center gap-2">
              Draft v{draft.number}
              <span className="tag tag-warning">unpromoted</span>
            </span>
          }
          description={`Created ${relativeTime(draft.created_at)}${active ? ` from v${active.number}` : ""}. Every edit lands here; the active version keeps serving until you promote.`}
          actions={
            <>
              <Button variant="ghost" size="sm" onClick={() => setConfirm("discard")} disabled={!active} title={active ? undefined : "The first version can’t be discarded; delete the model instead"}>
                Discard draft
              </Button>
              {!draftBlocked && gate && !gate.passed && (
                <Button variant="outline" size="sm" onClick={() => setConfirm("force")} disabled={promoting}>
                  Promote anyway
                </Button>
              )}
              <Button size="sm" onClick={() => void promote(false)} disabled={promoting || draftBlocked !== null || !gate?.passed}>
                {promoting ? <Spinner /> : <Rocket />}
                Promote
              </Button>
            </>
          }
        >
          {draftBlocked === "stale" ? (
            <Callout tone="info" action={<Button size="sm" variant="outline" onClick={() => goTo("train")}>Go to Train</Button>}>
              Rubric or labels changed — grade and fit the draft before it can be promoted.
            </Callout>
          ) : draftBlocked === "unevaluated" ? (
            <Callout tone="info" action={<Button size="sm" variant="outline" onClick={() => goTo("train")}>Go to Train</Button>}>
              Evaluate the draft (fit or save weights) to see whether it beats the active version.
            </Callout>
          ) : gate ? (
            <GatePanel gate={gate} metrics={draft.metrics} />
          ) : null}
        </Panel>
      ) : (
        <Callout tone="info" action={<Button size="sm" variant="outline" onClick={() => goTo("rubric")}>Edit rubric</Button>}>
          No draft. Editing the rubric, seeds or weights starts draft v{Math.max(0, ...detail.versions.map((v) => v.number)) + 1} from the active version.
        </Callout>
      )}

      <ul className="m-0 list-none space-y-2 p-0">
        {detail.versions
          .filter((v) => v.status !== "draft")
          .map((v) => (
            <VersionRow key={v.id} modelId={id} summary={v} onRestore={() => setConfirm({ restore: v })} />
          ))}
      </ul>
      {detail.versions.every((v) => v.status === "draft") && <p className="m-0 text-[12.5px] text-muted-foreground">Nothing promoted yet. Promote the draft to start serving it.</p>}

      <ConfirmDialog
        open={confirm === "force"}
        onOpenChange={(o) => !o && setConfirm(null)}
        title={`Promote v${draft?.number} anyway?`}
        description={
          <>
            The draft fails {gate?.checks.filter((c) => !c.passed).length ?? 0} gate check(s). It will start serving agents immediately and be marked as force-promoted. You can restore v{active?.number} later.
          </>
        }
        confirmLabel="Promote anyway"
        destructive
        onConfirm={() => promote(true)}
      />
      <ConfirmDialog
        open={confirm === "discard"}
        onOpenChange={(o) => !o && setConfirm(null)}
        title={`Discard draft v${draft?.number}?`}
        description="Its rubric, seed and weight edits are deleted. Examples and cached judge answers are kept."
        confirmLabel="Discard draft"
        destructive
        onConfirm={async () => {
          try {
            apply(await imDiscardDraft(id));
            toast("Draft discarded");
          } catch (e) {
            toast.error(errorMessage(e));
            return false;
          }
        }}
      />
      <ConfirmDialog
        open={typeof confirm === "object" && confirm !== null}
        onOpenChange={(o) => !o && setConfirm(null)}
        title={typeof confirm === "object" && confirm ? `Restore v${confirm.restore.number}?` : "Restore"}
        description={`It becomes the active version and serves agents immediately${active ? `; v${active.number} is retired` : ""}. Your draft is kept.`}
        confirmLabel="Restore"
        onConfirm={async () => {
          if (typeof confirm !== "object" || !confirm) return;
          try {
            apply(await imRestore(id, confirm.restore.id));
            toast.success(`v${confirm.restore.number} restored`);
          } catch (e) {
            toast.error(errorMessage(e));
            return false;
          }
        }}
      />
    </div>
  );
}

function VersionRow({ modelId, summary, onRestore }: { modelId: string; summary: VersionSummary; onRestore: () => void }) {
  const [open, setOpen] = useState(false);
  const [full, setFull] = useState<Version | null>(null);
  const [error, setError] = useState<string | null>(null);
  const held = summary.metrics?.eval;

  async function toggle() {
    const next = !open;
    setOpen(next);
    if (next && !full) {
      try {
        setFull(await imVersion(modelId, summary.id));
        setError(null);
      } catch (e) {
        setError(errorMessage(e));
      }
    }
  }

  return (
    <li className="rounded-lg border border-border bg-background">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 px-4 py-2.5">
        <button type="button" onClick={() => void toggle()} aria-expanded={open} className="inline-flex items-center gap-1.5 text-[13.5px] font-medium text-foreground hover:text-brand-600">
          <ChevronRight className={cn("h-3.5 w-3.5 text-muted-foreground transition-transform", open && "rotate-90")} />v{summary.number}
        </button>
        <span className={cn("tag", STATUS_TAG[summary.status])}>{summary.status}</span>
        {summary.gate?.forced && (
          <span className="tag bg-red-500/10 text-red-600" title="Promoted despite failing the gate">
            forced
          </span>
        )}
        <span className="font-mono text-[11.5px] text-muted-foreground">
          {summary.provider} · {summary.provider_model}
        </span>
        <span className="text-[12px] text-muted-foreground">
          acc <span className="font-mono text-foreground">{pct(held?.accuracy, 1)}</span> · log loss <span className="font-mono text-foreground">{num(held?.log_loss)}</span>
          {held && <span className="font-mono"> · n={held.n}</span>}
        </span>
        <span className="flex-1" />
        <span className="text-[11.5px] text-muted-foreground">{summary.promoted_at ? `promoted ${relativeTime(summary.promoted_at)}` : `created ${relativeTime(summary.created_at)}`}</span>
        {summary.status === "retired" && (
          <Button size="xs" variant="outline" onClick={onRestore} disabled={!summary.has_head}>
            <RotateCcw /> Restore
          </Button>
        )}
      </div>
      {open && (
        <div className="space-y-3 border-t border-border-subtle px-4 py-3">
          {error ? (
            <Callout tone="danger">{error}</Callout>
          ) : !full ? (
            <Spinner />
          ) : (
            <>
              <div>
                <h3 className="m-0 mb-1 text-[11px] font-medium tracking-wide text-muted-foreground uppercase">Description</h3>
                <p className="m-0 text-[12.5px] leading-relaxed whitespace-pre-wrap text-foreground">{full.description || "—"}</p>
              </div>
              {full.labels.length > 0 && (
                <div className="flex flex-wrap gap-1.5">
                  {full.labels.map((l) => (
                    <span key={l.id} className="tag tag-muted normal-case" title={l.description}>
                      {l.id}
                    </span>
                  ))}
                </div>
              )}
              <div>
                <h3 className="m-0 mb-1.5 text-[11px] font-medium tracking-wide text-muted-foreground uppercase">Rubric · {full.rubric.length}</h3>
                <div className="grid gap-2 md:grid-cols-2">
                  {full.rubric.map((q) => (
                    <QuestionPreview key={q.id} q={q} className="rounded-md border border-border-subtle px-3 py-2" />
                  ))}
                </div>
              </div>
              {full.head && !full.head_stale && (
                <div>
                  <h3 className="m-0 mb-1.5 text-[11px] font-medium tracking-wide text-muted-foreground uppercase">Weights{full.head.edited ? " · hand-edited" : ""}</h3>
                  <HeadTable head={full.head} rubric={full.rubric} />
                </div>
              )}
              <p className="m-0 font-mono text-[11px] text-muted-foreground">{full.seed_example_ids.length} seed examples</p>
            </>
          )}
        </div>
      )}
    </li>
  );
}
