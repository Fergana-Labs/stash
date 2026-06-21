"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import type { Editor } from "@tiptap/react";

import CopyButton from "../../_components/CopyButton";
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

// The whole create flow on one card: type + visibility selectors, the
// rich editor (Tiptap for markdown; Code + WYSIWYG tabs for HTML), and
// Create page. Publishing always yields two URLs — public view link and
// private edit link. "Private" visibility is the signup gate, surfaced
// as a modal.
export default function PageComposer({ appUrl }: { appUrl: string }) {
  const router = useRouter();
  const [title, setTitle] = useState("");
  const [contentType, setContentType] = useState<PasteContentType>("markdown");
  const [visibility, setVisibility] = useState<PasteVisibility | "private">("public");
  const [privateModal, setPrivateModal] = useState(false);
  const [agentDocsUrl, setAgentDocsUrl] = useState("https://joinstash.ai/pages/agents");

  useEffect(() => {
    setAgentDocsUrl(`${window.location.origin}/pages/agents`);
  }, []);
  const [editor, setEditor] = useState<Editor | null>(null);
  const [htmlDraft, setHtmlDraft] = useState("");
  const [htmlTab, setHtmlTab] = useState<"code" | "edit">("code");
  // Remounts the WYSIWYG frame when re-entering it so it picks up code
  // edits; mutations inside the frame update the draft without remounts.
  const [htmlEditVersion, setHtmlEditVersion] = useState(0);
  const [publishing, setPublishing] = useState(false);
  const [error, setError] = useState("");
  const [published, setPublished] = useState<{
    slug: string;
    editToken: string;
    visibility: PasteVisibility;
  } | null>(null);
  const [, setEditTick] = useState(0);

  // The editor instance is destroyed while the published panel is up
  // (the composer unmounts it), so guard before touching it.
  const liveEditor = editor && !editor.isDestroyed ? editor : null;
  const content =
    contentType === "markdown" && liveEditor && !liveEditor.isEmpty
      ? serializeMarkdown(liveEditor.getJSON(), "")
      : htmlDraft;
  const canPublish = content.trim().length > 0 && !publishing;

  function openHtmlTab(tab: "code" | "edit") {
    if (tab === "edit") setHtmlEditVersion((v) => v + 1);
    setHtmlTab(tab);
  }

  async function publish() {
    if (!canPublish) return;
    // The signup gate: private pages only exist in the product.
    if (visibility === "private") {
      setPrivateModal(true);
      return;
    }
    setPublishing(true);
    setError("");
    const result = await createPaste({ title, content, content_type: contentType, visibility });
    setPublishing(false);
    if (result.status === "error") {
      setError(result.message);
      return;
    }
    setPublished({ slug: result.slug, editToken: result.edit_token, visibility });
    // The feed below is server-rendered; refresh so the new page shows
    // up in Recent without a manual reload.
    router.refresh();
  }

  // Publishing unmounts the editor (panel takes its place), so reset just
  // clears state — the editor remounts fresh and empty.
  function reset() {
    setPublished(null);
    setTitle("");
    setHtmlDraft("");
    setHtmlTab("code");
    setError("");
  }

  if (published) {
    return (
      <PublishedPanel
        slug={published.slug}
        editToken={published.editToken}
        visibility={published.visibility}
        onReset={reset}
      />
    );
  }

  return (
    <div className="rounded-xl border border-border bg-surface p-4">
      <div className="flex flex-wrap items-center gap-3">
        <input
          type="text"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          placeholder="Title (optional)"
          maxLength={200}
          className="h-9 min-w-0 flex-1 rounded-md border border-border bg-white px-3 text-[14px] text-ink placeholder:text-muted focus:border-brand focus:outline-none"
        />
        <Segmented
          options={[
            { value: "markdown", label: "MD" },
            { value: "html", label: "HTML" },
          ]}
          value={contentType}
          onChange={(v) => setContentType(v as PasteContentType)}
        />
        <Segmented
          options={[
            { value: "public", label: "Public" },
            { value: "unlisted", label: "Unlisted" },
            { value: "private", label: "Private" },
          ]}
          value={visibility}
          onChange={(v) => setVisibility(v as PasteVisibility | "private")}
        />
      </div>

      <div className="mt-3 overflow-hidden rounded-lg border border-border bg-white">
        {contentType === "markdown" ? (
          <div className="min-h-[300px]">
            <PasteMarkdownEditor
              initialMarkdown=""
              onSave={async () => {}}
              toolbarVisibility="when-focused"
              onEditor={(e) => {
                setEditor(e);
                e?.on("update", () => setEditTick((n) => n + 1));
              }}
            />
          </div>
        ) : (
          <div>
            <div className="flex items-center gap-1 border-b border-border-subtle px-2 py-1.5">
              {(["code", "edit"] as const).map((tab) => (
                <button
                  key={tab}
                  type="button"
                  onClick={() => openHtmlTab(tab)}
                  className={
                    "rounded px-2.5 py-1 text-[12.5px] font-medium transition " +
                    (htmlTab === tab
                      ? "bg-brand text-white shadow-sm"
                      : "text-dim hover:bg-brand/10 hover:text-brand-ink")
                  }
                >
                  {tab === "code" ? "Code" : "Edit visually"}
                </button>
              ))}
              {htmlTab === "edit" && (
                <span className="ml-2 text-[12.5px] text-muted">
                  Click into the page to edit text in place.
                </span>
              )}
            </div>
            {htmlTab === "code" ? (
              <textarea
                value={htmlDraft}
                onChange={(e) => setHtmlDraft(e.target.value)}
                spellCheck={false}
                placeholder={HTML_PLACEHOLDER}
                className="min-h-[300px] w-full resize-y bg-white p-3 font-mono text-[13px] leading-[1.5] text-ink placeholder:text-muted focus:outline-none"
              />
            ) : (
              <div className="min-h-[300px]">
                <HtmlFrame
                  key={htmlEditVersion}
                  html={htmlDraft}
                  title={title || "Draft"}
                  editable
                  onHtmlMutated={setHtmlDraft}
                />
              </div>
            )}
          </div>
        )}
      </div>

      <div className="mt-3 flex items-start justify-between gap-3">
        {error ? (
          <p className="text-[13px] text-red-600">{error}</p>
        ) : (
          <p className="text-[13px] text-muted">
            You&apos;ll get a public view link and a private edit link.
          </p>
        )}
        <button
          type="button"
          onClick={publish}
          disabled={!canPublish}
          className="inline-flex h-10 shrink-0 items-center rounded-md bg-brand px-5 text-[14px] font-medium text-white transition hover:bg-brand-hover disabled:cursor-not-allowed disabled:opacity-50"
        >
          {publishing ? "Publishing…" : "Create page"}
        </button>
      </div>

      <div className="-mx-4 -mb-4 mt-4 flex flex-wrap items-center justify-between gap-x-4 gap-y-2 rounded-b-xl border-t border-border bg-raised/70 px-4 py-3">
        <p className="text-[14px] text-foreground">
          <span className="font-medium text-ink">Have an agent do this instead</span>
          <span className="text-dim"> — copy the link and paste it to your agent. It explains everything.</span>
        </p>
        <div className="flex shrink-0 items-center gap-2">
          <CopyButton
            value={agentDocsUrl}
            label="Copy link"
            copiedLabel="Copied"
            className="inline-flex h-8 items-center rounded-md border border-border bg-white px-3 text-[13px] font-medium text-ink transition hover:bg-raised"
          />
          <Link
            href="/pages/agents"
            className="text-[13px] font-medium text-dim underline-offset-2 hover:text-ink hover:underline"
          >
            View →
          </Link>
        </div>
      </div>

      {privateModal && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-6"
          onClick={() => setPrivateModal(false)}
        >
          <div
            className="w-full max-w-[300px] rounded-xl border border-border bg-white p-5 shadow-xl"
            onClick={(e) => e.stopPropagation()}
          >
            <h3 className="font-display text-[18px] font-semibold text-ink">
              Private pages need an account
            </h3>
            <p className="mt-2 text-[14px] leading-relaxed text-dim">
              Private pages live in your Stash, with access controls and agent
              permissions. Pages published here are always reachable by link.
            </p>
            <div className="mt-5 flex items-center gap-3">
              <a
                href={appUrl}
                className="inline-flex h-10 items-center rounded-md bg-brand px-4 text-[14px] font-medium text-white transition hover:bg-brand-hover"
              >
                Start free →
              </a>
              <button
                type="button"
                onClick={() => setPrivateModal(false)}
                className="text-[14px] text-dim hover:text-ink"
              >
                Maybe later
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function Segmented({
  options,
  value,
  onChange,
}: {
  options: { value: string; label: string }[];
  value: string;
  onChange: (value: string) => void;
}) {
  return (
    <div className="inline-flex shrink-0 rounded-md border border-border bg-white p-0.5">
      {options.map((opt) => (
        <button
          key={opt.value}
          type="button"
          onClick={() => onChange(opt.value)}
          className={
            "rounded px-2.5 py-1 text-[12.5px] font-medium transition " +
            (value === opt.value
              ? "bg-brand text-white shadow-sm"
              : "text-dim hover:bg-brand/10 hover:text-brand-ink")
          }
        >
          {opt.label}
        </button>
      ))}
    </div>
  );
}
