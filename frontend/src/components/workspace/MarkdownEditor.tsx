"use client";

import { useEffect, useMemo, useState } from "react";
import { EditorContent, useEditor } from "@tiptap/react";
import StarterKit from "@tiptap/starter-kit";
import Collaboration from "@tiptap/extension-collaboration";
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
import * as Y from "yjs";
import { WebsocketProvider } from "y-websocket";
import EditorToolbar from "./EditorToolbar";
import WikiLink, { WikiLinkNode } from "./extensions/WikiLink";
import { NotebookPage } from "../../lib/types";
import { getToken, getWsBase } from "../../lib/api";

// User colors for collaboration cursors
const COLORS = [
  "#958DF1", "#F98181", "#FBBC88", "#FAF594",
  "#70CFF8", "#94FADB", "#B9F18D", "#C3A4F0",
];

function getRandomColor() {
  return COLORS[Math.floor(Math.random() * COLORS.length)];
}

interface MarkdownEditorProps {
  workspaceId: string | null;
  notebookId: string | null;
  file: NotebookPage;
  onSave: (content: string) => void;
  pageNames?: string[];
  onNavigateToPage?: (pageName: string) => void;
}

export default function MarkdownEditor({ workspaceId, notebookId, file, onSave, pageNames = [], onNavigateToPage }: MarkdownEditorProps) {
  const [connected, setConnected] = useState(false);
  const [synced, setSynced] = useState(false);

  // Get auth token and user info
  const token = typeof window !== "undefined" ? getToken() : null;
  const userName = useMemo(() => {
    return "User";
  }, []);
  const userColor = useMemo(() => getRandomColor(), []);

  // Create Y.Doc and provider
  const [ydoc] = useState(() => new Y.Doc());
  const [provider, setProvider] = useState<WebsocketProvider | null>(null);

  useEffect(() => {
    if (!token) return;

    const wsBase = getWsBase();

    const wsPath = workspaceId && notebookId
      ? `/api/v1/workspaces/${workspaceId}/notebooks/${notebookId}/pages/${file.id}`
      : notebookId
        ? `/api/v1/notebooks/${notebookId}/pages/${file.id}`
        : `/api/v1/notebooks/unknown/pages/${file.id}`;
    const prov = new WebsocketProvider(
      `${wsBase}${wsPath}`,
      "yjs",
      ydoc,
      {
        connect: true,
        params: { token },
      }
    );

    prov.on("status", ({ status }: { status: string }) => {
      setConnected(status === "connected");
    });

    prov.on("sync", (isSynced: boolean) => {
      setSynced(isSynced);
    });

    prov.awareness.setLocalStateField("user", {
      name: userName,
      color: userColor,
    });

    setProvider(prov);

    return () => {
      prov.disconnect();
      prov.destroy();
      setProvider(null);
      setConnected(false);
      setSynced(false);
    };
  }, [token, workspaceId, notebookId, file.id, ydoc, userName, userColor]);

  return (
    <div className="flex flex-col h-full">
      {/* File header */}
      <div className="flex items-center justify-between px-4 py-2 bg-surface border-b border-border">
        <div className="flex items-center gap-3">
          <span className="text-foreground text-sm font-medium">{file.name}</span>
          <span
            className={`w-2 h-2 rounded-full ${
              connected ? "bg-green-400" : "bg-yellow-400"
            }`}
            title={connected ? (synced ? "Connected & synced" : "Connected, syncing...") : "Disconnected"}
          />
        </div>
      </div>

      {provider ? (
        <CollaborativeEditor
          ydoc={ydoc}
          onSave={onSave}
          initialMarkdown={file.content_markdown}
          workspaceId={workspaceId}
          pageNames={pageNames}
          onNavigateToPage={onNavigateToPage}
        />
      ) : (
        <div className="flex-1 flex items-center justify-center bg-background text-muted">
          Connecting...
        </div>
      )}
    </div>
  );
}

function CollaborativeEditor({
  ydoc,
  onSave,
  initialMarkdown,
  workspaceId,
  pageNames,
  onNavigateToPage,
}: {
  ydoc: Y.Doc;
  onSave: (content: string) => void;
  initialMarkdown: string;
  workspaceId: string | null;
  pageNames: string[];
  onNavigateToPage?: (pageName: string) => void;
}) {
  const editor = useEditor({
    immediatelyRender: false,
    extensions: [
      // Match collab server's createTiptapExtensions() exactly
      StarterKit.configure({
        blockquote: false,
        codeBlock: false,
        heading: false,
        bold: false,
        italic: false,
        undoRedo: false, // Disable undo/redo when using YJS collaboration
      }),
      Heading.configure({
        levels: [1, 2, 3],
      }),
      Bold,
      Italic,
      Underline,
      Subscript,
      Superscript,
      Typography,
      Link.configure({
        openOnClick: false,
        HTMLAttributes: {
          class: "text-brand underline cursor-pointer",
        },
      }),
      Image.configure({
        HTMLAttributes: {
          class: "max-w-full rounded-md my-2",
        },
      }),
      WikiLinkNode,
      WikiLink.configure({
        pageNames,
      }),
      Placeholder.configure({
        placeholder: "Start typing...",
      }),
      Collaboration.configure({
        document: ydoc,
      }),
    ],
    editorProps: {
      attributes: {
        class: "max-w-none px-6 py-4 min-h-full focus:outline-none",
      },
    },
  });

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

  // Keyboard shortcut: Ctrl+S to save
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "s") {
        e.preventDefault();
        if (editor) {
          onSave(serializeMarkdown(editor.getJSON(), initialMarkdown));
        }
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [editor, initialMarkdown, onSave]);

  return (
    <>
      <EditorToolbar editor={editor} workspaceId={workspaceId} />
      <div className="flex-1 overflow-y-auto bg-background">
        <EditorContent editor={editor} className="h-full" />
      </div>
    </>
  );
}

type JSONNode = {
  type?: string;
  text?: string;
  marks?: Array<{ type: string; attrs?: Record<string, string> }>;
  attrs?: Record<string, unknown>;
  content?: JSONNode[];
};

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
