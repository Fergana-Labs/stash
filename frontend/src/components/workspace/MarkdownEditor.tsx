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
import WikiLink from "./extensions/WikiLink";
import { NotebookPage, FileInfo } from "../../lib/types";
import { listFiles, WorkspacePageEntry } from "../../lib/api";

const AUTOSAVE_DEBOUNCE_MS = 1500;

export type SaveStatus = "saved" | "dirty" | "saving";

interface MarkdownEditorProps {
  workspaceId: string | null;
  notebookId: string | null;
  file: NotebookPage;
  onSave: (content: string) => void;
  onSaveStatusChange?: (status: SaveStatus) => void;
  onRename?: (name: string) => void;
  /** Every page in the workspace, used to seed `[[` autocomplete. */
  pageIndex?: WorkspacePageEntry[];
  /** Called on clicks to same-origin stash routes so the notebooks
   *  page can SPA-select the target instead of reloading. */
  onNavigateInternal?: (href: string) => void;
  /** Notebook name shown in the header breadcrumb. */
  notebookName?: string | null;
  /** Folder name shown between the notebook and the page title, if the
   *  page lives inside a folder. */
  folderName?: string | null;
}

export default function MarkdownEditor({
  workspaceId,
  notebookId,
  file,
  onSave,
  onSaveStatusChange,
  onRename,
  pageIndex = [],
  onNavigateInternal,
  notebookName,
  folderName,
}: MarkdownEditorProps) {
  const [dirty, setDirty] = useState(false);
  const [saving, setSaving] = useState(false);
  const saveTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const lastSaved = useRef<string>(file.content_markdown);

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
        HTMLAttributes: { class: "wiki-table" },
      }),
      TableRow,
      TableHeader,
      TableCell,
      WikiLink.configure({
        pageIndex,
        workspaceId: workspaceId ?? "",
        context: {
          notebookId: notebookId ?? null,
          folderId: file.folder_id ?? null,
        },
      }),
      Placeholder.configure({ placeholder: "Start typing..." }),
    ],
    editorProps: {
      attributes: {
        class: "max-w-none min-h-[200px] focus:outline-none wiki-body",
      },
      handleDOMEvents: {
        click: (_view, event) => {
          const target = event.target as HTMLElement | null;
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
            lastSaved.current = md;
            onSave(md);
          }
        }
      }
    };
  }, [editor, onSave]);

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
        lastSaved.current = md;
        onSave(md);
        setDirty(false);
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [editor, onSave]);

  const [title, setTitle] = useState(file.name);
  const titleTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const handleTitleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const newTitle = e.target.value;
    setTitle(newTitle);
    if (!onRename || !newTitle.trim()) return;
    if (titleTimer.current) clearTimeout(titleTimer.current);
    titleTimer.current = setTimeout(() => onRename(newTitle.trim()), AUTOSAVE_DEBOUNCE_MS);
  };

  const updatedLabel = file.updated_at
    ? `Updated ${new Date(file.updated_at).toLocaleDateString(undefined, {
        month: "short",
        day: "numeric",
        year: "numeric",
      })}`
    : "";

  return (
    <div className="flex h-full flex-col">
      <EditorToolbar editor={editor} workspaceId={workspaceId} />
      <div className="flex-1 overflow-y-auto bg-background">
        <div className="mx-auto w-full max-w-[820px] px-12 py-10">
          <header className="mb-8">
            {(notebookName || folderName) && (
              <nav className="mb-2 flex flex-wrap items-center gap-1.5 text-[12px] text-dim">
                {notebookName && <span>{notebookName}</span>}
                {notebookName && folderName && <span className="text-muted">/</span>}
                {folderName && <span>{folderName}</span>}
              </nav>
            )}
            {updatedLabel && (
              <p className="mb-2 font-mono text-[11px] font-medium uppercase tracking-[0.12em] text-muted">
                {updatedLabel}
              </p>
            )}
            <input
              type="text"
              value={title}
              onChange={handleTitleChange}
              placeholder="Untitled"
              className="w-full border-none bg-transparent font-display text-[40px] font-bold leading-[1.05] tracking-[-0.02em] text-foreground outline-none placeholder:text-muted/40"
            />
          </header>
          <EditorContent editor={editor} className="wiki-content" />
        </div>
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

function parseInlineMarkdown(text: string): JSONNode[] {
  // Inline grammar, ordered by priority:
  //   [[wiki link]]            — wiki node
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
      // Legacy `[[...]]` from old imports — pass through as plain text.
      // New content uses markdown links with id URLs instead.
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

function markdownToInitialJSON(markdown: string): JSONNode {
  if (!markdown || !markdown.trim()) {
    return { type: "doc", content: [{ type: "paragraph" }] };
  }

  const blocks = markdown.split(/\n{2,}/).map((b) => b.trim()).filter(Boolean);
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

function serializeMarkdown(doc: JSONNode | null | undefined, fallback: string): string {
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
  return marks.reduce((value, mark) => {
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
}
