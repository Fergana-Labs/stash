"use client";

import { useCallback, useMemo, useState } from "react";

import CommentsRail from "./CommentsRail";
import HtmlEditWorkbench from "./HtmlEditWorkbench";
import MarkdownEditClient from "./MarkdownEditClient";
import { updatePaste } from "../actions";
import type { Paste, PasteComment } from "../_lib/paste";

// The edit page below the header: editor on the left, comments rail on
// the right (only once a comment exists — same as the read page), plus
// the switch controlling whether readers get the commenting surface.
// The editor always sees comments regardless of the switch.
export default function EditPageClient({
  paste,
  token,
  initialComments,
}: {
  paste: Paste;
  token: string;
  initialComments: PasteComment[];
}) {
  const [comments, setComments] = useState(initialComments);
  const [enabled, setEnabled] = useState(paste.comments_enabled);
  const [toggleError, setToggleError] = useState("");

  const addLocal = useCallback((comment: PasteComment) => {
    setComments((cur) => [...cur, comment]);
  }, []);

  const removeLocal = useCallback((id: string) => {
    setComments((cur) => cur.filter((c) => c.id !== id && c.parent_id !== id));
  }, []);

  const anchors = useMemo(
    () =>
      comments
        .filter((c) => c.quoted_text)
        .map((c) => ({ id: c.id, quoted: c.quoted_text })),
    [comments],
  );

  async function toggle(next: boolean) {
    setEnabled(next);
    setToggleError("");
    const result = await updatePaste(paste.slug, token, { comments_enabled: next });
    if (result.status === "error") {
      setEnabled(!next);
      setToggleError(result.message);
    }
  }

  const editor =
    paste.content_type === "html" ? (
      <HtmlEditWorkbench
        slug={paste.slug}
        token={token}
        title={paste.title}
        initialHtml={paste.content}
        onCommentAdded={addLocal}
        highlights={anchors}
      />
    ) : (
      <MarkdownEditClient
        slug={paste.slug}
        token={token}
        initialMarkdown={paste.content}
        onCommentAdded={addLocal}
      />
    );

  return (
    <div>
      <div className="flex items-center justify-end gap-3">
        {toggleError && <span className="text-[12.5px] text-red-600">{toggleError}</span>}
        <label className="flex cursor-pointer items-center gap-2 text-[12.5px] text-dim">
          <input
            type="checkbox"
            checked={enabled}
            onChange={(e) => toggle(e.target.checked)}
            className="h-3.5 w-3.5 accent-[var(--brand)]"
          />
          Allow reader comments
        </label>
      </div>

      {comments.length === 0 ? (
        <div className="mt-2">{editor}</div>
      ) : (
        <div className="mt-2 lg:grid lg:grid-cols-[minmax(0,1fr)_280px] lg:gap-7">
          <div className="min-w-0">{editor}</div>
          <aside className="mt-8 lg:mt-0">
            <div className="lg:sticky lg:top-6 lg:max-h-[calc(100vh-48px)] lg:overflow-y-auto">
              <CommentsRail
                slug={paste.slug}
                comments={comments}
                onCommentAdded={addLocal}
                onCommentDeleted={removeLocal}
                pageToken={token}
              />
            </div>
          </aside>
        </div>
      )}
    </div>
  );
}
