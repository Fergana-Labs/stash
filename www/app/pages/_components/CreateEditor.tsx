"use client";

import { useState } from "react";
import Link from "next/link";
import type { Editor } from "@tiptap/react";

import HtmlFrame from "./HtmlFrame";
import PasteMarkdownEditor from "./PasteMarkdownEditor";
import PublishedPanel from "./PublishedPanel";
import { createPaste, type PasteContentType, type PasteVisibility } from "../actions";
import { serializeMarkdown } from "../_lib/markdown";

const HTML_PLACEHOLDER = `<!doctype html>
<html>
  <body>
    <h1>Hello</h1>
  </body>
</html>`;

interface Props {
  contentType: PasteContentType;
  visibility: PasteVisibility;
  publicEdit: boolean;
}

// The create-flow editor: the same editing surfaces a published page has,
// but writing into a local draft until Publish. Markdown gets the Tiptap
// WYSIWYG; HTML gets Code | Preview.
export default function CreateEditor({ contentType, visibility, publicEdit }: Props) {
  const [title, setTitle] = useState("");
  const [editor, setEditor] = useState<Editor | null>(null);
  const [htmlCode, setHtmlCode] = useState("");
  const [htmlTab, setHtmlTab] = useState<"code" | "preview">("code");
  const [publishing, setPublishing] = useState(false);
  const [error, setError] = useState("");
  const [published, setPublished] = useState<{ slug: string; editToken: string } | null>(null);
  // Re-render on editor keystrokes so the Publish button's disabled state
  // tracks emptiness without serializing the doc on every input.
  const [, setEditTick] = useState(0);

  const content =
    contentType === "markdown" && editor && !editor.isEmpty
      ? serializeMarkdown(editor.getJSON(), "")
      : htmlCode;
  const canPublish = content.trim().length > 0 && !publishing;

  async function publish() {
    if (!canPublish) return;
    setPublishing(true);
    setError("");
    const result = await createPaste({
      title,
      content,
      content_type: contentType,
      visibility,
      public_edit: publicEdit,
    });
    setPublishing(false);
    if (result.status === "error") {
      setError(result.message);
      return;
    }
    setPublished({ slug: result.slug, editToken: result.edit_token });
  }

  if (published) {
    return (
      <div className="mx-auto max-w-[920px] px-6 py-10">
        <PublishedPanel
          slug={published.slug}
          editToken={published.editToken}
          visibility={visibility}
          publicEdit={publicEdit}
        />
      </div>
    );
  }

  return (
    <div className="flex min-h-screen flex-col">
      <header className="border-b border-border-subtle">
        <div className="mx-auto flex max-w-[1100px] flex-wrap items-center gap-x-4 gap-y-2 px-6 py-3">
          <Link href="/pages" className="shrink-0 font-mono text-[12px] text-muted hover:text-ink">
            ← stash pages
          </Link>
          <input
            type="text"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="Untitled page"
            maxLength={200}
            className="min-w-0 flex-1 bg-transparent text-[15px] font-medium text-ink placeholder:text-muted focus:outline-none"
          />
          <Badge>{contentType === "markdown" ? "MD" : "HTML"}</Badge>
          <Badge>{visibility}</Badge>
          {publicEdit && <Badge>anyone can edit</Badge>}
          {error && <span className="text-[13px] text-red-600">{error}</span>}
          <button
            type="button"
            onClick={publish}
            disabled={!canPublish}
            className="inline-flex h-9 shrink-0 items-center rounded-md bg-brand px-4 text-[14px] font-medium text-white transition hover:bg-brand-hover disabled:cursor-not-allowed disabled:opacity-50"
          >
            {publishing ? "Publishing…" : "Publish"}
          </button>
        </div>
      </header>

      {contentType === "markdown" ? (
        <div className="mx-auto w-full max-w-[1100px] flex-1 px-6 py-6">
          <div className="min-h-[60vh] rounded-xl border border-border bg-white">
            <PasteMarkdownEditor
              initialMarkdown=""
              onSave={async () => {}}
              onEditor={(e) => {
                setEditor(e);
                e?.on("update", () => setEditTick((n) => n + 1));
              }}
            />
          </div>
        </div>
      ) : (
        <div className="mx-auto w-full max-w-[1100px] flex-1 px-6 py-6">
          <div className="inline-flex rounded-md border border-border bg-white p-0.5">
            {(["code", "preview"] as const).map((tab) => (
              <button
                key={tab}
                type="button"
                onClick={() => setHtmlTab(tab)}
                className={
                  "rounded px-3 py-1 text-[13px] capitalize transition " +
                  (htmlTab === tab ? "bg-ink text-white" : "text-dim hover:text-ink")
                }
              >
                {tab}
              </button>
            ))}
          </div>
          <div className="mt-4 overflow-hidden rounded-xl border border-border bg-white">
            {htmlTab === "code" ? (
              <textarea
                value={htmlCode}
                onChange={(e) => setHtmlCode(e.target.value)}
                spellCheck={false}
                placeholder={HTML_PLACEHOLDER}
                className="min-h-[60vh] w-full resize-y bg-white p-4 font-mono text-[13px] leading-[1.5] text-ink placeholder:text-muted focus:outline-none"
              />
            ) : (
              <HtmlFrame key={htmlCode} html={htmlCode} title={title || "Preview"} />
            )}
          </div>
        </div>
      )}
    </div>
  );
}

function Badge({ children }: { children: React.ReactNode }) {
  return (
    <span className="inline-flex shrink-0 rounded border border-border bg-raised px-1.5 py-0.5 font-mono text-[10.5px] font-medium text-dim">
      {children}
    </span>
  );
}
