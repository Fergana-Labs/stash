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

const COLLAB_URL = process.env.NEXT_PUBLIC_COLLAB_URL || "ws://localhost:3458";

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
          collab={{ url: COLLAB_URL, room: `paste:${slug}`, token }}
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
