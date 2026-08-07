"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";

import { Page } from "../../lib/types";
import { uploadFile, fileDownloadUrl } from "../../lib/api";

const AUTOSAVE_DEBOUNCE_MS = 1500;

export type SaveStatus = "saved" | "dirty" | "saving";

interface MarkdownEditorProps {
  file: Page;
  onSave: (content: string) => void | Promise<void>;
  /** A save was refused because the page changed elsewhere (409). Shown as a
   *  banner; editing freezes until the parent reloads the page. */
  conflictMessage?: string | null;
  confirmSave?: () => boolean;
  onSaveStatusChange?: (status: SaveStatus) => void;
}

/** The markdown editor edits markdown.
 *
 *  It used to be a rich-text editor: every open converted the file into a
 *  visual document and every save converted it back. Anything that document
 *  had no block for was flattened on the way through — fenced code blocks
 *  came back as inline spans with their line breaks stripped (turning two
 *  shell commands into one unrunnable string), blockquotes lost their
 *  markers, and a frontmatter block turned into a heading. 193 pages in
 *  production carry code fences, 99 of them SKILL.md files, and one keystroke
 *  anywhere in the document was enough to rewrite the lot.
 *
 *  So there is no conversion now. The textarea holds the file's bytes, the
 *  preview renders a copy for looking at, and a save writes back exactly what
 *  is in the box. Nothing can be lost in a round trip that does not happen. */
export default function MarkdownEditor({
  file,
  onSave,
  conflictMessage,
  confirmSave,
  onSaveStatusChange,
}: MarkdownEditorProps) {
  const [value, setValue] = useState(file.content_markdown);
  const [dirty, setDirty] = useState(false);
  const [saving, setSaving] = useState(false);
  const [showPreview, setShowPreview] = useState(false);
  const saveTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const lastSaved = useRef(file.content_markdown);
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);
  const readOnly = !file.can_write || !!conflictMessage;

  // Load the file when the page changes. Keyed on id, not content: a save
  // echo must not yank the buffer out from under the cursor.
  useEffect(() => {
    setValue(file.content_markdown);
    lastSaved.current = file.content_markdown;
    setDirty(false);
    setSaving(false);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [file.id]);

  useEffect(() => {
    onSaveStatusChange?.(saving ? "saving" : dirty ? "dirty" : "saved");
  }, [saving, dirty, onSaveStatusChange]);

  const save = useCallback(
    async (next: string) => {
      if (readOnly || (confirmSave && !confirmSave())) return;
      setSaving(true);
      try {
        await onSave(next);
        lastSaved.current = next;
        setDirty(false);
      } finally {
        setSaving(false);
      }
    },
    [confirmSave, onSave, readOnly]
  );

  const saveRef = useRef(save);
  useEffect(() => {
    saveRef.current = save;
  }, [save]);

  function onChange(next: string) {
    setValue(next);
    setDirty(next !== lastSaved.current);
    if (saveTimer.current) clearTimeout(saveTimer.current);
    saveTimer.current = setTimeout(() => {
      saveTimer.current = null;
      if (next !== lastSaved.current) void saveRef.current(next);
    }, AUTOSAVE_DEBOUNCE_MS);
  }

  // Flush a pending save when leaving the page.
  useEffect(() => {
    return () => {
      if (!saveTimer.current) return;
      clearTimeout(saveTimer.current);
      const pending = textareaRef.current?.value;
      if (pending !== undefined && pending !== lastSaved.current) {
        void saveRef.current(pending);
      }
    };
  }, [file.id]);

  // Cmd/Ctrl+S flushes immediately.
  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if (!((e.metaKey || e.ctrlKey) && e.key === "s")) return;
      e.preventDefault();
      if (readOnly) return;
      if (saveTimer.current) {
        clearTimeout(saveTimer.current);
        saveTimer.current = null;
      }
      const current = textareaRef.current?.value;
      if (current !== undefined && current !== lastSaved.current) void saveRef.current(current);
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [readOnly, save]);

  /** Dropped and pasted files upload, then their markdown link lands at the
   *  cursor — the one editor affordance worth keeping from the rich version. */
  const insertFiles = useCallback(
    async (files: FileList | File[]) => {
      const area = textareaRef.current;
      if (!area || readOnly) return;
      for (const file of Array.from(files)) {
        const result = await uploadFile(file);
        const href = fileDownloadUrl(result.id);
        const snippet = result.content_type.startsWith("image/")
          ? `![${result.name}](${href})`
          : `[${result.name}](${href})`;
        const at = area.selectionStart;
        const next = area.value.slice(0, at) + snippet + area.value.slice(area.selectionEnd);
        onChange(next);
        // Put the caret after what we just inserted.
        requestAnimationFrame(() => {
          area.selectionStart = area.selectionEnd = at + snippet.length;
          area.focus();
        });
      }
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [readOnly]
  );

  return (
    <div className="flex h-full flex-col">
      <div className="flex shrink-0 items-center justify-end gap-1 border-b border-border-subtle px-3 py-1.5">
        <button
          type="button"
          onClick={() => setShowPreview((p) => !p)}
          className="cursor-pointer rounded px-2 py-1 text-[12px] text-muted-foreground transition-colors hover:bg-raised hover:text-foreground"
        >
          {showPreview ? "Hide preview" : "Preview"}
        </button>
      </div>

      {conflictMessage && (
        <div className="border-b border-red-300/40 bg-red-500/10 px-4 py-2 text-[13px] text-red-500">
          {conflictMessage}
        </div>
      )}
      {readOnly && !conflictMessage && (
        <div className="border-b border-border-subtle bg-raised px-4 py-2 text-[12px] text-muted-foreground">
          Read-only
        </div>
      )}

      <div className="flex min-h-0 flex-1 bg-background">
        <textarea
          ref={textareaRef}
          value={value}
          readOnly={readOnly}
          onChange={(e) => onChange(e.target.value)}
          onPaste={(e) => {
            const files = e.clipboardData?.files;
            if (!files || files.length === 0) return;
            e.preventDefault();
            void insertFiles(files);
          }}
          onDragOver={(e) => e.preventDefault()}
          onDrop={(e) => {
            const files = e.dataTransfer?.files;
            if (!files || files.length === 0) return;
            e.preventDefault();
            void insertFiles(files);
          }}
          spellCheck={false}
          placeholder="Start typing..."
          className="min-h-0 flex-1 resize-none bg-transparent px-12 pt-10 pb-24 font-mono text-[13px] leading-[1.7] text-foreground outline-none"
        />
        {showPreview && (
          <div className="min-h-0 flex-1 overflow-y-auto border-l border-border-subtle">
            <article className="prose prose-sm markdown-content mx-auto max-w-[920px] px-8 py-8 text-foreground">
              <Markdown remarkPlugins={[remarkGfm]}>{value}</Markdown>
            </article>
          </div>
        )}
      </div>
    </div>
  );
}

/** Comment anchors are `<span data-comment-id>` wrappers embedded in the
 *  markdown. The plain editor neither creates nor understands them, but pages
 *  written before it still carry them, and the thread list is reconciled
 *  against what the file actually contains after every save. */
export function extractCommentIdsFromMarkdown(markdown: string): string[] {
  const ids: string[] = [];
  const re = /<span\s+data-comment-id="([^"]+)"/g;
  let m: RegExpExecArray | null;
  while ((m = re.exec(markdown)) !== null) ids.push(m[1]);
  return Array.from(new Set(ids));
}
