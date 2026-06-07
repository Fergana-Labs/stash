"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";

import { track } from "@/lib/analytics";
import { API_BASE, apiFetch, getAuthToken } from "@/lib/api";
import { READ_TOOLS, describeToolCall } from "@/lib/agentChat";
import type { StepCtx } from "@/lib/onboarding/paths";

type Overview = {
  sessions: { session_id?: string; name?: string }[];
  files: {
    pages: { id: string; name: string }[];
  };
};

type Citation = { id: string; tool: string; label: string };

// Step 3: one live agentic search. Show a few personalized suggestions
// (or let user type their own), stream the answer with citations, then
// the wizard's "Continue" hands off to /workspaces/{id}. Single question
// by design — this is the demo, not the workspace itself.
export default function MemoryAskStep({
  workspaceId,
  onAnswered,
}: StepCtx & { onAnswered?: () => void }) {
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
        const token = await getAuthToken();
        const res = await fetch(
          `${API_BASE}/api/v1/workspaces/${workspaceId}/ask`,
          {
            method: "POST",
            headers: {
              "Content-Type": "application/json",
              ...(token ? { Authorization: `Bearer ${token}` } : {}),
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
                const id = String(evt.id ?? describeToolCall(evt.name, evt.args));
                const label = describeToolCall(evt.name, evt.args);
                setCitations((prev) =>
                  prev.some((c) => c.id === id)
                    ? prev
                    : [...prev, { id, tool: evt.name, label }],
                );
              } else if (evt.type === "tool_result" && evt.ok === false) {
                // The tool errored — don't claim it grounded the answer.
                setCitations((prev) => prev.filter((c) => c.id !== String(evt.id)));
              }
            } catch {
              // Partial chunks — resume on next loop.
            }
          }
        }
        // The agent finished — unblock "Launch workspace".
        onAnswered?.();
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
    [workspaceId, streaming, onAnswered],
  );

  useEffect(() => () => abortRef.current?.abort(), []);

  return (
    <div className="space-y-6">
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
          ) : streaming && !answer ? (
            <div className="flex items-center gap-2 py-2 text-[13px] text-muted">
              <span className="flex gap-1" aria-hidden>
                <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-brand [animation-delay:-0.3s]" />
                <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-brand [animation-delay:-0.15s]" />
                <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-brand" />
              </span>
              Thinking…
            </div>
          ) : (
            <>
              <div className="prose prose-sm max-w-none text-[13px] leading-relaxed text-foreground">
                <Markdown remarkPlugins={[remarkGfm]}>{answer}</Markdown>
                {streaming && (
                  <span className="inline-block h-3 w-1.5 animate-pulse bg-brand align-baseline" />
                )}
              </div>
              {citations.length > 0 && (
                <div className="border-t border-border-subtle pt-3 text-[11.5px] text-muted">
                  <span className="font-medium text-foreground">
                    Grounded on:
                  </span>{" "}
                  {citations.map((c, i) => (
                    <span key={c.id}>
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
