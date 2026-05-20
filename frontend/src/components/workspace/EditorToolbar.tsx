"use client";

import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { Editor } from "@tiptap/react";
import { uploadFile } from "../../lib/api";

interface EditorToolbarProps {
  editor: Editor | null;
  workspaceId?: string | null;
  /** When set, the bubble menu shows a "Comment" button that asks the
   *  parent to open a comment composer anchored to the current
   *  selection. The parent owns the composer + the server call. */
  onStartComment?: () => void;
  /** "always" (default) shows the pill whenever the editor is editable.
   *  "when-focused" hides it unless the editor has focus — right for
   *  inline editors like workspace + stash descriptions. */
  visibility?: "always" | "when-focused";
}

// Fixed pill toolbar centered along the viewport bottom. Rendered via a
// portal to document.body so it floats above any flex/scroll ancestor.
export default function EditorToolbar({
  editor,
  workspaceId,
  onStartComment,
  visibility = "always",
}: EditorToolbarProps) {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [uploading, setUploading] = useState(false);
  const [, forceRender] = useState(0);
  const [mounted, setMounted] = useState(false);
  const [tableMenuOpen, setTableMenuOpen] = useState(false);
  const [isFocused, setIsFocused] = useState(false);
  const tableBtnRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    setMounted(true);
  }, []);

  // Track editor focus for visibility="when-focused" inline use. We keep
  // the pill alive briefly after blur so clicks on the toolbar itself
  // don't dismiss it before the click handler fires.
  useEffect(() => {
    if (!editor) return;
    setIsFocused(editor.isFocused);
    const onFocus = () => setIsFocused(true);
    const onBlur = () => setIsFocused(editor.isFocused);
    editor.on("focus", onFocus);
    editor.on("blur", onBlur);
    return () => {
      editor.off("focus", onFocus);
      editor.off("blur", onBlur);
    };
  }, [editor]);

  // Close the table menu on outside click / Escape.
  useEffect(() => {
    if (!tableMenuOpen) return;
    const onDown = (e: MouseEvent) => {
      if (!tableBtnRef.current?.contains(e.target as Node)) setTableMenuOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setTableMenuOpen(false);
    };
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [tableMenuOpen]);

  // Re-render on every editor transaction so active/disabled states stay
  // in sync with the editor state (selection change, history boundary,
  // mark toggles, etc.).
  useEffect(() => {
    if (!editor) return;
    const onUpdate = () => forceRender((n) => n + 1);
    editor.on("transaction", onUpdate);
    editor.on("selectionUpdate", onUpdate);
    return () => {
      editor.off("transaction", onUpdate);
      editor.off("selectionUpdate", onUpdate);
    };
  }, [editor]);

  const inTable = editor?.isActive("table") ?? false;

  // Close the table menu automatically when the caret leaves the table.
  useEffect(() => {
    if (tableMenuOpen && !inTable) setTableMenuOpen(false);
  }, [tableMenuOpen, inTable]);

  if (!editor || !editor.isEditable || !mounted) return null;
  if (visibility === "when-focused" && !isFocused && !tableMenuOpen) return null;

  const selectionEmpty = editor.state.selection.empty;

  async function handleUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file || !editor || !workspaceId) return;
    setUploading(true);
    try {
      const result = await uploadFile(workspaceId, file);
      const href = `/api/v1/workspaces/${workspaceId}/files/${result.id}/download`;
      if (result.content_type.startsWith("image/")) {
        editor.chain().focus().setImage({ src: result.url, alt: result.name }).run();
      } else {
        editor.chain().focus().setLink({ href }).insertContent(result.name).run();
      }
    } catch {
      // Storage may not be configured — fail silently.
    }
    setUploading(false);
    if (fileInputRef.current) fileInputRef.current.value = "";
  }

  function promptLink() {
    if (!editor) return;
    const existing = editor.getAttributes("link").href as string | undefined;
    const url = window.prompt("Link URL", existing ?? "https://");
    if (url == null) return;
    if (url === "") {
      editor.chain().focus().unsetLink().run();
      return;
    }
    editor.chain().focus().extendMarkRange("link").setLink({ href: url }).run();
  }

  const inline = visibility === "when-focused";
  const toolbar = (
    <div
      className={
        inline
          ? "inline-flex items-center gap-0.5 rounded-full border border-border bg-surface px-2 py-1.5 shadow-[0_6px_20px_-4px_rgba(0,0,0,0.18)]"
          : "fixed left-1/2 z-40 inline-flex -translate-x-1/2 items-center gap-0.5 rounded-full border border-border bg-surface px-2 py-1.5 shadow-[0_6px_20px_-4px_rgba(0,0,0,0.18)]"
      }
      style={inline ? undefined : { bottom: 16 }}
      onMouseDown={(e) => e.preventDefault()}
    >
      <Btn
        title="Undo"
        disabled={!editor.can().undo()}
        onClick={() => editor.chain().focus().undo().run()}
      >
        <UndoIcon />
      </Btn>
      <Btn
        title="Redo"
        disabled={!editor.can().redo()}
        onClick={() => editor.chain().focus().redo().run()}
      >
        <RedoIcon />
      </Btn>

      <Sep />

      <Btn
        title="Bold (⌘B)"
        active={editor.isActive("bold")}
        onClick={() => editor.chain().focus().toggleBold().run()}
      >
        <span className="font-semibold">B</span>
      </Btn>
      <Btn
        title="Italic (⌘I)"
        active={editor.isActive("italic")}
        onClick={() => editor.chain().focus().toggleItalic().run()}
      >
        <span className="italic">I</span>
      </Btn>
      <Btn
        title="Strikethrough"
        active={editor.isActive("strike")}
        onClick={() => editor.chain().focus().toggleStrike().run()}
      >
        <span className="line-through">S</span>
      </Btn>
      <Btn
        title="Inline code"
        active={editor.isActive("code")}
        onClick={() => editor.chain().focus().toggleCode().run()}
      >
        <CodeIcon />
      </Btn>

      <Sep />

      <Btn
        title="Heading 1"
        active={editor.isActive("heading", { level: 1 })}
        onClick={() => editor.chain().focus().toggleHeading({ level: 1 }).run()}
      >
        <HText n={1} />
      </Btn>
      <Btn
        title="Heading 2"
        active={editor.isActive("heading", { level: 2 })}
        onClick={() => editor.chain().focus().toggleHeading({ level: 2 }).run()}
      >
        <HText n={2} />
      </Btn>
      <Btn
        title="Heading 3"
        active={editor.isActive("heading", { level: 3 })}
        onClick={() => editor.chain().focus().toggleHeading({ level: 3 }).run()}
      >
        <HText n={3} />
      </Btn>

      <Sep />

      <Btn
        title="Bullet list"
        active={editor.isActive("bulletList")}
        onClick={() => editor.chain().focus().toggleBulletList().run()}
      >
        <BulletIcon />
      </Btn>
      <Btn
        title="Numbered list"
        active={editor.isActive("orderedList")}
        onClick={() => editor.chain().focus().toggleOrderedList().run()}
      >
        <OrderedIcon />
      </Btn>
      <Btn
        title="Quote"
        active={editor.isActive("blockquote")}
        onClick={() => editor.chain().focus().toggleBlockquote().run()}
      >
        <QuoteIcon />
      </Btn>
      <Btn
        title="Horizontal rule"
        onClick={() => editor.chain().focus().setHorizontalRule().run()}
      >
        <HrIcon />
      </Btn>

      <Sep />

      <div ref={tableBtnRef} className="relative">
        <Btn
          title={inTable ? "Table options" : "Insert table"}
          active={inTable && tableMenuOpen}
          onClick={() => {
            if (inTable) {
              setTableMenuOpen((o) => !o);
              return;
            }
            editor
              .chain()
              .focus()
              .insertTable({ rows: 3, cols: 3, withHeaderRow: true })
              .run();
          }}
        >
          <TableIcon />
        </Btn>
        {tableMenuOpen && inTable && (
          <TableMenu
            editor={editor}
            onClose={() => setTableMenuOpen(false)}
          />
        )}
      </div>
      <Btn
        title={editor.isActive("link") ? "Edit link" : "Add link"}
        active={editor.isActive("link")}
        onClick={promptLink}
      >
        <LinkIcon />
      </Btn>
      {workspaceId && (
        <Btn
          title="Upload image or file"
          disabled={uploading}
          onClick={() => fileInputRef.current?.click()}
        >
          {uploading ? <Spinner /> : <ImageIcon />}
        </Btn>
      )}

      {onStartComment && (
        <>
          <Sep />
          <button
            type="button"
            onMouseDown={(e) => e.preventDefault()}
            onClick={() => onStartComment()}
            disabled={selectionEmpty}
            title={selectionEmpty ? "Select text to comment" : "Comment on selection"}
            className={
              "inline-flex h-7 items-center gap-1.5 rounded-md px-2.5 text-[12.5px] font-medium transition " +
              (selectionEmpty
                ? "cursor-not-allowed text-muted/40"
                : "text-foreground hover:bg-raised")
            }
          >
            <CommentIcon />
            Comment
          </button>
        </>
      )}

      {workspaceId && (
        <input
          ref={fileInputRef}
          type="file"
          accept="image/*,.pdf,.doc,.docx,.txt,.csv,.xls,.xlsx"
          className="hidden"
          onChange={handleUpload}
        />
      )}
    </div>
  );

  if (inline) {
    // Render in the document flow under the editor so descriptions don't
    // anchor their toolbar to the viewport bottom.
    return <div className="mt-3 flex justify-start">{toolbar}</div>;
  }
  return createPortal(toolbar, document.body);
}

function Btn({
  title,
  active,
  disabled,
  onClick,
  children,
}: {
  title: string;
  active?: boolean;
  disabled?: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onMouseDown={(e) => e.preventDefault()}
      onClick={onClick}
      disabled={disabled}
      title={title}
      aria-label={title}
      className={
        "inline-flex h-7 w-7 items-center justify-center rounded-md text-[13px] transition " +
        (disabled
          ? "cursor-not-allowed text-muted/40"
          : active
            ? "bg-foreground/5 text-foreground"
            : "text-muted hover:bg-raised hover:text-foreground")
      }
    >
      {children}
    </button>
  );
}

function Sep() {
  return <span className="mx-1 h-4 w-px bg-border" aria-hidden />;
}

function TableMenu({
  editor,
  onClose,
}: {
  editor: Editor;
  onClose: () => void;
}) {
  function run(fn: () => void) {
    return () => {
      fn();
      // Most table ops leave the menu logically obsolete (e.g. deleteTable
      // moves the caret out, deleteRow may collapse). Close after every op
      // so users don't fire stale commands against a now-different cell.
      onClose();
    };
  }
  return (
    <div
      className="absolute bottom-full left-1/2 z-50 mb-2 w-56 -translate-x-1/2 overflow-hidden rounded-md border border-border bg-surface py-1 text-[12.5px] shadow-[0_8px_24px_-6px_rgba(0,0,0,0.25)]"
      onMouseDown={(e) => e.preventDefault()}
    >
      <Item onClick={run(() => editor.chain().focus().addRowBefore().run())}>Add row above</Item>
      <Item onClick={run(() => editor.chain().focus().addRowAfter().run())}>Add row below</Item>
      <Item onClick={run(() => editor.chain().focus().addColumnBefore().run())}>Add column left</Item>
      <Item onClick={run(() => editor.chain().focus().addColumnAfter().run())}>Add column right</Item>
      <Divider />
      <Item onClick={run(() => editor.chain().focus().toggleHeaderRow().run())}>Toggle header row</Item>
      <Item onClick={run(() => editor.chain().focus().toggleHeaderColumn().run())}>Toggle header column</Item>
      <Item onClick={run(() => editor.chain().focus().mergeOrSplit().run())}>Merge / split cells</Item>
      <Divider />
      <Item destructive onClick={run(() => editor.chain().focus().deleteRow().run())}>Delete row</Item>
      <Item destructive onClick={run(() => editor.chain().focus().deleteColumn().run())}>Delete column</Item>
      <Item destructive onClick={run(() => editor.chain().focus().deleteTable().run())}>Delete table</Item>
    </div>
  );
}

function Item({
  onClick,
  destructive,
  children,
}: {
  onClick: () => void;
  destructive?: boolean;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={
        "block w-full px-3 py-1.5 text-left transition " +
        (destructive
          ? "text-red-600 hover:bg-red-500/10"
          : "text-foreground hover:bg-raised")
      }
    >
      {children}
    </button>
  );
}

function Divider() {
  return <div className="my-1 border-t border-border" />;
}

function HText({ n }: { n: 1 | 2 | 3 }) {
  return (
    <span className="font-semibold tracking-tight">
      H<span className="text-[10px]">{n}</span>
    </span>
  );
}

function UndoIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d="M9 14L4 9l5-5" />
      <path d="M4 9h11a5 5 0 0 1 0 10h-4" />
    </svg>
  );
}

function RedoIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d="M15 14l5-5-5-5" />
      <path d="M20 9H9a5 5 0 0 0 0 10h4" />
    </svg>
  );
}

function CodeIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="16 18 22 12 16 6" />
      <polyline points="8 6 2 12 8 18" />
    </svg>
  );
}

function BulletIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <line x1="9" y1="6" x2="20" y2="6" />
      <line x1="9" y1="12" x2="20" y2="12" />
      <line x1="9" y1="18" x2="20" y2="18" />
      <circle cx="4.5" cy="6" r="1.2" fill="currentColor" />
      <circle cx="4.5" cy="12" r="1.2" fill="currentColor" />
      <circle cx="4.5" cy="18" r="1.2" fill="currentColor" />
    </svg>
  );
}

function OrderedIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <line x1="10" y1="6" x2="20" y2="6" />
      <line x1="10" y1="12" x2="20" y2="12" />
      <line x1="10" y1="18" x2="20" y2="18" />
      <text x="3" y="9" fontSize="7" fill="currentColor" stroke="none" fontFamily="ui-monospace, monospace">1</text>
      <text x="3" y="15" fontSize="7" fill="currentColor" stroke="none" fontFamily="ui-monospace, monospace">2</text>
      <text x="3" y="21" fontSize="7" fill="currentColor" stroke="none" fontFamily="ui-monospace, monospace">3</text>
    </svg>
  );
}

function QuoteIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor" stroke="none">
      <path d="M6.5 7C5 7 4 8 4 9.5V13c0 1.5 1 2.5 2.5 2.5H8L6 19h2.5l3-5.5V9.5C11.5 8 10.5 7 9 7H6.5zM15.5 7C14 7 13 8 13 9.5V13c0 1.5 1 2.5 2.5 2.5H17l-2 3.5h2.5l3-5.5V9.5C20.5 8 19.5 7 18 7h-2.5z" />
    </svg>
  );
}

function HrIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
      <line x1="4" y1="12" x2="20" y2="12" />
    </svg>
  );
}

function TableIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <rect x="3" y="4" width="18" height="16" rx="1.5" />
      <line x1="3" y1="10" x2="21" y2="10" />
      <line x1="3" y1="16" x2="21" y2="16" />
      <line x1="9" y1="4" x2="9" y2="20" />
      <line x1="15" y1="4" x2="15" y2="20" />
    </svg>
  );
}

function LinkIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d="M10 13a5 5 0 0 0 7 0l3-3a5 5 0 1 0-7-7l-1.5 1.5" />
      <path d="M14 11a5 5 0 0 0-7 0l-3 3a5 5 0 1 0 7 7l1.5-1.5" />
    </svg>
  );
}

function ImageIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <rect x="3" y="4" width="18" height="16" rx="2" />
      <circle cx="9" cy="9.5" r="1.4" />
      <path d="M21 16l-5-5-9 9" />
    </svg>
  );
}

function CommentIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d="M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5a8.48 8.48 0 0 1 8 8v.5z" />
    </svg>
  );
}

function Spinner() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" className="animate-spin" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
      <path d="M21 12a9 9 0 1 1-3-6.7" />
    </svg>
  );
}
