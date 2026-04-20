"use client";

import { Extension } from "@tiptap/react";
import Suggestion from "@tiptap/suggestion";
import { ReactRenderer } from "@tiptap/react";
import tippy, { Instance as TippyInstance } from "tippy.js";
import {
  forwardRef,
  useEffect,
  useImperativeHandle,
  useState,
} from "react";
import type { WorkspacePageEntry } from "../../../lib/api";
import {
  formatPagePath,
  pageHref,
  rankForAutocomplete,
  type WikiLinkContext,
} from "../../../lib/wikiLink";

interface SuggestionItem {
  page: WorkspacePageEntry;
  label: string;
  hint: string;
}

interface SuggestionListProps {
  items: SuggestionItem[];
  command: (item: { page: WorkspacePageEntry }) => void;
}

interface SuggestionListRef {
  onKeyDown: (props: { event: KeyboardEvent }) => boolean;
}

const SuggestionList = forwardRef<SuggestionListRef, SuggestionListProps>(
  ({ items, command }, ref) => {
    const [selectedIndex, setSelectedIndex] = useState(0);

    useEffect(() => setSelectedIndex(0), [items]);

    useImperativeHandle(ref, () => ({
      onKeyDown: ({ event }) => {
        if (event.key === "ArrowUp") {
          setSelectedIndex((i) => (i + items.length - 1) % items.length);
          return true;
        }
        if (event.key === "ArrowDown") {
          setSelectedIndex((i) => (i + 1) % items.length);
          return true;
        }
        if (event.key === "Enter" || event.key === "Tab") {
          if (items[selectedIndex]) {
            command({ page: items[selectedIndex].page });
          }
          return true;
        }
        if (event.key === "Escape") {
          return true;
        }
        return false;
      },
    }));

    if (items.length === 0) return null;

    return (
      <div className="bg-base border border-border rounded-lg shadow-lg overflow-hidden py-1 min-w-[220px] z-50">
        {items.map((item, i) => (
          <button
            key={item.page.id}
            onClick={() => command({ page: item.page })}
            className={`block w-full text-left px-3 py-1.5 text-sm transition-colors ${
              i === selectedIndex
                ? "bg-brand/10 text-brand"
                : "text-foreground hover:bg-raised"
            }`}
          >
            <div className="truncate">{item.label}</div>
            {item.hint ? (
              <div className="text-xs text-muted truncate">{item.hint}</div>
            ) : null}
          </button>
        ))}
      </div>
    );
  }
);
SuggestionList.displayName = "SuggestionList";

function suggestionRenderer() {
  let component: ReactRenderer<SuggestionListRef> | null = null;
  let popup: TippyInstance[] | null = null;

  return {
    onStart: (props: Record<string, unknown>) => {
      component = new ReactRenderer(SuggestionList, {
        props,
        editor: props.editor as never,
      });

      if (!props.clientRect) return;

      popup = tippy("body", {
        getReferenceClientRect: props.clientRect as () => DOMRect,
        appendTo: () => document.body,
        content: component.element,
        showOnCreate: true,
        interactive: true,
        trigger: "manual",
        placement: "bottom-start",
      });
    },

    onUpdate(props: Record<string, unknown>) {
      component?.updateProps(props);
      if (popup?.[0] && props.clientRect) {
        popup[0].setProps({
          getReferenceClientRect: props.clientRect as () => DOMRect,
        });
      }
    },

    onKeyDown(props: { event: KeyboardEvent }) {
      if (props.event.key === "Escape") {
        popup?.[0]?.hide();
        return true;
      }
      return component?.ref?.onKeyDown(props) ?? false;
    },

    onExit() {
      popup?.[0]?.destroy();
      component?.destroy();
    },
  };
}

export interface WikiLinkOptions {
  pageIndex: WorkspacePageEntry[];
  workspaceId: string;
  context: WikiLinkContext;
}

function buildSuggestions(
  query: string,
  pages: WorkspacePageEntry[],
  ctx: WikiLinkContext
): SuggestionItem[] {
  const ranked = rankForAutocomplete(pages, ctx);
  const q = query.toLowerCase();
  const matches = q
    ? ranked.filter((p) => {
        const path = formatPagePath(p, ctx).toLowerCase();
        return path.includes(q) || p.name.toLowerCase().includes(q);
      })
    : ranked;
  return matches.slice(0, 8).map((p) => {
    const label = p.name;
    const hint =
      p.notebook_id === ctx.notebookId && p.folder_id === ctx.folderId
        ? ""
        : p.notebook_id === ctx.notebookId
          ? `in ${p.folder_name ?? "notebook root"}`
          : `in ${p.notebook_name}${p.folder_name ? ` / ${p.folder_name}` : ""}`;
    return { page: p, label, hint };
  });
}

export const WikiLink = Extension.create<WikiLinkOptions>({
  name: "wikiLink",

  addOptions() {
    return {
      pageIndex: [],
      workspaceId: "",
      context: { notebookId: null, folderId: null },
    };
  },

  addProseMirrorPlugins() {
    return [
      Suggestion({
        editor: this.editor,
        char: "[[",
        items: ({ query }: { query: string }) =>
          buildSuggestions(query, this.options.pageIndex, this.options.context),
        render: suggestionRenderer,
        command: ({ editor, range, props }: Record<string, unknown>) => {
          const ed = editor as import("@tiptap/react").Editor;
          const { page } = props as { page: WorkspacePageEntry };
          const href = pageHref(page, this.options.workspaceId);
          ed.chain()
            .focus()
            .deleteRange(range as { from: number; to: number })
            .insertContent([
              {
                type: "text",
                text: page.name,
                marks: [{ type: "link", attrs: { href } }],
              },
              { type: "text", text: " " },
            ])
            .run();
        },
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
      } as any),
    ];
  },
});

export default WikiLink;
