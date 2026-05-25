"use client";

import { useCallback, useEffect, useRef, type MouseEvent } from "react";
import { EditorContent, useEditor } from "@tiptap/react";
import StarterKit from "@tiptap/starter-kit";
import Heading from "@tiptap/extension-heading";
import Bold from "@tiptap/extension-bold";
import Italic from "@tiptap/extension-italic";
import TiptapLink from "@tiptap/extension-link";
import Underline from "@tiptap/extension-underline";
import Subscript from "@tiptap/extension-subscript";
import Superscript from "@tiptap/extension-superscript";
import Typography from "@tiptap/extension-typography";
import Image from "@tiptap/extension-image";
import Placeholder from "@tiptap/extension-placeholder";
import { Table, TableCell, TableHeader, TableRow } from "@tiptap/extension-table";
import { shouldFocusEditorFrame } from "../lib/editorClick";
import EditorToolbar from "./workspace/EditorToolbar";

const AUTOSAVE_MS = 1500;

type DescriptionEditorProps = {
  value: string;
  canEdit: boolean;
  placeholder: string;
  ariaLabel: string;
  onSave: (html: string) => Promise<void> | void;
  /** Workspace ID for inline image uploads from the toolbar. */
  workspaceId?: string | null;
};

export function isBlankDescription(value: string): boolean {
  return value.trim() === "" || value.trim() === "<p></p>";
}

export default function DescriptionEditor({
  value,
  canEdit,
  placeholder,
  ariaLabel,
  onSave,
  workspaceId,
}: DescriptionEditorProps) {
  const canEditRef = useRef(canEdit);
  const lastSaved = useRef(value);
  const onSaveRef = useRef(onSave);
  const pendingHtml = useRef<string | null>(null);
  const saveTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    canEditRef.current = canEdit;
  }, [canEdit]);

  useEffect(() => {
    onSaveRef.current = onSave;
  }, [onSave]);

  const flushPendingSave = useCallback(async () => {
    if (saveTimer.current) {
      clearTimeout(saveTimer.current);
      saveTimer.current = null;
    }

    const html = pendingHtml.current;
    pendingHtml.current = null;
    if (html === null || html === lastSaved.current) return;

    lastSaved.current = html;
    await onSaveRef.current(html);
  }, []);

  const queueSave = useCallback(
    (html: string) => {
      pendingHtml.current = html;
      if (saveTimer.current) clearTimeout(saveTimer.current);
      saveTimer.current = setTimeout(() => {
        void flushPendingSave();
      }, AUTOSAVE_MS);
    },
    [flushPendingSave]
  );

  const editor = useEditor({
    immediatelyRender: false,
    editable: canEdit,
    content: value || "<p></p>",
    extensions: [
      // Inline editor uses the same surface as the page editor — same
      // toolbar, same supported blocks (lists, quote, code, hr, table).
      // Heading/Bold/Italic/Link/Underline are configured separately so
      // disable the StarterKit copies.
      StarterKit.configure({
        heading: false,
        bold: false,
        italic: false,
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
      Image,
      Table.configure({
        resizable: true,
        HTMLAttributes: { class: "file-page-table" },
      }),
      TableRow,
      TableHeader,
      TableCell,
      TiptapLink.configure({
        openOnClick: false,
        autolink: true,
        HTMLAttributes: { rel: "noopener noreferrer" },
      }),
      Placeholder.configure({ placeholder }),
    ],
    editorProps: {
      attributes: {
        "aria-label": ariaLabel,
        class:
          "prose prose-sm max-w-none description-editor-content focus:outline-none file-page-body",
      },
      handleDOMEvents: {
        blur: () => {
          void flushPendingSave();
          return false;
        },
        click: (_view, event) => {
          const target = event.target as HTMLElement | null;
          const anchor = target?.closest?.("a");
          if (!anchor) return false;

          const href = anchor.getAttribute("href");
          if (!href) return false;

          const shouldOpen = !canEditRef.current || event.metaKey || event.ctrlKey;
          if (!shouldOpen) return false;

          event.preventDefault();
          openHref(href);
          return true;
        },
      },
    },
    onUpdate: ({ editor: ed }) => {
      // Read-only viewers (public-stash anonymous readers, workspace
      // viewers without write access) still mount the editor so they
      // can see the rendered description, but must never hit the
      // authenticated save endpoint. TipTap's mount-time normalization
      // emits onUpdate even when nobody touched the content, so this
      // gate is load-bearing.
      if (!canEditRef.current) return;
      const html = ed.isEmpty ? "" : ed.getHTML();
      if (html === lastSaved.current) return;
      queueSave(html);
    },
  });

  useEffect(() => {
    if (!editor) return;
    editor.setEditable(canEdit);
  }, [canEdit, editor]);

  useEffect(() => {
    lastSaved.current = value;
    if (!editor || pendingHtml.current !== null) return;

    const html = editor.isEmpty ? "" : editor.getHTML();
    if (html === value) return;

    editor.commands.setContent(value || "<p></p>", { emitUpdate: false });
  }, [editor, value]);

  useEffect(() => {
    return () => {
      void flushPendingSave();
    };
  }, [flushPendingSave]);

  function handleEditorFrameClick(event: MouseEvent<HTMLDivElement>) {
    if (!editor) return;
    if (!canEdit) return;
    if (!shouldFocusEditorFrame(editor.view.dom, event.target)) return;

    editor.commands.focus();
  }

  return (
    <div
      data-editable={canEdit ? "true" : "false"}
      onClick={handleEditorFrameClick}
      className={
        "description-editor -mx-1 px-1 py-0.5 " + (canEdit ? "cursor-text" : "")
      }
    >
      <EditorContent editor={editor} />
      {canEdit && (
        <EditorToolbar
          editor={editor}
          workspaceId={workspaceId ?? null}
          visibility="when-focused"
        />
      )}
    </div>
  );
}

function openHref(href: string) {
  const hasScheme = /^[a-z][a-z0-9+.-]*:/i.test(href);
  if (href.startsWith("/")) {
    window.location.href = href;
    return;
  }
  if (hasScheme) {
    window.open(href, "_blank", "noopener,noreferrer");
    return;
  }
  window.open(`https://${href}`, "_blank", "noopener,noreferrer");
}
