"use client";

import { forwardRef, useEffect, useImperativeHandle, useRef, useState } from "react";

import HtmlPageView from "./HtmlPageView";
import { Page } from "../../lib/types";
import type { SaveStatus } from "./MarkdownEditor";

const AUTOSAVE_DEBOUNCE_MS = 1500;

interface HtmlPageEditorProps {
  file: Page;
  onSave: (html: string) => void;
  onSaveStatusChange?: (status: SaveStatus) => void;
}

export interface HtmlPageEditorHandle {
  /** Save the buffer now (skipping the debounce) — called when the user
   *  leaves edit mode, so the last keystrokes aren't lost to the timer. */
  flush: () => void;
}

// Split textarea + sandboxed iframe preview. Same 1500ms debounced autosave
// as MarkdownEditor. The preview reuses HtmlPageView so the live preview
// and the read-only renderer share an isolation boundary — what you see
// here is exactly what readers will see.
const HtmlPageEditor = forwardRef<HtmlPageEditorHandle, HtmlPageEditorProps>(
  function HtmlPageEditor({ file, onSave, onSaveStatusChange }, ref) {
    const [value, setValue] = useState(file.content_html);
    const [dirty, setDirty] = useState(false);
    const [saving, setSaving] = useState(false);
    const saveTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
    const lastSaved = useRef(file.content_html);
    // HtmlPageView pins its document to the first html it sees, so the
    // preview refreshes by remounting (nonce key) on each debounced save
    // rather than re-rendering per keystroke.
    const [preview, setPreview] = useState({ html: file.content_html, nonce: 0 });

    // Pull in fresh content when the parent swaps to a different page. Our own
    // saves echo back through the parent's page state with content equal to
    // lastSaved — resetting on those would clobber keystrokes typed during the
    // save round-trip.
    useEffect(() => {
      if (file.content_html === lastSaved.current) return;
      setValue(file.content_html);
      lastSaved.current = file.content_html;
      setDirty(false);
      setPreview((p) => ({ html: file.content_html, nonce: p.nonce + 1 }));
    }, [file.id, file.content_html]);

    useEffect(() => {
      onSaveStatusChange?.(saving ? "saving" : dirty ? "dirty" : "saved");
    }, [saving, dirty, onSaveStatusChange]);

    useImperativeHandle(
      ref,
      () => ({
        flush() {
          if (saveTimer.current) clearTimeout(saveTimer.current);
          if (value === lastSaved.current) return;
          onSave(value);
          lastSaved.current = value;
          setDirty(false);
        },
      }),
      [value, onSave],
    );

    function onChange(next: string) {
      setValue(next);
      setDirty(next !== lastSaved.current);
      if (saveTimer.current) clearTimeout(saveTimer.current);
      saveTimer.current = setTimeout(() => {
        if (next === lastSaved.current) return;
        setSaving(true);
        try {
          onSave(next);
          lastSaved.current = next;
          setDirty(false);
          setPreview((p) => ({ html: next, nonce: p.nonce + 1 }));
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
          autoFocus
          className="min-h-[60vh] w-full rounded-md border border-border-subtle bg-background p-3 font-mono text-[13px] leading-[1.5] text-foreground"
          placeholder="<!doctype html>&#10;<html>&#10;  <body>&#10;    <h1>Hello</h1>&#10;  </body>&#10;</html>"
        />
        <div className="min-h-[60vh] overflow-hidden rounded-md border border-border-subtle bg-raised/30">
          <HtmlPageView key={preview.nonce} html={preview.html} title={file.name} />
        </div>
      </div>
    );
  },
);

export default HtmlPageEditor;
