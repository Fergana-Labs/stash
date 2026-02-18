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
import Placeholder from "@tiptap/extension-placeholder";
import * as Y from "yjs";
import { WebsocketProvider } from "y-websocket";
import EditorToolbar from "./EditorToolbar";
import { WorkspaceFile } from "../../lib/types";

// User colors for collaboration cursors
const COLORS = [
  "#958DF1", "#F98181", "#FBBC88", "#FAF594",
  "#70CFF8", "#94FADB", "#B9F18D", "#C3A4F0",
];

function getRandomColor() {
  return COLORS[Math.floor(Math.random() * COLORS.length)];
}

interface MarkdownEditorProps {
  workspaceId: string;
  file: WorkspaceFile;
  onSave: (content: string) => void;
}

export default function MarkdownEditor({ workspaceId, file, onSave }: MarkdownEditorProps) {
  const [connected, setConnected] = useState(false);
  const [synced, setSynced] = useState(false);

  // Get auth token and user info
  const token = typeof window !== "undefined" ? localStorage.getItem("moltchat_token") : null;
  const userName = useMemo(() => {
    return "User";
  }, []);
  const userColor = useMemo(() => getRandomColor(), []);

  // Create Y.Doc and provider
  const [ydoc] = useState(() => new Y.Doc());
  const [provider, setProvider] = useState<WebsocketProvider | null>(null);

  useEffect(() => {
    if (!token) return;

    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const wsBase = `${protocol}//${window.location.host}`;

    const prov = new WebsocketProvider(
      `${wsBase}/api/v1/workspaces/${workspaceId}/files/${file.id}`,
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
  }, [token, workspaceId, file.id, ydoc, userName, userColor]);

  return (
    <div className="flex flex-col h-full">
      {/* File header */}
      <div className="flex items-center justify-between px-4 py-2 bg-gray-900 border-b border-gray-800">
        <div className="flex items-center gap-3">
          <span className="text-white text-sm font-medium">{file.name}</span>
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
        />
      ) : (
        <div className="flex-1 flex items-center justify-center bg-gray-950 text-gray-500">
          Connecting...
        </div>
      )}
    </div>
  );
}

function CollaborativeEditor({
  ydoc,
  onSave,
}: {
  ydoc: Y.Doc;
  onSave: (content: string) => void;
}) {
  const editor = useEditor({
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
          class: "text-blue-400 underline cursor-pointer",
        },
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

  // Keyboard shortcut: Ctrl+S to save
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "s") {
        e.preventDefault();
        if (editor) {
          onSave(editor.getText());
        }
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [editor, onSave]);

  return (
    <>
      <EditorToolbar editor={editor} />
      <div className="flex-1 overflow-y-auto bg-gray-950">
        <EditorContent editor={editor} className="h-full" />
      </div>
    </>
  );
}
