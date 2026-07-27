"use client";

import { useEffect, useState } from "react";
import { readSourceDoc } from "@/lib/api";

// Inline viewer for one connected-source document: fetches the content lazily
// and shows the provider deep link when the backend can derive one.
export default function SourceDocViewer({
  source,
  providerLabel,
  refValue,
  name,
  onClose,
}: {
  source: string;
  providerLabel: string;
  refValue: string;
  name?: string;
  onClose: () => void;
}) {
  const [content, setContent] = useState<string | null>(null);
  const [title, setTitle] = useState(name ?? "");
  const [url, setUrl] = useState<string | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    setContent(null);
    setUrl(null);
    setError("");
    readSourceDoc(source, refValue)
      .then((doc) => {
        if (cancelled) return;
        setContent(doc.content ?? "");
        setUrl(doc.url ?? null);
        if (doc.name) setTitle(doc.name);
      })
      .catch((e) => {
        if (!cancelled) setError(e instanceof Error ? e.message : "Could not read document");
      });
    return () => {
      cancelled = true;
    };
  }, [source, refValue]);

  return (
    <div className="mt-3 overflow-hidden rounded-lg border border-border">
      <div className="flex items-center justify-between gap-2 border-b border-border bg-surface px-3 py-2.5">
        <div className="min-w-0 truncate font-mono text-[12.5px] font-semibold text-foreground">
          {title || refValue}
        </div>
        <div className="flex shrink-0 items-center gap-3">
          {url && (
            <a
              href={url}
              target="_blank"
              rel="noreferrer"
              className="text-[12px] font-semibold text-brand hover:underline"
            >
              Open in {providerLabel} ↗
            </a>
          )}
          <button type="button" onClick={onClose} className="cursor-pointer text-[12px] text-muted-foreground hover:text-foreground">
            Close
          </button>
        </div>
      </div>
      {error ? (
        <div className="bg-base px-3 py-3 text-[12px] text-error">{error}</div>
      ) : content === null ? (
        <div className="bg-base px-3 py-3 text-[12px] text-muted-foreground">Loading…</div>
      ) : (
        <pre className="scroll-thin max-h-96 overflow-auto whitespace-pre-wrap break-words bg-base px-3 py-3 font-mono text-[12px] text-foreground">
          {content}
        </pre>
      )}
    </div>
  );
}
