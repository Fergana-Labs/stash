"use client";

import { defaultKeymap, history, historyKeymap } from "@codemirror/commands";
import { syntaxTree } from "@codemirror/language";
import { markdown } from "@codemirror/lang-markdown";
import { EditorState, type Range } from "@codemirror/state";
import {
  Decoration,
  type DecorationSet,
  EditorView,
  keymap,
  placeholder,
  ViewPlugin,
  type ViewUpdate,
} from "@codemirror/view";
import { useEffect, useRef } from "react";

interface LiveMarkdownEditorProps {
  value: string;
  onChange: (value: string) => void;
  onSave: (value: string) => void;
  readOnly?: boolean;
}

export default function LiveMarkdownEditor({
  value,
  onChange,
  onSave,
  readOnly = false,
}: LiveMarkdownEditorProps) {
  const hostRef = useRef<HTMLDivElement | null>(null);
  const viewRef = useRef<EditorView | null>(null);
  const onChangeRef = useRef(onChange);
  const onSaveRef = useRef(onSave);
  const syncingRef = useRef(false);

  useEffect(() => {
    onChangeRef.current = onChange;
    onSaveRef.current = onSave;
  }, [onChange, onSave]);

  useEffect(() => {
    if (!hostRef.current) return;

    const view = new EditorView({
      parent: hostRef.current,
      state: EditorState.create({
        doc: value,
        extensions: [
          history(),
          markdown(),
          liveMarkdownDecorations,
          placeholder("Start typing..."),
          EditorState.readOnly.of(readOnly),
          EditorView.editable.of(!readOnly),
          EditorView.contentAttributes.of({ "aria-label": "Start typing..." }),
          keymap.of([
            ...defaultKeymap,
            ...historyKeymap,
            {
              key: "Mod-s",
              preventDefault: true,
              run: (currentView) => {
                onSaveRef.current(currentView.state.doc.toString());
                return true;
              },
            },
          ]),
          EditorView.updateListener.of((update) => {
            if (!update.docChanged || syncingRef.current) return;
            onChangeRef.current(update.state.doc.toString());
          }),
          EditorView.lineWrapping,
          // CodeMirror maps pointer coordinates from measured line boxes.
          // Vertical margins sit outside those boxes and make clicks drift
          // farther down the document after every heading; padding is measured.
          EditorView.theme({
            "&": {
              minHeight: "75vh",
              backgroundColor: "transparent",
              color: "var(--color-foreground)",
              fontSize: "14px",
            },
            ".cm-scroller": {
              minHeight: "75vh",
              overflow: "visible",
              fontFamily: "inherit",
              lineHeight: "1.7",
            },
            ".cm-content": {
              minHeight: "75vh",
              boxSizing: "border-box",
              padding: "34px 48px 96px",
              caretColor: "var(--color-foreground)",
            },
            ".cm-focused": { outline: "none" },
            ".cm-gutters": { display: "none" },
            ".cm-line": { padding: "0" },
            ".cm-live-heading-1": {
              fontSize: "28px",
              fontWeight: "700",
              lineHeight: "1.25",
              paddingTop: "18px",
              paddingBottom: "8px",
            },
            ".cm-live-heading-2": {
              fontSize: "21px",
              fontWeight: "700",
              lineHeight: "1.3",
              paddingTop: "16px",
              paddingBottom: "6px",
            },
            ".cm-live-heading-3": {
              fontSize: "17px",
              fontWeight: "650",
              lineHeight: "1.35",
              paddingTop: "14px",
              paddingBottom: "4px",
            },
            ".cm-live-heading-1 span, .cm-live-heading-2 span, .cm-live-heading-3 span": {
              color: "var(--color-foreground)",
              textDecoration: "none",
            },
            ".cm-live-strong": { fontWeight: "700" },
            ".cm-live-emphasis": { fontStyle: "italic" },
            ".cm-live-inline-code": {
              borderRadius: "4px",
              backgroundColor: "var(--color-raised)",
              color: "var(--color-brand-600)",
              fontFamily: "var(--font-mono)",
              fontSize: "0.9em",
            },
            ".cm-selectionBackground, ::selection": {
              backgroundColor: "color-mix(in srgb, var(--color-brand-500) 20%, transparent) !important",
            },
          }),
        ],
      }),
    });
    viewRef.current = view;

    return () => {
      view.destroy();
      viewRef.current = null;
    };
    // The view owns subsequent document updates; changing props must not
    // recreate it and move the caret.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    const view = viewRef.current;
    if (!view || view.state.doc.toString() === value) return;
    syncingRef.current = true;
    view.dispatch({
      changes: { from: 0, to: view.state.doc.length, insert: value },
    });
    syncingRef.current = false;
  }, [value]);

  return <div ref={hostRef} data-testid="live-markdown-editor" className="min-w-0 flex-1" />;
}

const liveMarkdownDecorations = ViewPlugin.fromClass(
  class {
    decorations: DecorationSet;

    constructor(view: EditorView) {
      this.decorations = buildDecorations(view);
    }

    update(update: ViewUpdate) {
      if (update.docChanged || update.selectionSet || update.viewportChanged) {
        this.decorations = buildDecorations(update.view);
      }
    }
  },
  { decorations: (plugin) => plugin.decorations },
);

function buildDecorations(view: EditorView): DecorationSet {
  const decorations: Range<Decoration>[] = [];
  const activeLine = view.state.doc.lineAt(view.state.selection.main.head);

  syntaxTree(view.state).iterate({
    enter(node) {
      const heading = /^ATXHeading([1-3])$/.exec(node.name);
      if (heading) {
        const line = view.state.doc.lineAt(node.from);
        decorations.push(
          Decoration.line({
            attributes: { class: `cm-live-heading-${heading[1]}` },
          }).range(line.from),
        );
      }

      const markClass = {
        StrongEmphasis: "cm-live-strong",
        Emphasis: "cm-live-emphasis",
        InlineCode: "cm-live-inline-code",
      }[node.name];
      if (markClass) {
        decorations.push(Decoration.mark({ class: markClass }).range(node.from, node.to));
      }

      const line = view.state.doc.lineAt(node.from);
      if (line.number === activeLine.number) return;

      if (node.name === "HeaderMark" && node.node.parent?.name.startsWith("ATXHeading")) {
        const afterMark = view.state.sliceDoc(node.to, Math.min(node.to + 1, line.to));
        const to = afterMark === " " ? node.to + 1 : node.to;
        decorations.push(Decoration.replace({}).range(node.from, to));
      }
      if (node.name === "EmphasisMark" || node.name === "CodeMark") {
        decorations.push(Decoration.replace({}).range(node.from, node.to));
      }
    },
  });

  return Decoration.set(decorations, true);
}
