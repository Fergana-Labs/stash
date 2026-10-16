"use client";
/* eslint-disable @next/next/no-img-element -- Authenticated bounded image data URLs. */
import { useEffect, useState } from "react";
import { Check, Copy } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { errorMessage } from "@/components/reward-models/rm-text";
import {
  tasteImage,
  type TasteExample,
  type TasteTrial,
} from "@/lib/taste-api";
const inputClass =
  "w-full rounded border border-border bg-background px-3 py-2 text-sm";

export function Picture({
  kind,
  id,
  alt,
  className = "",
}: {
  kind: string;
  id: string;
  alt: string;
  className?: string;
}) {
  const [url, setUrl] = useState("");
  const [error, setError] = useState("");
  useEffect(() => {
    let active = true;
    tasteImage(kind, id)
      .then((r) => {
        if (active) setUrl(r.data_url);
      })
      .catch((e) => {
        if (active) setError(errorMessage(e));
      });
    return () => {
      active = false;
    };
  }, [kind, id]);
  // Authenticated pixels; generated HTML is never executed in the workspace.
  return url ? (
    <img
      src={url}
      alt={alt}
      className={cn("w-full object-contain object-top", className)}
    />
  ) : (
    <div className="flex min-h-36 items-center justify-center bg-surface p-6 text-xs text-muted-foreground">
      {error || "Loading preview…"}
    </div>
  );
}
export function CopyText({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <div className="relative">
      <pre className="max-h-80 overflow-auto whitespace-pre sm:whitespace-pre-wrap sm:break-words rounded border border-border bg-surface p-4 pt-11 sm:pt-4 sm:pr-20 font-mono text-xs">
        {text}
      </pre>
      <Button
        size="xs"
        variant="outline"
        className="absolute right-2 top-2"
        onClick={() =>
          void navigator.clipboard.writeText(text).then(() => setCopied(true))
        }
      >
        {copied ? <Check /> : <Copy />}
        {copied ? "Copied" : "Copy"}
      </Button>
    </div>
  );
}
export function ReviewCard({
  example,
  onSave,
  onInspect,
}: {
  example: TasteExample;
  onSave: (label: string, note: string) => Promise<void>;
  onInspect: () => void;
}) {
  const [note, setNote] = useState(example.note);
  const [busy, setBusy] = useState(false);
  async function save(label: string) {
    setBusy(true);
    try {
      await onSave(label, note);
    } finally {
      setBusy(false);
    }
  }
  return (
    <article className="overflow-hidden rounded border border-border bg-background">
      <button
        className="block w-full cursor-zoom-in bg-surface"
        aria-label="Inspect preference evidence"
        onClick={onInspect}
      >
        <Picture
          kind="example"
          id={example.id}
          alt="Website from your history"
          className="h-56"
        />
      </button>
      <div className="space-y-3 p-4">
        <div className="flex flex-wrap justify-between gap-2 text-xs text-muted-foreground">
          <span>
            {example.reference ? "Reference you shared" : "Past website output"}
          </span>
          <span>
            {example.reviewed
              ? "Confirmed by you"
              : example.usable
                ? "Learned from your feedback"
                : example.label_status === "model_guess"
                  ? "Model guess · excluded"
                  : "Unclear · excluded"}{" "}
            · {example.partition}
          </span>
        </div>
        <blockquote className="m-0 border-l-2 border-brand-500/40 pl-3 text-sm">
          {example.quote ||
            "No clear human feedback is attached to this output."}
        </blockquote>
        <p className="m-0 text-xs text-muted-foreground">
          {example.usable
            ? `Label: ${example.label}${example.reference ? " · desired reference" : example.scope === "aspect" ? " · specific visual aspect" : ""}. No confirmation needed.`
            : "This example is excluded unless clearer evidence or your answer supplies a label."}{" "}
          {example.reason}
        </p>
        <details>
          <summary className="cursor-pointer text-xs text-muted-foreground">
            {example.usable
              ? "Correct this interpretation (optional)"
              : "Clarify this example"}
          </summary>
          <div className="mt-3 space-y-3">
            <label className="block text-xs text-muted-foreground">
              What matters to you?
              <textarea
                className={cn(inputClass, "mt-1")}
                rows={2}
                value={note}
                onChange={(e) => setNote(e.target.value)}
                placeholder="Optional: what should the agent learn?"
              />
            </label>
            <div className="flex flex-wrap gap-2">
              {[
                ["liked", "Keep this"],
                ["disliked", "Change this"],
                ["skip", "Skip"],
              ].map(([label, title]) => (
                <Button
                  key={label}
                  size="sm"
                  disabled={busy}
                  variant={
                    example.usable && example.label === label
                      ? "default"
                      : "outline"
                  }
                  onClick={() => void save(label)}
                >
                  {title}
                  {example.usable && example.label === label && <Check />}
                </Button>
              ))}
            </div>
          </div>
        </details>
      </div>
    </article>
  );
}
export function Design({
  trial,
  onInspect,
}: {
  trial: TasteTrial;
  onInspect: () => void;
}) {
  return (
    <article className="overflow-hidden rounded border border-border">
      <button
        className="block w-full cursor-zoom-in bg-surface"
        onClick={onInspect}
        aria-label={`Inspect ${trial.methodLabel} ${trial.task}`}
      >
        {trial.image ? (
          <Picture
            kind="design"
            id={trial.id}
            alt={`${trial.methodLabel}: ${trial.task}`}
            className="h-72"
          />
        ) : (
          <div className="flex h-72 items-center justify-center text-sm text-muted-foreground">
            {trial.status === "invalid"
              ? "Incomplete HTML output"
              : trial.status}
          </div>
        )}
      </button>
      <div className="space-y-2 p-4">
        <div className="flex justify-between gap-2">
          <strong className="text-sm">{trial.methodLabel}</strong>
          <span className="font-mono text-sm">
            {trial.score == null ? "Unscored" : trial.score.toFixed(3)}
          </span>
        </div>
        <p className="m-0 text-xs text-muted-foreground">
          {trial.score == null
            ? "No score from this grader"
            : "Uncalibrated taste readout"}
        </p>
        <button className="text-xs underline" onClick={onInspect}>
          View skill, changes &amp; grader evidence →
        </button>
      </div>
    </article>
  );
}
