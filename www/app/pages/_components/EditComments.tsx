"use client";

import { useState } from "react";

import CommentsRail from "./CommentsRail";
import { addComment, updatePaste } from "../actions";
import type { PasteComment } from "../_lib/paste";

// The edit page's comments rail: always visible to the editor, with the
// switch that controls whether readers see comments in view mode.
export default function EditComments({
  slug,
  token,
  initialComments,
  initialEnabled,
}: {
  slug: string;
  token: string;
  initialComments: PasteComment[];
  initialEnabled: boolean;
}) {
  const [comments, setComments] = useState(initialComments);
  const [enabled, setEnabled] = useState(initialEnabled);
  const [toggleError, setToggleError] = useState("");

  async function submit(input: { author_name: string; body: string }) {
    const result = await addComment(slug, {
      author_name: input.author_name,
      body: input.body,
      quoted_text: "",
      prefix: "",
      suffix: "",
    });
    if (result.status === "error") return result.message;
    setComments((cur) => [...cur, result.comment as PasteComment]);
    return "";
  }

  async function toggle(next: boolean) {
    setEnabled(next);
    setToggleError("");
    const result = await updatePaste(slug, token, { comments_enabled: next });
    if (result.status === "error") {
      setEnabled(!next);
      setToggleError(result.message);
    }
  }

  return (
    <CommentsRail
      comments={comments}
      onSubmit={submit}
      headerExtra={
        <div className="mt-2">
          <label className="flex cursor-pointer items-center gap-2 text-[12.5px] text-dim">
            <input
              type="checkbox"
              checked={enabled}
              onChange={(e) => toggle(e.target.checked)}
              className="h-3.5 w-3.5 accent-[var(--brand)]"
            />
            Show comments to readers
          </label>
          {toggleError && <p className="mt-1 text-[12px] text-red-600">{toggleError}</p>}
        </div>
      }
    />
  );
}
