"use client";

import { useEffect, useRef } from "react";
import { EditorContent, useEditor, type Editor } from "@tiptap/react";
import StarterKit from "@tiptap/starter-kit";
import Link from "@tiptap/extension-link";
import Underline from "@tiptap/extension-underline";
import Subscript from "@tiptap/extension-subscript";
import Superscript from "@tiptap/extension-superscript";
import Typography from "@tiptap/extension-typography";
import Image from "@tiptap/extension-image";
import Placeholder from "@tiptap/extension-placeholder";
import { Table, TableCell, TableHeader, TableRow } from "@tiptap/extension-table";

import EditorToolbar from "./EditorToolbar";
import { markdownToInitialJSON, serializeMarkdown } from "../_lib/markdown";

const AUTOSAVE_DEBOUNCE_MS = 1500;

export type SaveStatus = "saved" | "dirty" | "saving";

interface Props {
  initialMarkdown: string;
  /** Persists the markdown. Throw to signal failure — the editor keeps
   *  the content marked dirty so the next change retries the save. */
  onSave: (markdown: string) => Promise<void>;
  onSaveStatusChange?: (status: SaveStatus) => void;
  /** Hands the Tiptap instance to the parent — the create flow uses it
   *  to serialize the doc on Publish instead of waiting for autosave. */
  onEditor?: (editor: Editor | null) => void;
}

// The product app's MarkdownEditor (Tiptap) without the workspace-only
// machinery: no Yjs/Hocuspocus collaboration (content loads once from
// parsed markdown), no comment anchors, no file uploads. Same 1500ms
// debounced autosave and markdown round-trip.
export default function PasteMarkdownEditor({
  initialMarkdown,
  onSave,
  onSaveStatusChange,
  onEditor,
}: Props) {
  const saveTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const lastSaved = useRef(initialMarkdown);
  const saveMarkdownRef = useRef<(md: string) => void>(() => {});

  const editor = useEditor({
    immediatelyRender: false,
    extensions: [
      StarterKit.configure({
        codeBlock: false,
        heading: { levels: [1, 2, 3] },
        // StarterKit 3.x ships link + underline by default; we configure
        // those separately below, so disable the StarterKit copies to
        // avoid the "Duplicate extension names" warning + drift.
        link: false,
        underline: false,
      }),
      Underline,
      Subscript,
      Superscript,
      Typography,
      Link.configure({
        openOnClick: false,
        autolink: true,
        HTMLAttributes: { rel: "noopener noreferrer" },
      }),
      Image.configure({
        HTMLAttributes: { class: "max-w-full rounded-md my-2" },
      }),
      Table.configure({
        resizable: false,
      }),
      TableRow,
      TableHeader,
      TableCell,
      Placeholder.configure({ placeholder: "Start typing..." }),
    ],
    content: markdownToInitialJSON(initialMarkdown),
    editorProps: {
      attributes: {
        class:
          "prose prose-sm max-w-none min-h-full px-8 pt-8 pb-32 focus:outline-none file-page-body cursor-text",
        spellcheck: "false",
      },
    },
    onUpdate: ({ editor }) => {
      const md = serializeMarkdown(editor.getJSON(), lastSaved.current);
      if (md === lastSaved.current) return;
      onSaveStatusChange?.("dirty");
      if (saveTimer.current) clearTimeout(saveTimer.current);
      saveTimer.current = setTimeout(() => {
        saveTimer.current = null;
        saveMarkdownRef.current(md);
      }, AUTOSAVE_DEBOUNCE_MS);
    },
  });

  useEffect(() => {
    onEditor?.(editor);
  }, [editor, onEditor]);

  useEffect(() => {
    saveMarkdownRef.current = (md: string) => {
      void (async () => {
        onSaveStatusChange?.("saving");
        try {
          await onSave(md);
        } catch {
          onSaveStatusChange?.("dirty");
          return;
        }
        lastSaved.current = md;
        // If the doc changed during the save (user kept typing), the next
        // debounce flushes — only report "saved" when what we saved is
        // still what's on screen.
        const currentMd = editor ? serializeMarkdown(editor.getJSON(), md) : md;
        onSaveStatusChange?.(currentMd === md ? "saved" : "dirty");
      })();
    };
  }, [editor, onSave, onSaveStatusChange]);

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
        if (md !== lastSaved.current) saveMarkdownRef.current(md);
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [editor]);

  // Flush pending save on unmount.
  useEffect(() => {
    return () => {
      if (saveTimer.current) {
        clearTimeout(saveTimer.current);
        if (editor) {
          const md = serializeMarkdown(editor.getJSON(), lastSaved.current);
          if (md !== lastSaved.current) saveMarkdownRef.current(md);
        }
      }
    };
  }, [editor]);

  return (
    <div className="flex h-full flex-col">
      <EditorToolbar editor={editor} />
      <div className="relative flex-1 overflow-y-auto">
        <div className="mx-auto min-h-full w-full max-w-[920px]">
          <EditorContent editor={editor} className="min-h-full" />
        </div>
      </div>
    </div>
  );
}
