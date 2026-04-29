"use client";

import { useEffect, useRef, useState } from "react";

import HtmlPageView from "./HtmlPageView";
import { NotebookPage } from "../../lib/types";
import type { SaveStatus } from "./MarkdownEditor";

const AUTOSAVE_DEBOUNCE_MS = 1500;

interface HtmlPageEditorProps {
  file: NotebookPage;
  onSave: (html: string) => void;
  onSaveStatusChange?: (status: SaveStatus) => void;
}

// Split textarea + sandboxed iframe preview. Same 1500ms debounced autosave
// as MarkdownEditor. The preview reuses HtmlPageView so the live preview
// and the read-only renderer share an isolation boundary — what you see
// here is exactly what readers will see.
export default function HtmlPageEditor({
  file,
  onSave,
  onSaveStatusChange,
}: HtmlPageEditorProps) {
  const [value, setValue] = useState(file.content_html);
  const [dirty, setDirty] = useState(false);
  const [saving, setSaving] = useState(false);
  const saveTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const lastSaved = useRef(file.content_html);

  // Pull in fresh content when the parent swaps to a different page.
  useEffect(() => {
    setValue(file.content_html);
    lastSaved.current = file.content_html;
    setDirty(false);
  }, [file.id, file.content_html]);

  useEffect(() => {
    onSaveStatusChange?.(saving ? "saving" : dirty ? "dirty" : "saved");
  }, [saving, dirty, onSaveStatusChange]);

  function onChange(next: string) {
    setValue(next);
    setDirty(next !== lastSaved.current);
    if (saveTimer.current) clearTimeout(saveTimer.current);
    saveTimer.current = setTimeout(async () => {
      if (next === lastSaved.current) return;
      setSaving(true);
      try {
        onSave(next);
        lastSaved.current = next;
        setDirty(false);
      } finally {
        setSaving(false);
      }
    }, AUTOSAVE_DEBOUNCE_MS);
  }

  return (
    <div className="grid h-full grid-cols-1 gap-4 lg:grid-cols-2">
      <textarea
        value={value}
        onChange={(e) => onChange(e.target.value)}
        spellCheck={false}
        className="min-h-[60vh] w-full rounded-md border border-border-subtle bg-background p-3 font-mono text-[13px] leading-[1.5] text-foreground"
        placeholder="<!doctype html>&#10;<html>&#10;  <body>&#10;    <h1>Hello</h1>&#10;  </body>&#10;</html>"
      />
      <div className="min-h-[60vh] overflow-hidden rounded-md border border-border-subtle bg-raised/30">
        <HtmlPageView html={value} title={file.name} />
      </div>
    </div>
  );
}
