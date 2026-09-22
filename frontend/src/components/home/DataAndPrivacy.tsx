"use client";

import { useEffect, useState } from "react";
import { listUploadSources, updateUploadSource, type UploadSource } from "@/lib/api";
import { useScope } from "@/lib/scope-store";
import { cn } from "@/lib/utils";

const CLIENT_LABELS: Record<string, string> = {
  claude_code: "Claude Code",
  codex_cli: "Codex",
  cursor: "Cursor",
  gemini_cli: "Gemini CLI",
  opencode: "OpenCode",
  openclaw: "OpenClaw",
  hermes: "Hermes",
};

export default function DataAndPrivacy() {
  const scope = useScope();
  const [sources, setSources] = useState<UploadSource[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setSources(null);
    setError(null);
    listUploadSources()
      .then(({ sources: next }) => {
        if (!cancelled) setSources(next);
      })
      .catch((reason) => {
        if (!cancelled) {
          setError(reason instanceof Error ? reason.message : "Could not load upload sources");
        }
      });
    return () => {
      cancelled = true;
    };
  }, [scope?.scope_user_id]);

  return (
    <section className="rounded-2xl border border-border bg-surface p-6">
      <div>
        <h2 className="font-display text-[16px] font-semibold text-foreground">
          Your Stash installations
        </h2>
        <p className="mt-0.5 text-[12.5px] text-muted-foreground">
          The coding agents connected to this Stash.
        </p>
      </div>

      <div className="mt-5">
        <UploadSourceList sources={sources} error={error} />
      </div>
    </section>
  );
}

function UploadSourceList({
  sources,
  error,
}: {
  sources: UploadSource[] | null;
  error: string | null;
}) {
  if (error) {
    return <p className="text-[12.5px] text-destructive">Couldn&apos;t load: {error}</p>;
  }
  if (sources === null) {
    return <div className="h-[58px] animate-pulse rounded-xl bg-raised" />;
  }
  if (sources.length === 0) {
    return (
      <div className="rounded-xl border border-border bg-base px-4 py-3 text-[12.5px] text-muted-foreground">
        No CLI computers are signed in to this Stash yet.
      </div>
    );
  }

  return (
    <div className="divide-y divide-border border-y border-border">
      {sources.map((source) => (
        <div
          key={`${source.client ?? "waiting"}-${source.key_id ?? "unrecorded"}`}
          className="flex items-center justify-between gap-5 py-3"
        >
          <div className="min-w-0">
            <div className="truncate text-[13px] font-medium text-foreground">
              {source.client ? `${clientLabel(source.client)} on ` : ""}
              {computerLabel(source.key_name)}
            </div>
            <div className="text-[11.5px] text-muted-foreground">
              {source.last_uploaded_at ? (
                <>
                  {source.session_count} {source.session_count === 1 ? "session" : "sessions"} ·
                  last upload {relativeTime(source.last_uploaded_at)}
                </>
              ) : (
                "Signed in · waiting for the next coding-agent upload"
              )}
            </div>
          </div>
          {source.can_manage && source.key_id && source.uploads_enabled !== null && (
            <UploadToggle source={source} />
          )}
        </div>
      ))}
    </div>
  );
}

function UploadToggle({ source }: { source: UploadSource }) {
  const [enabled, setEnabled] = useState(source.uploads_enabled === true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function toggle() {
    if (!source.key_id) return;
    const next = !enabled;
    setSaving(true);
    setError(null);
    try {
      await updateUploadSource(source.key_id, next);
      setEnabled(next);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not change upload setting");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="shrink-0 text-right">
      <button
        role="switch"
        aria-checked={enabled}
        disabled={saving}
        onClick={() => void toggle()}
        className="group flex cursor-pointer items-center gap-2 disabled:opacity-50"
      >
        <span
          className={cn(
            "relative h-5 w-9 rounded-full transition-colors",
            enabled ? "bg-brand-500" : "bg-border group-hover:bg-muted-foreground/40",
          )}
        >
          <span
            className={cn(
              "absolute top-0.5 h-4 w-4 rounded-full bg-white shadow-sm transition-[left]",
              enabled ? "left-[18px]" : "left-0.5",
            )}
          />
        </span>
        <span
          className={cn(
            "w-[92px] whitespace-nowrap text-left text-[13px]",
            enabled ? "font-medium text-brand-500" : "text-muted-foreground",
          )}
        >
          {enabled ? "Uploading" : "Not uploading"}
        </span>
      </button>
      {error && <div className="mt-1 text-[11.5px] text-error">{error}</div>}
    </div>
  );
}

function clientLabel(client: string): string {
  const label = CLIENT_LABELS[client];
  if (!label) throw new Error(`Unknown coding-agent client: ${client}`);
  return label;
}

function computerLabel(keyName: string | null): string {
  if (keyName === null) return "computer not recorded";
  const cliName = /^CLI \((.+)\)$/.exec(keyName);
  return cliName ? cliName[1] : keyName;
}

function relativeTime(iso: string): string {
  const elapsedSeconds = Math.max(0, Math.floor((Date.now() - new Date(iso).getTime()) / 1000));
  if (elapsedSeconds < 60) return "just now";
  const minutes = Math.floor(elapsedSeconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.floor(hours / 24)}d ago`;
}
