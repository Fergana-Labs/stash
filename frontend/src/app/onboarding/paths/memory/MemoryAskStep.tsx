"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { track } from "@/lib/analytics";
import { apiFetch, getToken } from "@/lib/api";
import type { StepCtx } from "@/lib/onboarding/paths";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:3456";

type Overview = {
  sessions: { session_id?: string; name?: string }[];
  files: {
    pages: { id: string; name: string }[];
  };
};

const READ_TOOLS = new Set([
  "read_page",
  "grep_pages",
  "read_file",
  "search_history",
]);

type Citation = { tool: string; label: string };

// Step 3: one live agentic search. Show a few personalized suggestions
// (or let user type their own), stream the answer with citations, then
// the wizard's "Continue" hands off to /workspaces/{id}. Single question
// by design — this is the demo, not the workspace itself.
export default function MemoryAskStep({ workspaceId }: StepCtx) {
  const [suggestions, setSuggestions] = useState<string[]>([]);
  const [question, setQuestion] = useState("");
  const [submitted, setSubmitted] = useState(false);
  const [streaming, setStreaming] = useState(false);
  const [answer, setAnswer] = useState("");
  const [citations, setCitations] = useState<Citation[]>([]);
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  // Read inside the streaming callback's finally block without restarting it
  // on every citation update.
  const citationsRef = useRef<Citation[]>([]);
  useEffect(() => {
    citationsRef.current = citations;
  }, [citations]);

  useEffect(() => {
    if (!workspaceId) return;
    apiFetch<Overview>(`/api/v1/workspaces/${workspaceId}/overview`)
      .then((o) => {
        const pages = (o.files?.pages ?? []).slice(0, 2);
        const sessions = (o.sessions ?? []).slice(0, 1);
        const out: string[] = [];
        if (sessions.length > 0) {
          const s = sessions[0];
          const label = s.name || s.session_id || "the last session";
          out.push(`What was I working on in ${label}?`);
        }
        if (pages.length > 0) {
          out.push(`Catch me up on ${pages[0].name}`);
        }
        if (pages.length > 1) {
          out.push(`What's the state of ${pages[1].name}?`);
        }
        if (out.length === 0) {
          out.push(
            "What's the last thing I worked on?",
            "Catch me up on this workspace",
          );
        }
        setSuggestions(out.slice(0, 3));
      })
      .catch(() => {
        setSuggestions([
          "What's the last thing I worked on?",
          "Catch me up on this workspace",
        ]);
      });
  }, [workspaceId]);

  const ask = useCallback(
    async (q: string) => {
      if (!workspaceId || !q.trim() || streaming) return;
      setSubmitted(true);
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
              // Partial chunks — resume on next loop.
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
        // Fire after the stream finishes so has_results reflects what we
        // actually rendered, not whether the request started.
        track("web.ask_stash", {
          workspace_id: workspaceId,
          has_results: citationsRef.current.length > 0,
        });
      }
    },
    [workspaceId, streaming],
  );

  useEffect(() => () => abortRef.current?.abort(), []);

  return (
    <div className="space-y-6">
      <div className="space-y-2">
        <h1 className="font-display text-[28px] leading-[1.1] font-bold tracking-tight text-foreground">
          Your agent can search anything
        </h1>
        <p className="text-sm text-dim max-w-md">
          This is what your agent has access to anytime it does work for you.
        </p>
      </div>

      {!submitted && (
        <div className="space-y-3">
          {suggestions.length > 0 && (
            <div className="flex flex-wrap gap-2">
              {suggestions.map((s) => (
                <button
                  key={s}
                  type="button"
                  onClick={() => {
                    setQuestion(s);
                    void ask(s);
                  }}
                  className="rounded-full border border-border bg-surface px-3 py-1.5 text-[12px] text-foreground hover:bg-raised hover:border-brand"
                >
                  {s}
                </button>
              ))}
            </div>
          )}

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
              placeholder="Or write your own…"
              rows={2}
              className="flex-1 rounded-md border border-border bg-base px-3 py-2 text-[13px] text-foreground placeholder:text-muted focus:border-brand focus:outline-none resize-none"
            />
            <button
              type="submit"
              disabled={!question.trim()}
              className="rounded-md bg-brand px-4 py-2 text-[13px] font-medium text-white hover:bg-brand-hover disabled:opacity-60"
            >
              Ask
            </button>
          </form>
        </div>
      )}

      {submitted && (
        <div className="rounded-2xl border border-border bg-surface p-4 space-y-3">
          <div className="text-[12px] text-muted italic">{question}</div>
          {error ? (
            <div className="text-[12px] text-error rounded-lg border border-error/30 bg-error/10 px-3 py-2">
              {error}
            </div>
          ) : (
            <>
              <div className="text-[13px] text-foreground whitespace-pre-wrap leading-relaxed min-h-[60px]">
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
            </>
          )}
        </div>
      )}

    </div>
  );
}

function describeToolCall(
  name: string,
  args: Record<string, unknown> | undefined,
): string {
  if (!args) return name;
  if (name === "read_page" && typeof args.page_id === "string") {
    return `page ${shortId(args.page_id)}`;
  }
  if (name === "read_file" && typeof args.file_id === "string") {
    return `file ${shortId(args.file_id)}`;
  }
  if (
    (name === "grep_pages" || name === "search_history") &&
    typeof args.query === "string"
  ) {
    return `search "${args.query.slice(0, 40)}"`;
  }
  return name;
}

function shortId(id: string): string {
  return id.length > 8 ? id.slice(0, 8) : id;
}
