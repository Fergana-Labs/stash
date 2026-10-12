"use client";

import Link from "next/link";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { ArrowLeft, MoreHorizontal, Pencil, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { errorMessage } from "@/components/reward-models/rm-text";
import { cn } from "@/lib/utils";
import { imDelete, imRename, imUpdateModel, type ModelDetail } from "@/lib/intuition-api";
import { Callout, ConfirmDialog, inputClass, Spinner, useIntuition } from "./im-ui";

export default function IntuitionHeader() {
  const { id, detail, apply, version, goTo } = useIntuition();
  const router = useRouter();
  const [editing, setEditing] = useState(false);
  const [name, setName] = useState(detail.model.name);
  const [saving, setSaving] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const { active, draft, judge } = detail;

  async function save() {
    const next = name.trim();
    if (!next || next === detail.model.name) {
      setEditing(false);
      setName(detail.model.name);
      return;
    }
    setSaving(true);
    try {
      apply(await imRename(id, next));
      setEditing(false);
    } catch (e) {
      toast.error(errorMessage(e));
    } finally {
      setSaving(false);
    }
  }

  return (
    <header>
      <Link href="/reward-models/intuitions" className="inline-flex items-center gap-1 text-[12px] text-muted-foreground hover:text-foreground">
        <ArrowLeft className="h-3.5 w-3.5" /> Intuitions
      </Link>
      <div className="mt-2 flex items-start gap-3">
        <div className="min-w-0 flex-1">
          {editing ? (
            <input
              autoFocus
              aria-label="Model name"
              value={name}
              disabled={saving}
              maxLength={160}
              onChange={(e) => setName(e.target.value)}
              onBlur={() => void save()}
              onKeyDown={(e) => {
                if (e.key === "Enter") void save();
                if (e.key === "Escape") {
                  setName(detail.model.name);
                  setEditing(false);
                }
              }}
              className={cn(inputClass, "font-display text-[20px] font-semibold tracking-tight")}
            />
          ) : (
            <h1 className="group m-0 flex min-w-0 items-center gap-2 font-display text-[22px] font-semibold tracking-tight text-foreground">
              <span className="truncate">{detail.model.name}</span>
              <button
                type="button"
                aria-label="Rename"
                onClick={() => {
                  setName(detail.model.name);
                  setEditing(true);
                }}
                className="rounded p-1 text-muted-foreground opacity-0 group-hover:opacity-100 hover:bg-muted hover:text-foreground focus-visible:opacity-100"
              >
                <Pencil className="h-3.5 w-3.5" />
              </button>
            </h1>
          )}
          <div className="mt-1.5 flex flex-wrap items-center gap-2 text-[12px] text-muted-foreground">
            <span className="tag tag-muted">{detail.model.output_type}</span>
            {active ? <span className="tag tag-success">Active v{active.number}</span> : <span className="tag tag-muted">No active version</span>}
            {draft && (
              <button type="button" onClick={() => goTo("versions")} className="tag tag-warning hover:opacity-80" title="Edits land on the draft until you promote it">
                Draft v{draft.number} · unpromoted changes
              </button>
            )}
            <span className="inline-flex items-center gap-1.5 font-mono text-[11.5px]" title={judge.configured ? "Judge configured" : "Judge not configured"}>
              <span className={cn("h-1.5 w-1.5 rounded-full", judge.configured ? "bg-emerald-500" : "bg-red-500")} />
              {judge.provider} · {version?.provider_model ?? judge.model}
            </span>
          </div>
        </div>
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="ghost" size="icon-sm" aria-label="More actions">
              <MoreHorizontal />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            <DropdownMenuItem
              onSelect={() => {
                setName(detail.model.name);
                setEditing(true);
              }}
            >
              <Pencil /> Rename
            </DropdownMenuItem>
            <DropdownMenuItem variant="destructive" onSelect={() => setDeleting(true)}>
              <Trash2 /> Delete model
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
      <WhenToUse id={id} detail={detail} apply={apply} />
      {!judge.configured && (
        <div className="mt-3">
          <Callout tone="warning">
            Jev is not configured: set <code className="font-mono">TYPESAFE_API_KEY</code>. Cached answers still work; grading new items and changed questions will fail.
          </Callout>
        </div>
      )}
      <ConfirmDialog
        open={deleting}
        onOpenChange={setDeleting}
        title={`Delete “${detail.model.name}”?`}
        description="This deletes every version, example, cached judge answer and logged prediction. Agents calling it will start failing. This can’t be undone."
        confirmLabel="Delete model"
        destructive
        onConfirm={async () => {
          try {
            await imDelete(id);
            toast.success("Model deleted");
            router.push("/reward-models/intuitions");
          } catch (e) {
            toast.error(errorMessage(e));
            return false;
          }
        }}
      />
    </header>
  );
}

const WHEN_MAX = 2000;

/** Model-level "when to use", like a skill description: what agents read to decide whether to consult this model. */
function WhenToUse({ id, detail, apply }: { id: string; detail: ModelDetail; apply: (detail: ModelDetail) => void }) {
  const saved = detail.model.when_to_use ?? "";
  const [editing, setEditing] = useState(false);
  const [text, setText] = useState(saved);
  const [saving, setSaving] = useState(false);

  async function save() {
    const next = text.trim();
    if (next === saved) return setEditing(false);
    setSaving(true);
    try {
      apply(await imUpdateModel(id, { when_to_use: next }));
      setEditing(false);
      toast.success("Saved when to use");
    } catch (e) {
      toast.error(errorMessage(e));
    } finally {
      setSaving(false);
    }
  }

  const label = <span className="text-[10.5px] font-medium tracking-wide text-muted-foreground uppercase">When to use</span>;
  const hint = "Agents read this to decide when to consult the model, like a skill description. It isn’t versioned and changes take effect immediately.";

  if (editing) {
    return (
      <form
        className="mt-3 max-w-3xl"
        onSubmit={(e) => {
          e.preventDefault();
          void save();
        }}
      >
        <label htmlFor="im-when-to-use">{label}</label>
        <textarea
          id="im-when-to-use"
          autoFocus
          rows={3}
          value={text}
          maxLength={WHEN_MAX}
          disabled={saving}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
              e.preventDefault();
              void save();
            }
            if (e.key === "Escape") {
              setText(saved);
              setEditing(false);
            }
          }}
          placeholder="Before sending a drafted customer-support reply: check whether it’s ready to send, needs a light edit, or needs a rewrite."
          className={cn(inputClass, "mt-1 resize-y leading-relaxed")}
        />
        <div className="mt-1.5 flex flex-wrap items-center gap-2">
          <span className="min-w-0 flex-1 text-[11.5px] leading-snug text-muted-foreground">{hint}</span>
          <span className="font-mono text-[10.5px] text-muted-foreground tabular-nums">
            {text.length}/{WHEN_MAX}
          </span>
          <Button
            type="button"
            variant="ghost"
            size="xs"
            disabled={saving}
            onClick={() => {
              setText(saved);
              setEditing(false);
            }}
          >
            Cancel
          </Button>
          <Button type="submit" size="xs" disabled={saving}>
            {saving && <Spinner className="h-3 w-3" />}
            Save
          </Button>
        </div>
      </form>
    );
  }

  return (
    <div className="group mt-3 max-w-3xl">
      <div className="flex items-center gap-1.5">
        {label}
        <button
          type="button"
          aria-label="Edit when to use"
          onClick={() => {
            setText(saved);
            setEditing(true);
          }}
          className="rounded p-0.5 text-muted-foreground opacity-60 group-hover:opacity-100 hover:bg-muted hover:text-foreground focus-visible:opacity-100"
        >
          <Pencil className="h-3 w-3" />
        </button>
      </div>
      {saved ? (
        <p className="m-0 mt-0.5 text-[12.5px] leading-relaxed whitespace-pre-wrap text-dim">{saved}</p>
      ) : (
        <button
          type="button"
          onClick={() => {
            setText("");
            setEditing(true);
          }}
          className="mt-0.5 text-left text-[12.5px] text-muted-foreground underline decoration-dashed decoration-border underline-offset-2 hover:text-foreground"
        >
          Describe when an agent should consult this model, so it can find it like a skill.
        </button>
      )}
    </div>
  );
}
