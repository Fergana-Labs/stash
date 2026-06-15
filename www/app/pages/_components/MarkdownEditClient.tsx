"use client";

import { useRef, useState } from "react";

import PasteMarkdownEditor, { type SaveStatus } from "./PasteMarkdownEditor";
import SelectionCommentLayer from "./SelectionCommentLayer";
import { updatePaste } from "../actions";
import type { PasteComment } from "../_lib/paste";

interface Props {
  slug: string;
  token: string;
  initialMarkdown: string;
  onCommentAdded: (comment: PasteComment) => void;
}

// Live collab needs an explicitly configured server. Without one (e.g.
// prod before the env is set) the editor must run in plain autosave mode
// — binding Collaboration to a provider that never connects would source
// content from an empty Y.Doc and the page would render blank.
const COLLAB_URL =
  process.env.NEXT_PUBLIC_COLLAB_URL ||
  (process.env.NODE_ENV === "development" ? "ws://localhost:3458" : "");

const STATUS_LABELS: Record<SaveStatus, string> = {
  saved: "Saved",
  dirty: "Unsaved changes",
  saving: "Saving…",
};

export default function MarkdownEditClient({
  slug,
  token,
  initialMarkdown,
  onCommentAdded,
}: Props) {
  const wrapRef = useRef<HTMLDivElement | null>(null);
  const [status, setStatus] = useState<SaveStatus>("saved");
  const [error, setError] = useState("");

  async function save(markdown: string) {
    const result = await updatePaste(slug, token, { content: markdown });
    if (result.status === "error") {
      setError(result.message);
      throw new Error(result.message);
    }
    setError("");
  }

  return (
    <div>
      <div className="flex items-center justify-end gap-3">
        {error && <span className="text-[13px] text-red-600">{error}</span>}
        <span className="text-[13px] text-muted">{STATUS_LABELS[status]}</span>
      </div>
      <div ref={wrapRef} className="relative mt-2">
        <PasteMarkdownEditor
          initialMarkdown={initialMarkdown}
          onSave={save}
          onSaveStatusChange={setStatus}
          collab={COLLAB_URL ? { url: COLLAB_URL, room: `paste:${slug}`, token } : undefined}
        />
        <SelectionCommentLayer
          slug={slug}
          wrapRef={wrapRef}
          listenDom
          onCommentAdded={onCommentAdded}
        />
      </div>
    </div>
  );
}
