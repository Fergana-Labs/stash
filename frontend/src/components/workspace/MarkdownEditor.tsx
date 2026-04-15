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

interface MarkdownEditorProps {
  workspaceId: string | null;
  notebookId: string | null;
  file: NotebookPage;
  onSave: (content: string) => void;
  pageNames?: string[];
  onNavigateToPage?: (pageName: string) => void;
}

export default function MarkdownEditor({ workspaceId, file, onSave, pageNames = [], onNavigateToPage }: MarkdownEditorProps) {
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
        class: "max-w-none px-6 py-4 min-h-full focus:outline-none",
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

  const statusLabel = saving ? "Saving..." : dirty ? "Unsaved changes" : "Saved";
  const statusColor = saving || dirty ? "bg-yellow-400" : "bg-green-400";

  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center justify-between px-4 py-2 bg-surface border-b border-border">
        <div className="flex items-center gap-3">
          <span className="text-foreground text-sm font-medium">{file.name}</span>
          <span
            className={`w-2 h-2 rounded-full ${statusColor}`}
            title={statusLabel}
          />
        </div>
      </div>
      <EditorToolbar editor={editor} workspaceId={workspaceId} />
      <div className="flex-1 overflow-y-auto bg-background">
        <EditorContent editor={editor} className="h-full" />
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

function parseInlineMarkdown(text: string): JSONNode[] {
  // Parse inline markdown (bold, italic, wiki links) into TipTap nodes/marks.
  // Regex matches: [[wiki links]], **bold**, *italic*
  const inlinePattern = /(\[\[([^\]]+)\]\]|\*\*(.+?)\*\*|\*(.+?)\*)/g;
  const nodes: JSONNode[] = [];
  let lastIndex = 0;
  let match: RegExpExecArray | null;

  while ((match = inlinePattern.exec(text)) !== null) {
    // Push plain text before this match
    if (match.index > lastIndex) {
      nodes.push({ type: "text", text: text.slice(lastIndex, match.index) });
    }

    if (match[2] !== undefined) {
      // [[wiki link]]
      nodes.push({ type: "wikiLinkNode", attrs: { pageName: match[2] } });
    } else if (match[3] !== undefined) {
      // **bold**
      nodes.push({ type: "text", text: match[3], marks: [{ type: "bold" }] });
    } else if (match[4] !== undefined) {
      // *italic*
      nodes.push({ type: "text", text: match[4], marks: [{ type: "italic" }] });
    }

    lastIndex = match.index + match[0].length;
  }

  // Push remaining plain text
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
      default:
        return value;
    }
  }, text);
}
