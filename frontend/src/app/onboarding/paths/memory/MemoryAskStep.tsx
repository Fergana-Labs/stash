"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";

import { track } from "@/lib/analytics";
import { API_BASE, getAuthToken, getOverview } from "@/lib/api";

type Citation = { id: string; tool: string; label: string };

// The onboarding ask runs the in-process tool loop (not the cloud agent), so
// its stream carries the API tool names below — distinct from the cloud
// agent's harness tools labelled in lib/agentChat.ts.
const READ_TOOLS = new Set([
  "read_page",
  "grep_pages",
  "read_file",
  "search_history",
  "search",
  "read_source",
  "list_source",
]);

function shortId(id: string): string {
  return id.length > 8 ? id.slice(0, 8) : id;
}

function describeToolCall(name: string, args: Record<string, unknown> | undefined): string {
  if (!args) return name;
  if (name === "read_page" && typeof args.page_id === "string") return `page ${shortId(args.page_id)}`;
  if (name === "read_file" && typeof args.file_id === "string") return `file ${shortId(args.file_id)}`;
  if (
    (name === "grep_pages" || name === "search_history" || name === "search") &&
    typeof args.query === "string"
  ) {
    return `search "${args.query.slice(0, 40)}"`;
  }
  if (name === "read_source" && typeof args.ref === "string") return `read ${args.ref.slice(0, 48)}`;
  if (name === "list_source" && typeof args.source === "string") {
    const path = typeof args.path === "string" && args.path ? `/${args.path}` : "";
    return `browse ${args.source}${path}`;
  }
  return name;
}

// Step 3: one live agentic search. Show a few personalized suggestions
// (or let user type their own), stream the answer with citations, then
// the wizard's "Continue" hands off to the user's drive. Single question
// by design — this is the demo, not the drive itself.
export default function MemoryAskStep({
  onAnswered,
}: { onAnswered?: () => void }) {
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
    getOverview()
      .then((o) => {
        const pages = (o.files?.pages ?? []).slice(0, 2);
        const sessions = (o.sessions ?? []).slice(0, 1);
        const out: string[] = [];
        if (sessions.length > 0) {
          const s = sessions[0];
          const label = s.title || s.session_id || "the last session";
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
            "Catch me up on my drive",
          );
        }
        setSuggestions(out.slice(0, 3));
      })
      .catch(() => {
        setSuggestions([
          "What's the last thing I worked on?",
          "Catch me up on my drive",
        ]);
      });
  }, []);

  const ask = useCallback(
    async (q: string) => {
      if (!q.trim() || streaming) return;
      setSubmitted(true);
      setStreaming(true);
      setAnswer("");
      setCitations([]);
      setError(null);

      const controller = new AbortController();
      abortRef.current = controller;

      try {
        const token = await getAuthToken();
        const res = await fetch(`${API_BASE}/api/v1/me/ask`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            ...(token ? { Authorization: `Bearer ${token}` } : {}),
          },
          body: JSON.stringify({
            messages: [{ role: "user", content: q }],
          }),
          signal: controller.signal,
        });
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
        // The agent finished — unblock "Launch drive".
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
        track("web.ask_skill", {
          has_results: citationsRef.current.length > 0,
        });
      }
    },
    [streaming, onAnswered],
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
                  className="cursor-pointer rounded-full border border-border bg-surface px-3 py-1.5 text-[12px] text-foreground hover:bg-raised hover:border-brand"
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
              className="flex-1 rounded-md border border-border bg-base px-3 py-2 text-[13px] text-foreground placeholder:text-muted-foreground focus:border-brand focus:outline-none resize-none"
            />
            <button
              type="submit"
              disabled={!question.trim()}
              className="cursor-pointer rounded-md bg-brand px-4 py-2 text-[13px] font-medium text-white hover:bg-brand-hover disabled:opacity-60"
            >
              Ask
            </button>
          </form>
        </div>
      )}

      {submitted && (
        <div className="rounded-2xl border border-border bg-surface p-4 space-y-3">
          <div className="text-[12px] text-muted-foreground italic">{question}</div>
          {error ? (
            <div className="text-[12px] text-error rounded-lg border border-error/30 bg-error/10 px-3 py-2">
              {error}
            </div>
          ) : streaming && !answer ? (
            <div className="flex items-center gap-2 py-2 text-[13px] text-muted-foreground">
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
                <div className="border-t border-border-subtle pt-3 text-[11.5px] text-muted-foreground">
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
