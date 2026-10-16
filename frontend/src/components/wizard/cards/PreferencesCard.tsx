"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { CircleAlert, Loader2, ThumbsDown, ThumbsUp } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Picture } from "@/components/taste/website-eval-ui";
import { errorMessage } from "@/components/reward-models/rm-text";
import { tasteGet, tasteReview, type TasteExample, type TasteWorkspace } from "@/lib/taste-api";
import { cn } from "@/lib/utils";
import { CardShell, useWizard } from "../wizard-ui";

const ANSWERS = [
  ["liked", "Keep this"],
  ["disliked", "Change this"],
  ["skip", "Skip"],
] as const;

function LabelPill({ label }: { label: string }) {
  const liked = label === "liked";
  const Icon = liked ? ThumbsUp : ThumbsDown;
  return (
    <span className={cn("inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-[11px] font-medium", liked ? "bg-emerald-500/10 text-emerald-700 dark:text-emerald-400" : "bg-red-500/10 text-red-700 dark:text-red-400")}>
      <Icon className="size-3" />{liked ? "Liked" : "Wanted changed"}
    </span>
  );
}

function Quote({ example }: { example: TasteExample }) {
  return <blockquote className="m-0 line-clamp-3 border-l-2 border-border pl-2 text-[12.5px] italic">{example.quote || "No comment attached to this output."}</blockquote>;
}

function Question({ example, onAnswer }: { example: TasteExample; onAnswer: (label: string) => Promise<void> }) {
  const [saving, setSaving] = useState("");
  return (
    <li className="flex gap-3 rounded border border-border p-2">
      <div className="w-36 shrink-0 overflow-hidden rounded bg-surface"><Picture kind="example" id={example.id} alt="Website from your session" className="h-24" /></div>
      <div className="flex min-w-0 flex-1 flex-col gap-2">
        <Quote example={example} />
        {example.reason && <p className="m-0 text-[11.5px] text-muted-foreground">{example.reason}</p>}
        <div className="mt-auto flex flex-wrap gap-1.5">
          {ANSWERS.map(([label, title]) => (
            <Button key={label} type="button" size="xs" variant="outline" disabled={!!saving} onClick={() => { setSaving(label); void onAnswer(label).finally(() => setSaving("")); }}>
              {saving === label && <Loader2 className="animate-spin" />}{title}
            </Button>
          ))}
        </div>
      </div>
    </li>
  );
}

/** What the wizard learned from the user's sessions, and the few examples it needs the user to call. */
export default function PreferencesCard() {
  const { send, version } = useWizard();
  const [data, setData] = useState<TasteWorkspace | null>(null);
  const [error, setError] = useState("");
  const answered = useRef(0);

  const load = useCallback(async () => {
    try { setData(await tasteGet()); setError(""); } catch (e) { setError(errorMessage(e)); }
  }, []);
  useEffect(() => { void load(); }, [load, version]);

  const learned = data?.examples.filter((e) => e.usable) ?? [];
  const open = data?.examples.filter((e) => !e.usable && e.needs_clarification) ?? [];
  const gaps = data?.labels.build_gaps ?? [];

  async function answer(example: TasteExample, label: string) {
    try {
      await tasteReview(example.id, label, example.note);
      answered.current += 1;
      const next = await tasteGet();
      setData(next);
      if (next && !next.examples.some((e) => !e.usable && e.needs_clarification)) {
        send(`Answered ${answered.current} open question${answered.current === 1 ? "" : "s"}.`, "event");
      }
    } catch (e) { setError(errorMessage(e)); }
  }

  return (
    <CardShell icon={ThumbsUp} title="What I learned from your sessions" subtitle={data ? `${data.labels.liked} liked · ${data.labels.disliked} wanted changed` : undefined}>
      {error && <p role="alert" className="m-0 mb-2 text-[11.5px] text-destructive">{error}</p>}
      {!data ? (
        <p role="status" className="m-0 text-[12px] text-muted-foreground"><Loader2 className="mr-1 inline size-3 animate-spin" />Loading…</p>
      ) : (
        <div className="space-y-4">
          {gaps.length > 0 && (
            <div className="flex gap-2 rounded border border-amber-500/30 bg-amber-500/5 px-3 py-2 text-[12px]">
              <CircleAlert className="mt-0.5 size-3.5 shrink-0 text-amber-600" />
              <div>{gaps.map((g) => <p key={g} className="m-0">{g}</p>)}</div>
            </div>
          )}
          {open.length > 0 && (
            <section>
              <h4 className="m-0 mb-2 text-[12px] font-semibold">Needs your call · {open.length}</h4>
              <ul className="m-0 flex list-none flex-col gap-2 p-0">
                {open.map((e) => <Question key={e.id} example={e} onAnswer={(label) => answer(e, label)} />)}
              </ul>
            </section>
          )}
          {learned.length > 0 && (
            <section>
              <h4 className="m-0 mb-2 text-[12px] font-semibold">From your feedback · {learned.length}</h4>
              <ul className="m-0 grid list-none gap-2 p-0 sm:grid-cols-2">
                {learned.map((e) => (
                  <li key={e.id} className="overflow-hidden rounded border border-border">
                    <div className="bg-surface"><Picture kind="example" id={e.id} alt="Website from your session" className="h-28" /></div>
                    <div className="space-y-1.5 p-2"><LabelPill label={e.label} /><Quote example={e} /></div>
                  </li>
                ))}
              </ul>
            </section>
          )}
          {!open.length && !learned.length && <p className="m-0 text-[12px] text-muted-foreground">No clear feedback found yet.</p>}
        </div>
      )}
    </CardShell>
  );
}
