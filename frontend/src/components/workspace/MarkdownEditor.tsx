"use client";

import { useEffect, useRef, useState } from "react";
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
import EditorToolbar from "./EditorToolbar";
import WikiLink, { WikiLinkNode } from "./extensions/WikiLink";
import { NotebookPage } from "../../lib/types";

const AUTOSAVE_DEBOUNCE_MS = 1500;

export type SaveStatus = "saved" | "dirty" | "saving";

interface MarkdownEditorProps {
  workspaceId: string | null;
  notebookId: string | null;
  file: NotebookPage;
  onSave: (content: string) => void;
  onSaveStatusChange?: (status: SaveStatus) => void;
  onRename?: (name: string) => void;
  pageNames?: string[];
  onNavigateToPage?: (pageName: string) => void;
}

export default function MarkdownEditor({ workspaceId, file, onSave, onSaveStatusChange, onRename, pageNames = [], onNavigateToPage }: MarkdownEditorProps) {
  const [dirty, setDirty] = useState(false);
  const [saving, setSaving] = useState(false);
  const saveTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const lastSaved = useRef<string>(file.content_markdown);

  const editor = useEditor({
    immediatelyRender: false,
    content: markdownToInitialJSON(file.content_markdown),
    extensions: [
      StarterKit.configure({
        blockquote: false,
        codeBlock: false,
        heading: false,
        bold: false,
        italic: false,
      }),
      Heading.configure({ levels: [1, 2, 3] }),
      Bold,
      Italic,
      Underline,
      Subscript,
      Superscript,
      Typography,
      Link.configure({
        openOnClick: false,
        HTMLAttributes: { class: "text-brand underline cursor-pointer" },
      }),
      Image.configure({
        HTMLAttributes: { class: "max-w-full rounded-md my-2" },
      }),
      WikiLinkNode,
      WikiLink.configure({ pageNames }),
      Placeholder.configure({ placeholder: "Start typing..." }),
    ],
    editorProps: {
      attributes: {
        class: "max-w-none min-h-[200px] focus:outline-none wiki-body",
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

  // Wiki link click handler
  useEffect(() => {
    const handleWikiLinkClick = (e: Event) => {
      const detail = (e as CustomEvent).detail;
      if (detail?.pageName && onNavigateToPage) {
        onNavigateToPage(detail.pageName);
      }
    };
    document.addEventListener("wiki-link-click", handleWikiLinkClick);
    return () => document.removeEventListener("wiki-link-click", handleWikiLinkClick);
  }, [onNavigateToPage]);

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

  return (
    <div className="flex flex-col h-full">
      <EditorToolbar editor={editor} workspaceId={workspaceId} />
      <div className="flex-1 overflow-y-auto bg-background">
        <div className="max-w-[720px] mx-auto w-full px-8 py-10">
          <input
            type="text"
            value={title}
            onChange={handleTitleChange}
            placeholder="Untitled"
            className="w-full text-3xl font-bold text-foreground bg-transparent border-none outline-none placeholder:text-muted/40 mb-1 font-display"
          />
          <div className="text-[11px] text-muted mb-6">
            {file.updated_at ? `Last edited ${new Date(file.updated_at).toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" })}` : ""}
          </div>
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
      // [[wiki link]]
      nodes.push({ type: "wikiLinkNode", attrs: { pageName: match[2] } });
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
    return {
      type: "paragraph",
      content: parseInlineMarkdown(block),
    };
  });
  return { type: "doc", content: nodes };
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
    case "wikiLinkNode": {
      const pageName = node.attrs?.pageName || "";
      return `[[${pageName}]]`;
    }
    case "image": {
      const src = String(node.attrs?.src || "");
      const alt = String(node.attrs?.alt || "");
      const title = node.attrs?.title ? String(node.attrs.title) : "";
      return title ? `[![${alt}](${src})](${title})` : `![${alt}](${src})`;
    }
    case "text":
      return applyMarks(node.text || "", node.marks || []);
    default:
      return children;
  }
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
