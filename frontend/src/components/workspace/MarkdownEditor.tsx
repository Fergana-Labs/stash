"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { EditorContent, useEditor } from "@tiptap/react";
import StarterKit from "@tiptap/starter-kit";
import Heading from "@tiptap/extension-heading";
import Bold from "@tiptap/extension-bold";
import Italic from "@tiptap/extension-italic";
import Link from "@tiptap/extension-link";
import Underline from "@tiptap/extension-underline";
import Subscript from "@tiptap/extension-subscript";
import Superscript from "@tiptap/extension-superscript";
import Typography from "@tiptap/extension-typography";
import Image from "@tiptap/extension-image";
import Placeholder from "@tiptap/extension-placeholder";
import { Table, TableCell, TableHeader, TableRow } from "@tiptap/extension-table";
import EditorToolbar from "./EditorToolbar";
import CommentMark from "./CommentMark";
import CommentComposerPopover from "./CommentComposerPopover";
import { Page, FileInfo } from "../../lib/types";
import { listFiles } from "../../lib/api";

const AUTOSAVE_DEBOUNCE_MS = 1500;
const ANCHOR_CONTEXT_CHARS = 32;

export type SaveStatus = "saved" | "dirty" | "saving";

export type AddCommentArgs = {
  quoted_text: string;
  prefix: string;
  suffix: string;
  body: string;
};

interface MarkdownEditorProps {
  workspaceId: string | null;
  file: Page;
  onSave: (content: string) => void;
  confirmSave?: () => boolean;
  onSaveStatusChange?: (status: SaveStatus) => void;
  /** Called on clicks to same-origin stash routes so the page
   *  can SPA-select the target instead of reloading. */
  onNavigateInternal?: (href: string) => void;
  /** Adds a comment thread anchored to the current selection. Resolves
   *  with the new thread id so we can paint the `comment` mark onto the
   *  range. If the host doesn't pass this prop the "Comment" button is
   *  hidden (e.g. read-only / public view). */
  onAddComment?: (args: AddCommentArgs) => Promise<string | null>;
  /** Click on an anchored span surfaces the thread in the sidebar. */
  onActivateThread?: (threadId: string) => void;
  /** Highlight the currently selected thread's anchor more strongly. */
  activeThreadId?: string | null;
}

export default function MarkdownEditor({
  workspaceId,
  file,
  onSave,
  confirmSave,
  onSaveStatusChange,
  onNavigateInternal,
  onAddComment,
  onActivateThread,
  activeThreadId,
}: MarkdownEditorProps) {
  const [dirty, setDirty] = useState(false);
  const [saving, setSaving] = useState(false);
  const saveTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const lastSaved = useRef<string>(file.content_markdown);
  const scrollContainerRef = useRef<HTMLDivElement | null>(null);
  const [commentPopover, setCommentPopover] = useState<{
    top: number;
    left: number;
  } | null>(null);
  // Holds the selection range alive while the composer is open — the
  // <textarea> taking focus changes the editor's selection, so we capture
  // the range up front and re-apply when we set the mark.
  const [composerState, setComposerState] = useState<{
    top: number;
    left: number;
    from: number;
    to: number;
    quoted_text: string;
    prefix: string;
    suffix: string;
  } | null>(null);

  // Resolved markdown — relative image refs like ![](a69cb715b010.jpg) get
  // rewritten to absolute signed URLs if a matching workspace file exists.
  // While the lookup is in-flight, show the raw markdown so the page never
  // flashes empty.
  const [resolvedMarkdown, setResolvedMarkdown] = useState<string>(file.content_markdown);

  useEffect(() => {
    let cancelled = false;
    setResolvedMarkdown(file.content_markdown);
    if (!workspaceId) return;
    const relativeNames = extractRelativeImageNames(file.content_markdown);
    if (relativeNames.size === 0) return;
    listFiles(workspaceId)
      .then((files) => {
        if (cancelled) return;
        const map = buildFileNameMap(files, relativeNames);
        if (map.size === 0) return;
        setResolvedMarkdown(rewriteRelativeImages(file.content_markdown, map));
      })
      .catch(() => {
        // Network flake is non-fatal — the raw markdown is still visible.
      });
    return () => {
      cancelled = true;
    };
  }, [workspaceId, file.content_markdown]);

  const initialContent = useMemo(
    () => markdownToInitialJSON(resolvedMarkdown),
    [resolvedMarkdown]
  );

  const editor = useEditor({
    immediatelyRender: false,
    content: initialContent,
    extensions: [
      StarterKit.configure({
        blockquote: false,
        codeBlock: false,
        heading: false,
        bold: false,
        italic: false,
        // StarterKit 3.x ships link + underline by default; we configure
        // those separately below, so disable the StarterKit copies to
        // avoid the "Duplicate extension names" warning + drift.
        link: false,
        underline: false,
      }),
      Heading.configure({ levels: [1, 2, 3] }),
      Bold,
      Italic,
      Underline,
      Subscript,
      Superscript,
      Typography,
      Link.configure({
        // We route clicks ourselves via editorProps.handleClickOn below
        // so internal stash URLs SPA-navigate instead of opening a new
        // tab, and relative/dead hrefs don't trigger 404s. Keep TipTap's
        // own click plugin disabled.
        openOnClick: false,
        autolink: true,
        HTMLAttributes: {
          // No class here — CSS classifies each anchor by href pattern
          // (see globals.css .ProseMirror a[...] rules) so internal,
          // external, and dead links style themselves consistently.
          rel: "noopener noreferrer",
        },
      }),
      Image.configure({
        HTMLAttributes: { class: "max-w-full rounded-md my-2" },
      }),
      Table.configure({
        resizable: false,
        HTMLAttributes: { class: "file-page-table" },
      }),
      TableRow,
      TableHeader,
      TableCell,
      Placeholder.configure({ placeholder: "Start typing..." }),
      CommentMark,
    ],
    editorProps: {
      attributes: {
        class: "max-w-none min-h-[200px] focus:outline-none file-page-body",
      },
      handleDOMEvents: {
        click: (_view, event) => {
          const target = event.target as HTMLElement | null;

          const commentEl = target?.closest?.("[data-comment-id]") as
            | HTMLElement
            | null;
          if (commentEl && onActivateThread) {
            const threadId = commentEl.getAttribute("data-comment-id");
            if (threadId) {
              event.preventDefault();
              onActivateThread(threadId);
              return true;
            }
          }

          const anchor = target?.closest?.("a");
          if (!anchor) return false;
          const href = anchor.getAttribute("href");
          if (!href) return false;

          const isStashAbsolute = /^https?:\/\/(app\.)?stash\.ac\//i.test(href);
          const isRouteRelative = href.startsWith("/");
          const hasScheme = /^[a-z][a-z0-9+.-]*:/i.test(href);

          if (isStashAbsolute || isRouteRelative) {
            event.preventDefault();
            onNavigateInternal?.(href);
            return true;
          }

          if (hasScheme) {
            event.preventDefault();
            window.open(href, "_blank", "noopener,noreferrer");
            return true;
          }

          // Relative href with no scheme and no leading slash — a stale
          // import artifact. Block it so the browser doesn't try to
          // resolve e.g. "README.md" against the current URL.
          event.preventDefault();
          return true;
        },
      },
    },
    onUpdate: ({ editor }) => {
      const md = serializeMarkdown(editor.getJSON(), lastSaved.current);
      if (md === lastSaved.current) return;
      setDirty(true);
      if (saveTimer.current) clearTimeout(saveTimer.current);
      saveTimer.current = setTimeout(() => {
        if (confirmSave && !confirmSave()) return;
        setSaving(true);
        lastSaved.current = md;
        onSave(md);
        setDirty(false);
        setSaving(false);
      }, AUTOSAVE_DEBOUNCE_MS);
    },
  });

  // When the resolved markdown changes (e.g. after file lookup completes),
  // replace the editor's content. We guard against unsaved user edits by
  // only replacing when the editor is still showing the original content.
  useEffect(() => {
    if (!editor) return;
    const currentMd = serializeMarkdown(editor.getJSON(), lastSaved.current);
    // Only reset if the editor's content still matches what we last loaded
    // (i.e. user hasn't typed anything since).
    if (currentMd !== lastSaved.current) return;
    editor.commands.setContent(initialContent);
    lastSaved.current = resolvedMarkdown;
  }, [editor, initialContent, resolvedMarkdown]);

  // Bubble save status to parent
  useEffect(() => {
    if (onSaveStatusChange) {
      onSaveStatusChange(saving ? "saving" : dirty ? "dirty" : "saved");
    }
  }, [saving, dirty, onSaveStatusChange]);

  // Flush pending save on unmount / page switch
  useEffect(() => {
    return () => {
      if (saveTimer.current) {
        clearTimeout(saveTimer.current);
        if (editor) {
          const md = serializeMarkdown(editor.getJSON(), lastSaved.current);
          if (md !== lastSaved.current) {
            if (confirmSave && !confirmSave()) return;
            lastSaved.current = md;
            onSave(md);
          }
        }
      }
    };
  }, [confirmSave, editor, onSave]);

  // Selection-anchored "Comment" popover. Mounted at the selection's
  // bottom-right, anchored to the scrolling container.
  useEffect(() => {
    if (!editor || !onAddComment) {
      setCommentPopover(null);
      return;
    }
    const update = () => {
      // Don't move the button while the composer is open — that would
      // make it look like a fresh selection cancelled the open thread.
      if (composerState) return;
      const { from, to, empty } = editor.state.selection;
      if (empty || from === to) {
        setCommentPopover(null);
        return;
      }
      const container = scrollContainerRef.current;
      if (!container) return;
      const coords = editor.view.coordsAtPos(to);
      const rect = container.getBoundingClientRect();
      setCommentPopover({
        top: coords.bottom - rect.top + container.scrollTop + 6,
        left: Math.min(
          coords.left - rect.left + container.scrollLeft,
          rect.width - 140,
        ),
      });
    };
    editor.on("selectionUpdate", update);
    editor.on("focus", update);
    return () => {
      editor.off("selectionUpdate", update);
      editor.off("focus", update);
    };
  }, [editor, onAddComment, composerState]);

  // Paint the active thread's anchor strongly. Toggles an `is-active`
  // class on the matching span(s) via direct DOM ops — the editor's
  // schema doesn't need to track presentation state.
  useEffect(() => {
    const container = scrollContainerRef.current;
    if (!container) return;
    const all = container.querySelectorAll<HTMLElement>("[data-comment-id]");
    all.forEach((el) => {
      el.classList.toggle(
        "is-active",
        !!activeThreadId && el.getAttribute("data-comment-id") === activeThreadId,
      );
    });
  }, [activeThreadId, resolvedMarkdown]);

  function openComposer() {
    if (!editor || !commentPopover) return;
    const { from, to, empty } = editor.state.selection;
    if (empty) return;
    const doc = editor.state.doc;
    const quoted = doc.textBetween(from, to, "\n", "\n");
    const prefixStart = Math.max(0, from - ANCHOR_CONTEXT_CHARS);
    const suffixEnd = Math.min(doc.content.size, to + ANCHOR_CONTEXT_CHARS);
    const prefix = doc.textBetween(prefixStart, from, "\n", "\n");
    const suffix = doc.textBetween(to, suffixEnd, "\n", "\n");
    setComposerState({
      top: commentPopover.top,
      left: commentPopover.left,
      from,
      to,
      quoted_text: quoted,
      prefix,
      suffix,
    });
    setCommentPopover(null);
  }

  async function submitComposer(body: string) {
    if (!editor || !onAddComment || !composerState) return;
    const threadId = await onAddComment({
      quoted_text: composerState.quoted_text,
      prefix: composerState.prefix,
      suffix: composerState.suffix,
      body,
    });
    if (!threadId) {
      setComposerState(null);
      return;
    }
    editor
      .chain()
      .focus()
      .setTextSelection({ from: composerState.from, to: composerState.to })
      .setMark("comment", { id: threadId })
      .setTextSelection(composerState.to)
      .run();
    setComposerState(null);
  }

  // Ctrl/Cmd+S → flush immediately
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "s") {
        e.preventDefault();
        if (!editor) return;
        if (saveTimer.current) {
          clearTimeout(saveTimer.current);
          saveTimer.current = null;
        }
        const md = serializeMarkdown(editor.getJSON(), lastSaved.current);
        if (confirmSave && !confirmSave()) return;
        lastSaved.current = md;
        onSave(md);
        setDirty(false);
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [confirmSave, editor, onSave]);

  return (
    <div className="flex h-full flex-col">
      <EditorToolbar editor={editor} workspaceId={workspaceId} />
      <div
        ref={scrollContainerRef}
        className="relative flex-1 overflow-y-auto bg-background"
      >
        <div className="mx-auto w-full max-w-[820px] px-12 py-10">
          <EditorContent editor={editor} className="file-page-content" />
        </div>
        {commentPopover && onAddComment && !composerState && (
          <button
            type="button"
            onMouseDown={(e) => {
              // Keep the editor selection alive across the click.
              e.preventDefault();
            }}
            onClick={openComposer}
            className="absolute z-30 rounded-md border border-border-subtle bg-raised px-3 py-1.5 text-sm font-medium text-foreground shadow-md hover:bg-raised-2"
            style={{ top: commentPopover.top, left: commentPopover.left }}
          >
            Comment
          </button>
        )}
        {composerState && onAddComment && (
          <CommentComposerPopover
            top={composerState.top}
            left={composerState.left}
            onCancel={() => setComposerState(null)}
            onSubmit={submitComposer}
          />
        )}
      </div>
    </div>
  );
}

type JSONNode = {
  type?: string;
  text?: string;
  marks?: Array<{ type: string; attrs?: Record<string, string> }>;
  attrs?: Record<string, unknown>;
  content?: JSONNode[];
};

function isAbsoluteUrl(url: string): boolean {
  // Only resolve remote images; relative paths like `a69cb715b010.jpg`
  // point at files we never uploaded into the page's storage and would 404.
  return /^https?:\/\//i.test(url);
}

const COMMENT_SPAN_RE = /<span\s+data-comment-id="([^"]+)">([\s\S]*?)<\/span>/g;

function parseInlineMarkdown(text: string): JSONNode[] {
  // Pre-pass: extract `<span data-comment-id="…">…</span>` wrappers (the
  // round-trip form of the `comment` mark) BEFORE the inline regex runs,
  // recurse on their inner content, then tag the resulting text nodes
  // with the `comment` mark. The inner content keeps its bold/italic/
  // link/etc. marks because parseInlineMarkdownInner handles them.
  const out: JSONNode[] = [];
  let lastIndex = 0;
  let m: RegExpExecArray | null;
  COMMENT_SPAN_RE.lastIndex = 0;
  while ((m = COMMENT_SPAN_RE.exec(text)) !== null) {
    if (m.index > lastIndex) {
      out.push(...parseInlineMarkdownInner(text.slice(lastIndex, m.index)));
    }
    const id = m[1];
    const innerNodes = parseInlineMarkdownInner(m[2]);
    for (const node of innerNodes) {
      if (node.type === "text") {
        node.marks = [
          ...(node.marks || []),
          { type: "comment", attrs: { id } },
        ];
      }
    }
    out.push(...innerNodes);
    lastIndex = m.index + m[0].length;
  }
  if (lastIndex < text.length) {
    out.push(...parseInlineMarkdownInner(text.slice(lastIndex)));
  }
  return out.length > 0 ? out : [{ type: "text", text }];
}

function parseInlineMarkdownInner(text: string): JSONNode[] {
  // Inline grammar, ordered by priority:
  //   [[bracketed text]]       — plain text
  //   [![alt](src)](href)      — image inside a link (matched before plain image
  //                              so the outer brackets don't swallow the image)
  //   ![alt](src)              — image node (absolute URLs only)
  //   [text](url)              — link mark
  //   **bold**                 — bold mark
  //   *italic*                 — italic mark
  //   `code`                   — code mark
  const inlinePattern =
    /(\[\[([^\]]+)\]\]|\[!\[([^\]]*)\]\(([^)]+)\)\]\(([^)]+)\)|!\[([^\]]*)\]\(([^)]+)\)|\[([^\]]+)\]\(([^)]+)\)|\*\*(.+?)\*\*|\*(.+?)\*|`([^`]+)`)/g;
  const nodes: JSONNode[] = [];
  let lastIndex = 0;
  let match: RegExpExecArray | null;

  while ((match = inlinePattern.exec(text)) !== null) {
    if (match.index > lastIndex) {
      nodes.push({ type: "text", text: text.slice(lastIndex, match.index) });
    }

    if (match[2] !== undefined) {
      // The filesystem has no bracket-link syntax; bracket refs stay plain.
      nodes.push({ type: "text", text: match[0] });
    } else if (match[3] !== undefined) {
      // [![alt](src)](href) — linked image. Render as the image (TipTap's
      // inline nodes can't nest a link around an image cleanly without the
      // ProseMirror schema also allowing it). The href is preserved as the
      // image's alt/title so it isn't silently dropped.
      const alt = match[3];
      const src = match[4];
      const href = match[5];
      if (isAbsoluteUrl(src)) {
        nodes.push({ type: "image", attrs: { src, alt, title: href } });
      } else {
        nodes.push({ type: "text", text: match[0] });
      }
    } else if (match[6] !== undefined) {
      // ![alt](src)
      const alt = match[6];
      const src = match[7];
      if (isAbsoluteUrl(src)) {
        nodes.push({ type: "image", attrs: { src, alt } });
      } else {
        // Keep the raw markdown visible so it isn't silently lost.
        nodes.push({ type: "text", text: match[0] });
      }
    } else if (match[8] !== undefined) {
      // [text](url)
      nodes.push({
        type: "text",
        text: match[8],
        marks: [{ type: "link", attrs: { href: match[9] } }],
      });
    } else if (match[10] !== undefined) {
      // **bold**
      nodes.push({ type: "text", text: match[10], marks: [{ type: "bold" }] });
    } else if (match[11] !== undefined) {
      // *italic*
      nodes.push({ type: "text", text: match[11], marks: [{ type: "italic" }] });
    } else if (match[12] !== undefined) {
      // `code`
      nodes.push({ type: "text", text: match[12], marks: [{ type: "code" }] });
    }

    lastIndex = match.index + match[0].length;
  }

  if (lastIndex < text.length) {
    nodes.push({ type: "text", text: text.slice(lastIndex) });
  }

  return nodes.length > 0 ? nodes : [{ type: "text", text }];
}

export function markdownToInitialJSON(markdown: string): JSONNode {
  if (!markdown || !markdown.trim()) {
    return { type: "doc", content: [{ type: "paragraph" }] };
  }

  // Heading lines often appear without a leading or trailing blank line in
  // agent-authored markdown. Force a paragraph break both BEFORE and AFTER
  // every ATX heading so block-splitting puts each heading on its own block.
  const normalized = markdown
    .replace(/(?<!\n\n)(\n)(#{1,6}[ \t]+)/g, "\n\n$2")
    .replace(/(^|\n\n)(#{1,6}[ \t]+[^\n]+)\n(?!\n)/g, "$1$2\n\n");
  const blocks = normalized.split(/\n{2,}/).map((b) => b.trim()).filter(Boolean);
  const nodes: JSONNode[] = blocks.map((block) => {
    const headingMatch = block.match(/^(#{1,3})\s+(.+)$/);
    if (headingMatch) {
      return {
        type: "heading",
        attrs: { level: headingMatch[1].length },
        content: parseInlineMarkdown(headingMatch[2]),
      };
    }

    const tableNode = parseTableBlock(block);
    if (tableNode) return tableNode;

    const listNode = parseListBlock(block);
    if (listNode) return listNode;

    return {
      type: "paragraph",
      content: parseInlineMarkdown(block),
    };
  });
  return { type: "doc", content: nodes };
}

// --- Lists ---

const BULLET_RE = /^([-*+])\s+(.*)$/;
const ORDERED_RE = /^\d+\.\s+(.*)$/;

function parseListBlock(block: string): JSONNode | null {
  const lines = block.split("\n");
  const first = lines[0];
  const isBullet = BULLET_RE.test(first);
  const isOrdered = ORDERED_RE.test(first);
  if (!isBullet && !isOrdered) return null;

  const items: JSONNode[] = [];
  for (const line of lines) {
    const m = isBullet ? line.match(BULLET_RE) : line.match(ORDERED_RE);
    if (!m) {
      // Not a list line — fold into the previous item's text if one exists.
      if (items.length > 0) {
        const last = items[items.length - 1];
        const para = last.content?.[0];
        if (para && para.type === "paragraph") {
          para.content = [
            ...(para.content || []),
            { type: "text", text: " " + line.trim() },
          ];
        }
      }
      continue;
    }
    const body = isBullet ? m[2] : m[1];
    items.push({
      type: "listItem",
      content: [
        {
          type: "paragraph",
          content: parseInlineMarkdown(body),
        },
      ],
    });
  }
  return {
    type: isBullet ? "bulletList" : "orderedList",
    content: items,
  };
}

// --- Tables (GitHub-flavored pipe tables) ---

const TABLE_SEPARATOR_RE = /^\|?\s*:?-+:?\s*(\|\s*:?-+:?\s*)+\|?$/;

function splitPipeRow(line: string): string[] {
  // Trim leading/trailing pipe and split on unescaped |.
  const trimmed = line.replace(/^\s*\|/, "").replace(/\|\s*$/, "");
  return trimmed.split(/(?<!\\)\|/).map((c) => c.trim().replace(/\\\|/g, "|"));
}

function parseTableBlock(block: string): JSONNode | null {
  const lines = block.split("\n");
  if (lines.length < 2) return null;
  if (!lines[0].includes("|")) return null;
  if (!TABLE_SEPARATOR_RE.test(lines[1].trim())) return null;

  const headerCells = splitPipeRow(lines[0]);
  const bodyLines = lines.slice(2);

  const headerRow: JSONNode = {
    type: "tableRow",
    content: headerCells.map((cell) => ({
      type: "tableHeader",
      content: [{ type: "paragraph", content: parseInlineMarkdown(cell) }],
    })),
  };

  const bodyRows: JSONNode[] = bodyLines
    .filter((l) => l.trim())
    .map((line) => {
      const cells = splitPipeRow(line);
      // Normalise cell count to header width.
      while (cells.length < headerCells.length) cells.push("");
      cells.length = headerCells.length;
      return {
        type: "tableRow",
        content: cells.map((cell) => ({
          type: "tableCell",
          content: [{ type: "paragraph", content: parseInlineMarkdown(cell) }],
        })),
      };
    });

  return { type: "table", content: [headerRow, ...bodyRows] };
}

// --- Relative image resolution ---

function extractRelativeImageNames(markdown: string): Set<string> {
  const names = new Set<string>();
  const re = /!\[[^\]]*\]\(([^)]+)\)/g;
  let m: RegExpExecArray | null;
  while ((m = re.exec(markdown)) !== null) {
    const src = m[1].trim();
    if (/^https?:\/\//i.test(src) || src.startsWith("/") || src.startsWith("data:")) continue;
    // Strip any fragment / querystring — storage keys are filename-only.
    const cleaned = src.split(/[?#]/)[0];
    if (cleaned) names.add(cleaned);
  }
  return names;
}

function buildFileNameMap(files: FileInfo[], wanted: Set<string>): Map<string, string> {
  const map = new Map<string, string>();
  const byName = new Map<string, string>();
  for (const f of files) byName.set(f.name, f.url);
  for (const want of wanted) {
    const url = byName.get(want) ?? byName.get(want.split("/").pop() || want);
    if (url) map.set(want, url);
  }
  return map;
}

function rewriteRelativeImages(markdown: string, urls: Map<string, string>): string {
  return markdown.replace(/(!\[[^\]]*\]\()([^)]+)(\))/g, (full, pre, src, post) => {
    const trimmed = src.trim();
    const cleaned = trimmed.split(/[?#]/)[0];
    const url = urls.get(cleaned);
    return url ? `${pre}${url}${post}` : full;
  });
}

export function serializeMarkdown(doc: JSONNode | null | undefined, fallback: string): string {
  if (!doc || !doc.content) return fallback;
  return doc.content.map((node) => renderNode(node, 0)).join("").trim() || fallback;
}

function renderNode(node: JSONNode, depth: number): string {
  const children = (node.content || []).map((child) => renderNode(child, depth + 1)).join("");
  switch (node.type) {
    case "paragraph":
      return `${children}\n\n`;
    case "heading": {
      const level = Number(node.attrs?.level || 1);
      return `${"#".repeat(Math.min(Math.max(level, 1), 6))} ${children.trim()}\n\n`;
    }
    case "bulletList":
      return `${(node.content || []).map((child) => renderNode(child, depth)).join("")}\n`;
    case "orderedList":
      return `${(node.content || []).map((child, index) => renderListItem(child, depth, index + 1)).join("")}\n`;
    case "listItem":
      return renderListItem(node, depth, null);
    case "blockquote":
      return `${children.trim().split("\n").map((line) => `> ${line}`).join("\n")}\n\n`;
    case "hardBreak":
      return "\n";
    case "image": {
      const src = String(node.attrs?.src || "");
      const alt = String(node.attrs?.alt || "");
      const title = node.attrs?.title ? String(node.attrs.title) : "";
      return title ? `[![${alt}](${src})](${title})` : `![${alt}](${src})`;
    }
    case "table":
      return renderTable(node);
    case "text":
      return applyMarks(node.text || "", node.marks || []);
    default:
      return children;
  }
}

function renderTable(node: JSONNode): string {
  const rows = node.content || [];
  if (rows.length === 0) return "";
  // Each row has tableHeader/tableCell children, each of which contains a
  // paragraph whose text is what we want to serialize.
  const cellsFor = (row: JSONNode): string[] =>
    (row.content || []).map((cell) => {
      const para = (cell.content || [])[0];
      const inline = (para?.content || [])
        .map((child) => renderNode(child, 0))
        .join("")
        .trim();
      return inline.replace(/\|/g, "\\|");
    });

  const headerCells = cellsFor(rows[0]);
  const colCount = headerCells.length;
  const separator = new Array(colCount).fill("---");
  const bodyRows = rows.slice(1).map(cellsFor);
  const toLine = (cells: string[]) => `| ${cells.join(" | ")} |`;
  return [
    toLine(headerCells),
    toLine(separator),
    ...bodyRows.map(toLine),
  ].join("\n") + "\n\n";
}

function renderListItem(node: JSONNode, depth: number, index: number | null): string {
  const prefix = index === null ? `${"  ".repeat(depth)}- ` : `${"  ".repeat(depth)}${index}. `;
  const text = (node.content || []).map((child) => renderNode(child, depth + 1)).join("").trimEnd();
  const lines = text.split("\n");
  return `${prefix}${lines[0] || ""}${lines.slice(1).map((line) => `\n${"  ".repeat(depth + 1)}${line}`).join("")}\n`;
}

function applyMarks(text: string, marks: Array<{ type: string; attrs?: Record<string, string> }>): string {
  // The `comment` mark must be the outermost wrapper so the round-trip
  // produces `<span data-comment-id>**bold**</span>`, not
  // `**<span>bold</span>**` (which would break our parser).
  const commentMark = marks.find((m) => m.type === "comment");
  const others = marks.filter((m) => m.type !== "comment");
  const inner = others.reduce((value, mark) => {
    switch (mark.type) {
      case "bold":
        return `**${value}**`;
      case "italic":
        return `*${value}*`;
      case "underline":
        return `<u>${value}</u>`;
      case "subscript":
        return `<sub>${value}</sub>`;
      case "superscript":
        return `<sup>${value}</sup>`;
      case "link":
        return `[${value}](${mark.attrs?.href || ""})`;
      case "code":
        return `\`${value}\``;
      default:
        return value;
    }
  }, text);
  const id = commentMark?.attrs?.id;
  if (id) return `<span data-comment-id="${id}">${inner}</span>`;
  return inner;
}

// Extract every `data-comment-id` value present in the saved content.
// Used by the page route to reconcile orphans after each save.
export function extractCommentIdsFromMarkdown(markdown: string): string[] {
  const ids: string[] = [];
  const re = /<span\s+data-comment-id="([^"]+)"/g;
  let m: RegExpExecArray | null;
  while ((m = re.exec(markdown)) !== null) ids.push(m[1]);
  return Array.from(new Set(ids));
}
