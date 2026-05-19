import { Mark, mergeAttributes } from "@tiptap/core";

// Anchors a comment thread to a range of text. Renders as
// `<span data-comment-id="…" class="comment-anchor">…</span>` so it
// round-trips as inline HTML through our custom markdown serializer (see
// MarkdownEditor.applyMarks / parseInlineMarkdown).
//
// - `inclusive: false` — typing at the right edge does NOT extend the mark,
//   matching Google Docs' behavior.
// - `excludes: ""` — coexists with bold/italic/link/etc.
export const CommentMark = Mark.create<{ HTMLAttributes: Record<string, unknown> }>(
  {
    name: "comment",
    inclusive: false,
    excludes: "",
    addAttributes() {
      return {
        id: {
          default: null,
          parseHTML: (el) => el.getAttribute("data-comment-id"),
          renderHTML: (attrs) => ({ "data-comment-id": attrs.id }),
        },
      };
    },
    parseHTML() {
      return [{ tag: "span[data-comment-id]" }];
    },
    renderHTML({ HTMLAttributes }) {
      return [
        "span",
        mergeAttributes(HTMLAttributes, { class: "comment-anchor" }),
        0,
      ];
    },
  },
);

export default CommentMark;
