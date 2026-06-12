"use client";

import { useState } from "react";

import CopyButton from "../../_components/CopyButton";
import { createPaste, type PasteContentType } from "../actions";

const HTML_START_RE = /^\s*(<!doctype|<html)/i;

const PLACEHOLDERS: Record<PasteContentType, string> = {
  markdown: "# My page\n\nPaste or write markdown here…",
  html: "<!doctype html>\n<html>\n  <body>\n    <h1>Hello</h1>\n  </body>\n</html>",
};

// Paste-first create flow: raw textarea + type toggle (auto-detected from
// the pasted content), then Publish. On success this swaps to the
// shown-once panel with the view/edit/raw URLs — the edit URL is the only
// time the edit token is ever displayed.
export default function PasteComposer() {
  const [title, setTitle] = useState("");
  const [content, setContent] = useState("");
  const [contentType, setContentType] = useState<PasteContentType>("markdown");
  const [typeTouched, setTypeTouched] = useState(false);
  const [publishing, setPublishing] = useState(false);
  const [error, setError] = useState("");
  const [published, setPublished] = useState<{ slug: string; editToken: string } | null>(null);

  function onContentChange(next: string) {
    setContent(next);
    if (!typeTouched) setContentType(HTML_START_RE.test(next) ? "html" : "markdown");
  }

  async function publish() {
    if (!content.trim() || publishing) return;
    setPublishing(true);
    setError("");
    const result = await createPaste({ title, content, content_type: contentType });
    setPublishing(false);
    if (result.status === "error") {
      setError(result.message);
      return;
    }
    setPublished({ slug: result.slug, editToken: result.edit_token });
  }

  if (published) {
    const origin = window.location.origin;
    const viewUrl = `${origin}/pages/${published.slug}`;
    const editUrl = `${viewUrl}/edit?token=${published.editToken}`;
    const rawUrl = `${viewUrl}/raw`;
    return (
      <div className="rounded-xl border border-border bg-surface p-6">
        <h2 className="font-display text-[20px] font-semibold text-ink">Your page is live.</h2>
        <p className="mt-1 text-[14px] text-dim">
          It&apos;s public — anyone with the link can see it.
        </p>
        <div className="mt-5 space-y-3">
          <UrlRow label="View" url={viewUrl} />
          <UrlRow label="Edit" url={editUrl} />
          <UrlRow label="Raw" url={rawUrl} />
        </div>
        <p className="mt-3 text-[13px] font-medium text-brand-ink">
          Save the edit link — it&apos;s the only way to edit this page and it won&apos;t be
          shown again.
        </p>
        <div className="mt-5 flex items-center gap-4">
          <a
            href={viewUrl}
            className="inline-flex h-10 items-center rounded-md bg-brand px-4 text-[14px] font-medium text-white transition hover:bg-brand-hover"
          >
            View your page →
          </a>
          <button
            type="button"
            onClick={() => {
              setPublished(null);
              setTitle("");
              setContent("");
              setTypeTouched(false);
              setContentType("markdown");
            }}
            className="text-[14px] text-dim hover:text-ink"
          >
            Publish another
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="rounded-xl border border-border bg-surface p-4 sm:p-6">
      <div className="flex flex-wrap items-center gap-3">
        <input
          type="text"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          placeholder="Title (optional)"
          maxLength={200}
          className="h-9 min-w-0 flex-1 rounded-md border border-border bg-white px-3 text-[14px] text-ink placeholder:text-muted focus:border-brand focus:outline-none"
        />
        <div className="inline-flex rounded-md border border-border bg-white p-0.5">
          {(["markdown", "html"] as const).map((type) => (
            <button
              key={type}
              type="button"
              onClick={() => {
                setContentType(type);
                setTypeTouched(true);
              }}
              className={
                "rounded px-3 py-1 font-mono text-[12px] transition " +
                (contentType === type
                  ? "bg-ink text-white"
                  : "text-dim hover:text-ink")
              }
            >
              {type === "markdown" ? "MD" : "HTML"}
            </button>
          ))}
        </div>
      </div>
      <textarea
        value={content}
        onChange={(e) => onContentChange(e.target.value)}
        spellCheck={false}
        placeholder={PLACEHOLDERS[contentType]}
        className="mt-3 min-h-[320px] w-full resize-y rounded-md border border-border bg-white p-3 font-mono text-[13px] leading-[1.5] text-ink placeholder:text-muted focus:border-brand focus:outline-none"
      />
      {error && <p className="mt-2 text-[13px] text-red-600">{error}</p>}
      <div className="mt-3 flex items-center justify-between gap-3">
        <p className="text-[13px] text-muted">
          Public, permanent, no signup. You&apos;ll get a secret edit link.
        </p>
        <button
          type="button"
          onClick={publish}
          disabled={!content.trim() || publishing}
          className="inline-flex h-10 items-center rounded-md bg-brand px-5 text-[14px] font-medium text-white transition hover:bg-brand-hover disabled:cursor-not-allowed disabled:opacity-50"
        >
          {publishing ? "Publishing…" : "Publish"}
        </button>
      </div>
    </div>
  );
}

function UrlRow({ label, url }: { label: string; url: string }) {
  return (
    <div className="flex items-center gap-3">
      <span className="w-10 shrink-0 font-mono text-[12px] text-muted">{label}</span>
      <input
        type="text"
        readOnly
        value={url}
        onFocus={(e) => e.target.select()}
        className="h-9 min-w-0 flex-1 rounded-md border border-border bg-white px-3 font-mono text-[12px] text-ink"
      />
      <CopyButton
        value={url}
        className="inline-flex h-9 shrink-0 items-center rounded-md border border-border bg-white px-3 text-[13px] font-medium text-ink transition hover:bg-raised"
      />
    </div>
  );
}
