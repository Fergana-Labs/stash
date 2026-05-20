"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { apiFetch, getToken } from "@/lib/api";
import type { StepCtx } from "@/lib/onboarding/paths";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:3456";

type Overview = {
  files: {
    pages: { id: string; name: string }[];
  };
};

// Tool events the agent emits when it reads workspace material. We surface
// these as citations — "Looked at: X, Y" — so the user sees real receipts
// that the answer was grounded on their imports.
const READ_TOOLS = new Set([
  "read_page",
  "grep_pages",
  "read_file",
  "search_history",
]);

type Citation = {
  tool: string;
  label: string;
};

export default function MemoryAskStep({ workspaceId }: StepCtx) {
  const [question, setQuestion] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [answer, setAnswer] = useState("");
  const [citations, setCitations] = useState<Citation[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [suggestions, setSuggestions] = useState<string[]>([]);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    if (!workspaceId) return;
    apiFetch<Overview>(`/api/v1/workspaces/${workspaceId}/overview`)
      .then((o) => {
        const pages = (o.files?.pages ?? []).slice(0, 3);
        if (pages.length >= 2) {
          setSuggestions([
            `What was the last thing we worked on in ${pages[0].name}?`,
            `Catch me up on ${pages[1].name}`,
            pages[2] ? `What's the state of ${pages[2].name}?` : `What have we been working on?`,
          ]);
        } else {
          setSuggestions([
            "What was the last thing we worked on?",
            "Catch me up on this workspace",
          ]);
        }
      })
      .catch(() => {});
  }, [workspaceId]);

  const ask = useCallback(
    async (q: string) => {
      if (!workspaceId || !q.trim() || streaming) return;
      setStreaming(true);
      setAnswer("");
      setCitations([]);
      setError(null);

      const controller = new AbortController();
      abortRef.current = controller;

      try {
        const res = await fetch(
          `${API_URL}/api/v1/workspaces/${workspaceId}/ask`,
          {
            method: "POST",
            headers: {
              "Content-Type": "application/json",
              Authorization: `Bearer ${getToken() ?? ""}`,
            },
            body: JSON.stringify({
              messages: [{ role: "user", content: q }],
              scope: "workspace",
            }),
            signal: controller.signal,
          },
        );
        if (!res.ok || !res.body) {
          throw new Error(`Ask failed: ${res.status}`);
        }

        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";
        for (;;) {
          const { done, value } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });
          const events = buffer.split("\n\n");
          buffer = events.pop() ?? "";
          for (const raw of events) {
            const line = raw.trim();
            if (!line.startsWith("data:")) continue;
            const payload = line.slice(5).trim();
            if (!payload) continue;
            try {
              const evt = JSON.parse(payload);
              if (evt.type === "text" && typeof evt.delta === "string") {
                setAnswer((prev) => prev + evt.delta);
              } else if (evt.type === "tool" && READ_TOOLS.has(evt.name)) {
                const label = describeToolCall(evt.name, evt.args);
                if (label) {
                  setCitations((prev) =>
                    prev.find((c) => c.label === label && c.tool === evt.name)
                      ? prev
                      : [...prev, { tool: evt.name, label }],
                  );
                }
              }
            } catch {
              // Ignore malformed lines — the SDK can emit partial chunks
              // we resume on next loop.
            }
          }
        }
      } catch (e) {
        if ((e as Error).name !== "AbortError") {
          setError(e instanceof Error ? e.message : String(e));
        }
      } finally {
        setStreaming(false);
        abortRef.current = null;
      }
    },
    [workspaceId, streaming],
  );

  useEffect(() => () => abortRef.current?.abort(), []);

  return (
    <div className="space-y-6">
      <div className="space-y-2">
        <h1 className="font-display text-[28px] leading-[1.1] font-bold tracking-tight text-foreground">
          Pick up where you left off
        </h1>
        <p className="text-sm text-dim max-w-md">
          Your agent has memory of what you&rsquo;ve done before. Ask
          anything — it&rsquo;ll look back at your sessions and answer with
          receipts.
        </p>
      </div>

      <BeforeAfter />

      <div className="rounded-2xl border border-border bg-surface p-4 space-y-3">
        <form
          onSubmit={(e) => {
            e.preventDefault();
            void ask(question);
          }}
          className="flex items-start gap-2"
        >
          <textarea
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            placeholder="Ask anything about your workspace…"
            rows={2}
            disabled={streaming}
            className="flex-1 rounded-md border border-border bg-base px-3 py-2 text-[13px] text-foreground placeholder:text-muted focus:border-brand focus:outline-none resize-none"
          />
          <button
            type="submit"
            disabled={streaming || !question.trim()}
            className="rounded-md bg-brand px-4 py-2 text-[13px] font-medium text-white hover:bg-brand-hover disabled:opacity-60"
          >
            {streaming ? "Asking…" : "Ask"}
          </button>
        </form>

        {suggestions.length > 0 && !answer && !streaming && (
          <div className="flex flex-wrap gap-2">
            {suggestions.map((s) => (
              <button
                key={s}
                type="button"
                onClick={() => {
                  setQuestion(s);
                  void ask(s);
                }}
                className="rounded-full border border-border-subtle bg-background/40 px-3 py-1 text-[11.5px] text-muted hover:text-foreground hover:border-brand"
              >
                {s}
              </button>
            ))}
          </div>
        )}

        {error && (
          <div className="text-[12px] text-error rounded-lg border border-error/30 bg-error/10 px-3 py-2">
            {error}
          </div>
        )}

        {(answer || citations.length > 0) && (
          <div className="rounded-xl border border-border-subtle bg-background/40 p-4 space-y-3">
            <div className="text-[13px] text-foreground whitespace-pre-wrap leading-relaxed">
              {answer}
              {streaming && (
                <span className="inline-block w-1.5 h-3 bg-brand ml-0.5 align-baseline animate-pulse" />
              )}
            </div>
            {citations.length > 0 && (
              <div className="border-t border-border-subtle pt-3 text-[11.5px] text-muted">
                <span className="font-medium text-foreground">
                  Grounded on:
                </span>{" "}
                {citations.map((c, i) => (
                  <span key={`${c.tool}-${c.label}-${i}`}>
                    {i > 0 && ", "}
                    <span className="font-mono">{c.label}</span>
                  </span>
                ))}
              </div>
            )}
          </div>
        )}
      </div>

      <p className="text-[11px] text-dim">
        Every conversation picks up where the last one left off. No more
        re-explaining what you&rsquo;re doing.
      </p>
    </div>
  );
}

function BeforeAfter() {
  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
      <div className="rounded-xl border border-border-subtle bg-background/40 p-4 opacity-60 min-h-[160px]">
        <div className="text-[10px] font-mono uppercase tracking-wider text-muted mb-2">
          Before
        </div>
        <pre className="font-mono text-[10.5px] text-muted leading-snug whitespace-pre-wrap">
          {`# Context

Last week I was working on the
API gateway. Here's where I left
off:

[paste 3,200 chars of session]
[re-explain the constraints]
[re-list the open questions]

OK, now keep going where we...`}
        </pre>
      </div>
      <div className="rounded-xl border border-brand bg-brand/5 p-4 min-h-[160px]">
        <div className="text-[10px] font-mono uppercase tracking-wider text-brand mb-2">
          After
        </div>
        <div className="space-y-2">
          <div className="font-mono text-[12.5px] text-foreground">
            Pick up where we left off on the gateway
          </div>
          <div className="inline-flex items-center gap-1.5 rounded-full bg-background/60 border border-border-subtle px-2 py-0.5 text-[10.5px] text-muted">
            <span className="w-1 h-1 rounded-full bg-brand" />
            remembers your past sessions
          </div>
        </div>
      </div>
    </div>
  );
}

function describeToolCall(name: string, args: Record<string, unknown> | undefined): string {
  if (!args) return name;
  if (name === "read_page" && typeof args.page_id === "string") {
    return `page ${shortId(args.page_id)}`;
  }
  if (name === "read_file" && typeof args.file_id === "string") {
    return `file ${shortId(args.file_id)}`;
  }
  if ((name === "grep_pages" || name === "search_history") && typeof args.query === "string") {
    return `search "${args.query.slice(0, 40)}"`;
  }
  return name;
}

function shortId(id: string): string {
  return id.length > 8 ? id.slice(0, 8) : id;
}
