"use client";

import { useEffect, useState } from "react";
import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";

import { DocumentBodySkeleton, SkeletonBlock } from "../SkeletonStates";

// Single source of truth for "show this file inline by content type."
// Used from the file viewer (/f/{fileId}) and from the skill detail page's
// SingleFilePreview, so both surfaces render PDFs, images, markdown, and
// plain text the same way. CSV stays out of scope — the file viewer
// redirects CSVs to /tables/{id}, and the skill viewer doesn't ingest.

interface Props {
  url: string;
  name: string;
  contentType: string;
  /** Layout for the markdown article. The file viewer wraps in
   *  a flex container with overflow-auto; the skill detail page sits
   *  inside a fixed-width column. Both want a centered article. */
  className?: string;
}

export function isPdf(ct: string) {
  return ct?.includes("pdf");
}
export function isImage(ct: string) {
  return ct?.startsWith("image/");
}
export function isMarkdown(ct: string, name: string) {
  return ct?.includes("markdown") || name.toLowerCase().endsWith(".md");
}
export function isText(ct: string) {
  return ct?.startsWith("text/");
}

export default function FileContentRenderer({ url, name, contentType, className }: Props) {
  const wantsText = isMarkdown(contentType, name) || isText(contentType);
  const [text, setText] = useState<string | null>(wantsText ? null : "");

  useEffect(() => {
    if (!wantsText || !url) return;
    let cancelled = false;
    (async () => {
      try {
        const res = await fetch(url);
        if (cancelled) return;
        if (res.ok) setText(await res.text());
        else setText("");
      } catch {
        if (!cancelled) setText("");
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [url, wantsText]);

  if (!url) {
    return <p className="px-5 py-8 text-muted">No download URL.</p>;
  }
  if (isPdf(contentType)) {
    return <iframe src={url} className={className ?? "h-[78vh] w-full bg-gray-200"} title={name} />;
  }
  if (isImage(contentType)) {
    return (
      <div className={className ?? "flex items-center justify-center bg-gray-100 p-8"}>
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src={url} alt={name} className="max-h-full max-w-full" />
      </div>
    );
  }
  if (isMarkdown(contentType, name)) {
    if (text === null) return <DocumentBodySkeleton className="mx-auto mt-8 max-w-[920px]" />;
    return (
      <article className="prose prose-sm markdown-content mx-auto max-w-[920px] px-6 py-6 text-foreground">
        <Markdown remarkPlugins={[remarkGfm]}>{text || ""}</Markdown>
      </article>
    );
  }
  if (isText(contentType)) {
    if (text === null) {
      return (
        <div className="space-y-2 px-5 py-4">
          {[0, 1, 2, 3, 4, 5, 6, 7].map((row) => (
            <SkeletonBlock key={row} className="h-4 w-full max-w-4xl" />
          ))}
        </div>
      );
    }
    return (
      <pre className="scroll-thin overflow-x-auto rounded-lg border border-border bg-base px-5 py-4 font-mono text-[12.5px] text-foreground">
        {text || ""}
      </pre>
    );
  }
  return (
    <div className="mx-auto max-w-md px-8 py-12 text-center text-[13px] text-muted">
      <p className="mb-3">No inline preview for this file type.</p>
      <a
        href={url}
        target="_blank"
        rel="noopener noreferrer"
        className="rounded-md bg-[var(--color-brand-600)] px-3 py-1.5 text-[12px] font-medium text-white hover:bg-[var(--color-brand-700)]"
      >
        Open original ↗
      </a>
    </div>
  );
}
