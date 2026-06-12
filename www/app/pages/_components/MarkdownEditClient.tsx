"use client";

import { useState } from "react";

import PasteMarkdownEditor, { type SaveStatus } from "./PasteMarkdownEditor";
import { updatePaste } from "../actions";

interface Props {
  slug: string;
  token: string;
  initialMarkdown: string;
}

const STATUS_LABELS: Record<SaveStatus, string> = {
  saved: "Saved",
  dirty: "Unsaved changes",
  saving: "Saving…",
};

export default function MarkdownEditClient({ slug, token, initialMarkdown }: Props) {
  const [status, setStatus] = useState<SaveStatus>("saved");
  const [error, setError] = useState("");

  async function save(markdown: string) {
    const result = await updatePaste(slug, token, markdown);
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
      <div className="mt-2">
        <PasteMarkdownEditor
          initialMarkdown={initialMarkdown}
          onSave={save}
          onSaveStatusChange={setStatus}
        />
      </div>
    </div>
  );
}
