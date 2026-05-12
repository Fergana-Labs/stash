"use client";

import { useEffect, useState } from "react";
import Markdown from "react-markdown";
import rehypeRaw from "rehype-raw";
import remarkGfm from "remark-gfm";
import {
  editStashHandoff,
  getStashHandoff,
  refreshStashHandoff,
  unpinStashHandoff,
  type StashHandoff,
} from "../../lib/api";

interface HandoffPanelProps {
  stashId: string;
  canWrite: boolean;
  // Initial bits from the spine response so we can decide whether to render
  // before the body GET resolves.
  spineHint?: { present: boolean; stale: boolean; pinned_at: string | null };
}

export default function HandoffPanel({ stashId, canWrite, spineHint }: HandoffPanelProps) {
  const [data, setData] = useState<StashHandoff | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    let cancel = false;
    setLoading(true);
    getStashHandoff(stashId)
      .then((d) => {
        if (!cancel) setData(d);
      })
      .catch((e) => {
        if (!cancel) setError(e instanceof Error ? e.message : "Failed to load handoff");
      })
      .finally(() => {
        if (!cancel) setLoading(false);
      });
    return () => {
      cancel = true;
    };
  }, [stashId]);

  const isPinned = !!data?.pinned_at;
  const hasBody = !!data?.body_markdown;

  async function handleRegenerate() {
    setBusy(true);
    setError("");
    try {
      const fresh = await getStashHandoff(stashId, { wait: true, maxWait: 90 });
      setData(fresh);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to regenerate");
    } finally {
      setBusy(false);
    }
  }

  async function handleQueueRefresh() {
    setBusy(true);
    setError("");
    try {
      await refreshStashHandoff(stashId);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to queue refresh");
    } finally {
      setBusy(false);
    }
  }

  function startEdit() {
    setDraft(data?.body_markdown ?? "");
    setEditing(true);
  }

  async function saveEdit() {
    setBusy(true);
    setError("");
    try {
      const updated = await editStashHandoff(stashId, draft);
      setData(updated);
      setEditing(false);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to save");
    } finally {
      setBusy(false);
    }
  }

  async function handleUnpin() {
    setBusy(true);
    setError("");
    try {
      const updated = await unpinStashHandoff(stashId);
      setData(updated);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to unpin");
    } finally {
      setBusy(false);
    }
  }

  async function handleCopy() {
    if (!data?.body_markdown) return;
    try {
      await navigator.clipboard.writeText(data.body_markdown);
    } catch {
      /* ignore */
    }
  }

  // Don't render anything while loading if we don't even have a hint of a body.
  if (loading && !spineHint?.present) {
    return null;
  }

  return (
    <section className="mt-6 rounded-xl border border-border bg-surface p-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="text-[10.5px] font-semibold uppercase tracking-wider text-muted">
            Orientation
          </span>
          <span className="text-[11px] text-muted">— agent-curated overview</span>
        </div>
        <div className="flex items-center gap-2 text-[11px] text-muted">
          {isPinned && (
            <span className="rounded-full bg-amber-100 px-2 py-0.5 text-amber-800">
              📌 Pinned
            </span>
          )}
          {!isPinned && data?.stale && hasBody && (
            <span className="rounded-full bg-blue-50 px-2 py-0.5 text-blue-700">
              Refreshing soon
            </span>
          )}
        </div>
      </div>

      {error && (
        <div className="mt-2 rounded-md bg-red-50 px-3 py-2 text-[12px] text-red-700">
          {error}
        </div>
      )}

      {editing ? (
        <div className="mt-3">
          <textarea
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            className="min-h-[280px] w-full rounded-md border border-border bg-base p-3 font-mono text-[13px] leading-relaxed"
            placeholder="Markdown handoff document. Saving will pin this until you unpin."
          />
        </div>
      ) : hasBody ? (
        <div className="prose prose-sm mt-3 max-w-none text-foreground">
          <Markdown remarkPlugins={[remarkGfm]} rehypePlugins={[rehypeRaw]}>
            {data!.body_markdown}
          </Markdown>
        </div>
      ) : (
        <div className="mt-3 rounded-lg border border-dashed border-border bg-base/50 p-6 text-center">
          <div className="text-[13px] text-muted">
            An orientation summary will appear here once the curator runs.
          </div>
          {canWrite && (
            <button
              onClick={handleRegenerate}
              disabled={busy}
              className="mt-3 rounded-md bg-[var(--color-brand-600)] px-3 py-1.5 text-[12px] font-medium text-white hover:bg-[var(--color-brand-700)] disabled:opacity-60"
            >
              {busy ? "Generating…" : "Generate now"}
            </button>
          )}
        </div>
      )}

      <div className="mt-3 flex items-center justify-between text-[11px] text-muted">
        <div className="flex items-center gap-2">
          {data?.generated_at && <span>Updated {formatRelative(data.generated_at)}</span>}
          {data?.model && <span>· {data.model}</span>}
          {data?.turns_used != null && data.turns_used > 0 && (
            <span>· {data.turns_used} turn{data.turns_used === 1 ? "" : "s"}</span>
          )}
          {data?.input_tokens != null && data.input_tokens > 0 && (
            <span>· {Math.round(data.input_tokens / 100) / 10}k tokens</span>
          )}
        </div>
        {canWrite && (
          <div className="flex items-center gap-2">
            {editing ? (
              <>
                <button
                  onClick={() => setEditing(false)}
                  disabled={busy}
                  className="rounded-md border border-border px-2.5 py-1 text-[11px] hover:bg-base"
                >
                  Cancel
                </button>
                <button
                  onClick={saveEdit}
                  disabled={busy}
                  className="rounded-md bg-[var(--color-brand-600)] px-2.5 py-1 text-[11px] font-medium text-white hover:bg-[var(--color-brand-700)] disabled:opacity-60"
                >
                  {busy ? "Saving…" : "Save (pins)"}
                </button>
              </>
            ) : (
              <>
                {!isPinned && hasBody && (
                  <button
                    onClick={handleQueueRefresh}
                    disabled={busy}
                    className="rounded-md border border-border px-2.5 py-1 text-[11px] hover:bg-base disabled:opacity-60"
                    title="Mark stale — worker will rerun"
                  >
                    Queue refresh
                  </button>
                )}
                {!isPinned && (
                  <button
                    onClick={handleRegenerate}
                    disabled={busy}
                    className="rounded-md border border-border px-2.5 py-1 text-[11px] hover:bg-base disabled:opacity-60"
                  >
                    {busy ? "…" : "Regenerate"}
                  </button>
                )}
                {hasBody && (
                  <button
                    onClick={handleCopy}
                    disabled={busy}
                    className="rounded-md border border-border px-2.5 py-1 text-[11px] hover:bg-base"
                  >
                    Copy
                  </button>
                )}
                {hasBody && (
                  <button
                    onClick={startEdit}
                    disabled={busy}
                    className="rounded-md border border-border px-2.5 py-1 text-[11px] hover:bg-base disabled:opacity-60"
                    title="Edit will pin the doc"
                  >
                    Edit
                  </button>
                )}
                {isPinned && (
                  <button
                    onClick={handleUnpin}
                    disabled={busy}
                    className="rounded-md border border-amber-300 bg-amber-50 px-2.5 py-1 text-[11px] text-amber-800 hover:bg-amber-100 disabled:opacity-60"
                  >
                    Unpin and let curator resume
                  </button>
                )}
              </>
            )}
          </div>
        )}
      </div>
    </section>
  );
}

function formatRelative(iso: string): string {
  const then = new Date(iso).getTime();
  const now = Date.now();
  const sec = Math.max(0, Math.round((now - then) / 1000));
  if (sec < 60) return `${sec}s ago`;
  const min = Math.round(sec / 60);
  if (min < 60) return `${min}m ago`;
  const hr = Math.round(min / 60);
  if (hr < 24) return `${hr}h ago`;
  const day = Math.round(hr / 24);
  return `${day}d ago`;
}
