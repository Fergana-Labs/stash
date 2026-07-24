"use client";

import { useEffect, useRef, useState } from "react";
import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";

import { listAgentRuns, type AgentRun } from "@/lib/api";

// A scheduled agent's history as one continuous feed. Every run is its own
// session — a fresh context — so a reset separator opens each run. The right
// rail is the feed's map: one entry per run, click to jump, scroll to track.
export default function AgentRunsView({ agentId }: { agentId: string }) {
  const [runs, setRuns] = useState<AgentRun[] | null>(null);
  const [active, setActive] = useState(0);
  const scrollRef = useRef<HTMLDivElement>(null);
  const runRefs = useRef<(HTMLDivElement | null)[]>([]);

  useEffect(() => {
    listAgentRuns(agentId).then(setRuns).catch(() => setRuns([]));
  }, [agentId]);

  // Open at the newest run, chat-style.
  useEffect(() => {
    if (!runs?.length) return;
    const el = scrollRef.current;
    if (el) el.scrollTop = el.scrollHeight;
    setActive(runs.length - 1);
  }, [runs]);

  function onScroll() {
    const el = scrollRef.current;
    if (!el) return;
    // Pinned to the bottom means the newest run, even when it's shorter than
    // the viewport and its separator never crosses the threshold line.
    if (el.scrollTop + el.clientHeight >= el.scrollHeight - 4) {
      setActive(runRefs.current.length - 1);
      return;
    }
    const threshold = el.scrollTop + el.clientHeight / 3;
    let current = 0;
    runRefs.current.forEach((r, i) => {
      if (r && r.offsetTop <= threshold) current = i;
    });
    setActive(current);
  }

  if (runs === null) {
    return <div className="p-6 text-[13px] text-muted-foreground">Loading runs…</div>;
  }
  if (runs.length === 0) {
    return (
      <div className="p-6 text-[13px] text-muted-foreground">
        No runs yet. Runs appear here after the schedule fires (or Run now from Config).
      </div>
    );
  }

  return (
    <div className="flex h-full min-h-0">
      <div
        ref={scrollRef}
        onScroll={onScroll}
        // relative so run offsetTops are measured against this scroller.
        className="scroll-thin relative min-w-0 flex-1 overflow-y-auto px-4 pb-6"
      >
        {runs.map((run, i) => (
          <div
            key={run.session_id}
            ref={(el) => {
              runRefs.current[i] = el;
            }}
          >
            <RunSeparator run={run} />
            {run.messages.map((m, j) =>
              m.role === "user" ? (
                <PromptDisclosure key={j} content={m.content} />
              ) : (
                <div
                  key={j}
                  className="markdown-content mt-2 text-[13px] leading-relaxed text-foreground"
                >
                  <Markdown remarkPlugins={[remarkGfm]}>{m.content}</Markdown>
                </div>
              ),
            )}
          </div>
        ))}
      </div>

      <div className="hidden w-44 shrink-0 overflow-y-auto border-l border-border py-3 pr-3 pl-2 sm:block">
        <div className="px-2 pb-2 text-[10.5px] font-medium uppercase tracking-wide text-muted-foreground">
          Runs
        </div>
        {runs.map((run, i) => (
          <button
            key={run.session_id}
            type="button"
            onClick={() =>
              runRefs.current[i]?.scrollIntoView({ behavior: "smooth", block: "start" })
            }
            className={
              "block w-full cursor-pointer truncate rounded px-2 py-1 text-left text-[12px] " +
              (i === active
                ? "bg-surface font-medium text-foreground"
                : "text-dim hover:text-foreground")
            }
          >
            {runDate(run)}
            {run.failed && <span className="ml-1.5 align-middle text-[9px] text-error">●</span>}
          </button>
        ))}
      </div>
    </div>
  );
}

function runDate(run: AgentRun): string {
  return new Date(run.started_at).toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

function RunSeparator({ run }: { run: AgentRun }) {
  return (
    <div className="flex items-center gap-3 pt-6 pb-1">
      <div className="h-px flex-1 bg-border" />
      <span className="text-[11px] whitespace-nowrap text-muted-foreground">
        {runDate(run)} · fresh context
        {run.failed && <span className="text-error"> · failed</span>}
      </span>
      <div className="h-px flex-1 bg-border" />
    </div>
  );
}

// The run's instruction is internal boilerplate (the same rendered prompt every
// tick), so it collapses by default and the feed reads result-first.
function PromptDisclosure({ content }: { content: string }) {
  return (
    <details className="mt-2">
      <summary className="cursor-pointer text-[11.5px] text-muted-foreground select-none hover:text-foreground">
        Show prompt
      </summary>
      <div className="mt-1.5 rounded-md border border-border-subtle bg-surface px-3 py-2 text-[12px] leading-relaxed whitespace-pre-wrap text-dim">
        {content}
      </div>
    </details>
  );
}
