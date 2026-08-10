"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { SkeletonBlock } from "@/components/SkeletonStates";
import { getCuratorLog, type CuratorLogEntry } from "@/lib/api";

function entryDate(entry: CuratorLogEntry): string {
  return new Date(entry.started_at).toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
  });
}

// Runs shown before "+N more runs" — the log flows with the page, so the
// tail is revealed, never scrolled inside its own box.
const ENTRY_ROWS = 5;

/** The curator log — what each nightly curation learned, newest first. One
 *  entry per run: its one-sentence summary, straight from the stored run.
 *  A failed run shows as failed. */
export default function CuratorLog() {
  const [entries, setEntries] = useState<CuratorLogEntry[] | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [showOlder, setShowOlder] = useState(false);

  useEffect(() => {
    let cancelled = false;
    getCuratorLog()
      .then((log) => {
        if (!cancelled) setEntries(log.entries);
      })
      .catch(() => {})
      .finally(() => {
        if (!cancelled) setLoaded(true);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  if (!loaded) {
    return (
      <section>
        <div className="sys-label mb-1.5">Curator log</div>
        <SkeletonBlock className="h-[120px] w-full" />
      </section>
    );
  }

  const visible = showOlder ? entries : entries?.slice(0, ENTRY_ROWS);

  return (
    <section>
      <div className="sys-label mb-1.5">Curator log</div>
      {!entries || !visible || entries.length === 0 ? (
        <div className="card-soft px-4 py-6 text-center text-[12.5px] text-muted-foreground">
          No entries yet. The curator writes one after every run — the first
          appears after tonight&apos;s pass.
        </div>
      ) : (
        <div className="flex flex-col gap-2.5">
          {visible.map((entry) => (
            <LogEntry key={entry.session_id} entry={entry} />
          ))}
          {!showOlder && entries.length > ENTRY_ROWS && (
            <button
              type="button"
              onClick={() => setShowOlder(true)}
              className="self-start text-[12.5px] text-muted-foreground underline decoration-dotted underline-offset-2 hover:text-foreground"
            >
              +{entries.length - ENTRY_ROWS} more {entries.length - ENTRY_ROWS === 1 ? "run" : "runs"}
            </button>
          )}
        </div>
      )}
    </section>
  );
}

function LogEntry({ entry }: { entry: CuratorLogEntry }) {
  return (
    <article className="card px-4 py-3.5">
      <div className="flex items-baseline justify-between gap-2">
        <span className="sys-label" style={{ fontSize: 10.5 }}>
          {entryDate(entry)}
        </span>
        <Link
          href={`/sessions/${encodeURIComponent(entry.session_id)}`}
          className="text-[11.5px] text-dim hover:text-foreground"
        >
          View run →
        </Link>
      </div>

      {entry.status === "failed" ? (
        <p className="mt-1.5 text-[13px] text-muted-foreground">
          Run failed{entry.error ? `: ${entry.error}` : "."}
        </p>
      ) : entry.status === "stopped" ? (
        <p className="mt-1.5 text-[13px] text-muted-foreground">Run stopped mid-pass.</p>
      ) : entry.summary ? (
        <p className="mt-1.5 whitespace-pre-line text-[13.5px] leading-[1.6] text-foreground">
          {entry.summary}
        </p>
      ) : (
        <p className="mt-1.5 text-[13px] text-muted-foreground">
          Run ended without a log entry.
        </p>
      )}
    </article>
  );
}
