"use client";

import { useEffect, useState } from "react";

import CopyButton from "../../_components/CopyButton";
import HtmlFrame from "./HtmlFrame";
import { updatePaste } from "../actions";

type Mode = "view" | "edit" | "raw";

interface Props {
  slug: string;
  token: string;
  title: string;
  initialHtml: string;
}

// The HTML edit page's three-mode selector. View renders the page, Edit is
// the app's contenteditable-iframe pattern (in-place text edits, saved on
// each debounced mutation), Raw is the full source for structural changes
// (scripts/styles) that contenteditable can't reach.
export default function HtmlEditWorkbench({ slug, token, title, initialHtml }: Props) {
  const [mode, setMode] = useState<Mode>("edit");
  const [html, setHtml] = useState(initialHtml);
  // Remount key for the frames: bumped on raw saves so View/Edit pick up
  // the new source. Edit-mode mutations must NOT bump it — the editable
  // iframe is the source of truth and a remount would trash the caret.
  const [version, setVersion] = useState(0);
  const [draft, setDraft] = useState(initialHtml);
  const [status, setStatus] = useState("");
  const [error, setError] = useState("");
  const [origin, setOrigin] = useState("");

  useEffect(() => {
    setOrigin(window.location.origin);
  }, []);

  async function save(nextHtml: string) {
    setStatus("Saving…");
    setError("");
    const result = await updatePaste(slug, token, nextHtml);
    if (result.status === "error") {
      setStatus("");
      setError(result.message);
      return false;
    }
    setStatus("Saved");
    return true;
  }

  function onMutated(nextHtml: string) {
    setHtml(nextHtml);
    setDraft(nextHtml);
    void save(nextHtml);
  }

  async function saveRaw() {
    const ok = await save(draft);
    if (!ok) return;
    setHtml(draft);
    setVersion((v) => v + 1);
  }

  return (
    <div>
      <div className="flex flex-wrap items-center gap-3">
        <div className="inline-flex rounded-md border border-border bg-white p-0.5">
          {(["view", "edit", "raw"] as const).map((m) => (
            <button
              key={m}
              type="button"
              onClick={() => setMode(m)}
              className={
                "rounded px-3 py-1 text-[13px] capitalize transition " +
                (mode === m ? "bg-ink text-white" : "text-dim hover:text-ink")
              }
            >
              {m}
            </button>
          ))}
        </div>
        {mode === "edit" && (
          <span className="text-[13px] text-muted">Click into the page to edit text in place.</span>
        )}
        <span className="ml-auto text-[13px] text-muted">{status}</span>
      </div>
      {error && <p className="mt-2 text-[13px] text-red-600">{error}</p>}

      <div className="mt-4 overflow-hidden rounded-xl border border-border bg-white">
        {mode === "view" && <HtmlFrame key={`view-${version}`} html={html} title={title} />}
        {mode === "edit" && (
          <HtmlFrame
            key={`edit-${version}`}
            html={html}
            title={title}
            editable
            onHtmlMutated={onMutated}
          />
        )}
        {mode === "raw" && (
          <div className="p-4">
            <textarea
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              spellCheck={false}
              className="min-h-[480px] w-full resize-y rounded-md border border-border bg-white p-3 font-mono text-[13px] leading-[1.5] text-ink focus:border-brand focus:outline-none"
            />
            <div className="mt-3 flex items-center justify-between gap-3">
              <div className="min-w-0 font-mono text-[12px] text-muted">
                Agents can edit too:{" "}
                <code className="break-all">
                  curl -X PATCH &quot;{origin}/pages/{slug}?token=…&quot; --data-binary @page.html
                </code>
              </div>
              <div className="flex shrink-0 items-center gap-2">
                <CopyButton
                  value={draft}
                  label="Copy source"
                  className="inline-flex h-9 items-center rounded-md border border-border bg-white px-3 text-[13px] font-medium text-ink transition hover:bg-raised"
                />
                <button
                  type="button"
                  onClick={saveRaw}
                  disabled={draft === html}
                  className="inline-flex h-9 items-center rounded-md bg-brand px-4 text-[13px] font-medium text-white transition hover:bg-brand-hover disabled:cursor-not-allowed disabled:opacity-50"
                >
                  Save
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
