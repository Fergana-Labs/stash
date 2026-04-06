"use client";

import { Node, mergeAttributes } from "@tiptap/react";
import Suggestion, { SuggestionOptions } from "@tiptap/suggestion";
import { ReactRenderer } from "@tiptap/react";
import tippy, { Instance as TippyInstance } from "tippy.js";
import {
  forwardRef,
  useEffect,
  useImperativeHandle,
  useState,
} from "react";

// --- Suggestion dropdown component ---

interface SuggestionListProps {
  items: string[];
  command: (item: { id: string }) => void;
}

interface SuggestionListRef {
  onKeyDown: (props: { event: KeyboardEvent }) => boolean;
}

const SuggestionList = forwardRef<SuggestionListRef, SuggestionListProps>(
  ({ items, command }, ref) => {
    const [selectedIndex, setSelectedIndex] = useState(0);

    useEffect(() => setSelectedIndex(0), [items]);

    useImperativeHandle(ref, () => ({
      onKeyDown: ({ event }: { event: KeyboardEvent }) => {
        if (event.key === "ArrowUp") {
          setSelectedIndex((i) => (i + items.length - 1) % items.length);
          return true;
        }
        if (event.key === "ArrowDown") {
          setSelectedIndex((i) => (i + 1) % items.length);
          return true;
        }
        if (event.key === "Enter") {
          if (items[selectedIndex]) {
            command({ id: items[selectedIndex] });
          }
          return true;
        }
        return false;
      },
    }));

    if (items.length === 0) return null;

    return (
      <div className="bg-base border border-border rounded-lg shadow-lg overflow-hidden py-1 min-w-[180px]">
        {items.map((item, i) => (
          <button
            key={item}
            onClick={() => command({ id: item })}
            className={`block w-full text-left px-3 py-1.5 text-sm transition-colors ${
              i === selectedIndex
                ? "bg-brand/10 text-brand"
                : "text-foreground hover:bg-raised"
            }`}
          >
            {item}
          </button>
        ))}
      </div>
    );
  }
);
SuggestionList.displayName = "SuggestionList";

// --- TipTap suggestion renderer using tippy.js ---

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

// --- WikiLink Node Extension ---

export interface WikiLinkOptions {
  pageNames: string[];
}

export const WikiLink = Node.create<WikiLinkOptions>({
  name: "wikiLink",
  group: "inline",
  inline: true,
  atom: true,

  addOptions() {
    return {
      pageNames: [],
    };
  },

  addAttributes() {
    return {
      pageName: {
        default: null,
        parseHTML: (element) => element.getAttribute("data-page-name"),
        renderHTML: (attributes) => ({
          "data-page-name": attributes.pageName,
        }),
      },
    };
  },

  parseHTML() {
    return [{ tag: 'span[data-type="wiki-link"]' }];
  },

  renderHTML({ node, HTMLAttributes }) {
    return [
      "span",
      mergeAttributes(HTMLAttributes, {
        "data-type": "wiki-link",
        class: "text-brand cursor-pointer hover:underline",
      }),
      `[[${node.attrs.pageName}]]`,
    ];
  },

  addKeyboardShortcuts() {
    return {};
  },

  addProseMirrorPlugins() {
    return [
      Suggestion({
        editor: this.editor,
        char: "[[",
        items: ({ query }: { query: string }) => {
          const names = this.options.pageNames;
          if (!query) return names.slice(0, 8);
          const lower = query.toLowerCase();
          return names
            .filter((n: string) => n.toLowerCase().includes(lower))
            .slice(0, 8);
        },
        render: suggestionRenderer,
        command: ({ editor, range, props }: Record<string, unknown>) => {
          const ed = editor as import("@tiptap/react").Editor;
          ed.chain()
            .focus()
            .deleteRange(range as { from: number; to: number })
            .insertContent(`[[${(props as { id: string }).id}]]`)
            .run();
        },
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
      } as any),
    ];
  },
});

export default WikiLink;
