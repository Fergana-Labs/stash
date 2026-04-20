"use client";

import { Node, mergeAttributes } from "@tiptap/core";
import { Extension } from "@tiptap/react";
import Suggestion, { SuggestionOptions } from "@tiptap/suggestion";
import { ReactRenderer } from "@tiptap/react";
import { NodeViewWrapper, ReactNodeViewRenderer } from "@tiptap/react";
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
  rankForAutocomplete,
  resolveWikiLink,
  type WikiLinkContext,
} from "../../../lib/wikiLink";

// --- Suggestion dropdown component ---

interface SuggestionItem {
  /** What we insert into the document (the full path as seen in markdown). */
  path: string;
  /** Primary label in the dropdown. */
  label: string;
  /** Hint text (e.g. the notebook/folder location). */
  hint: string;
}

interface SuggestionListProps {
  items: SuggestionItem[];
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
        if (event.key === "Enter" || event.key === "Tab") {
          if (items[selectedIndex]) {
            command({ id: items[selectedIndex].path });
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
            key={item.path}
            onClick={() => command({ id: item.path })}
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

// --- WikiLinkNode: renders [[path]] as a clickable styled element ---
// The node's `pageName` attribute stores the link's raw path text (e.g.
// "page" or "folder/page" or "notebook/folder/page"). Whether the link
// actually resolves depends on the surrounding editor's configured
// page index + context, checked on each render via a shared cache on
// the node's DOM data attributes.

function WikiLinkNodeView({
  node,
  extension,
}: {
  node: { attrs: Record<string, unknown> };
  extension: { options: WikiLinkOptions };
}) {
  const linkText = (node.attrs.pageName as string) || "";
  // addOptions() on the node guarantees these are present, but guard
  // defensively so a legacy cached bundle can't crash the whole editor.
  const pageIndex = extension.options?.pageIndex ?? [];
  const context = extension.options?.context ?? { notebookId: null, folderId: null };
  const resolution = resolveWikiLink(linkText, pageIndex, context);
  const isResolved = resolution.status === "resolved";

  // Display-friendly text: drop the bracket chrome entirely and show
  // only the final name segment so the link reads like a normal inline
  // reference, indistinguishable from a markdown link. Use the full
  // path on hover so authors can still see how they qualified it.
  const displayText = isResolved
    ? resolution.page.name
    : linkText.split("/").pop() || linkText;
  const tooltip = isResolved ? linkText : "Page not found — qualify the path.";

  // One class for working internal links, one for dead. Matches the
  // .ProseMirror a styling applied to markdown links so both feel
  // like the same thing when they work, and both fail the same way
  // when they don't.
  const className = isResolved ? "wiki-link-internal" : "wiki-link-dead";

  return (
    <NodeViewWrapper as="span" className="wiki-link-wrapper">
      <span
        className={className}
        title={tooltip}
        data-wiki-link={linkText}
        data-wiki-resolved={isResolved ? "true" : "false"}
        role={isResolved ? "link" : undefined}
        tabIndex={isResolved ? 0 : -1}
        onClick={(e) => {
          if (!isResolved) return;
          e.preventDefault();
          const event = new CustomEvent("wiki-link-click", {
            detail: { linkText },
            bubbles: true,
          });
          e.currentTarget.dispatchEvent(event);
        }}
        onKeyDown={(e) => {
          if (!isResolved) return;
          if (e.key === "Enter") {
            const event = new CustomEvent("wiki-link-click", {
              detail: { linkText },
              bubbles: true,
            });
            e.currentTarget.dispatchEvent(event);
          }
        }}
      >
        {displayText}
      </span>
    </NodeViewWrapper>
  );
}

export const WikiLinkNode = Node.create<WikiLinkOptions>({
  name: "wikiLinkNode",
  group: "inline",
  inline: true,
  atom: true,

  // The node needs pageIndex + context at render time to show resolved
  // vs dangling vs ambiguous styling. We duplicate the options with the
  // sibling WikiLink (suggestion) extension so the editor can configure
  // both in one place and the node's view can access them directly.
  addOptions() {
    return {
      pageIndex: [],
      context: { notebookId: null, folderId: null },
    };
  },

  addAttributes() {
    return {
      pageName: {
        default: "",
      },
    };
  },

  parseHTML() {
    return [
      {
        tag: 'span[data-wiki-link]',
        getAttrs: (el) => {
          const element = el as HTMLElement;
          return { pageName: element.getAttribute("data-wiki-link") || "" };
        },
      },
    ];
  },

  renderHTML({ HTMLAttributes }) {
    // Static fallback used when the node view isn't mounted (tests,
    // SSR, copy-to-HTML). Show the final path segment as the display
    // text so the output still looks like an ordinary link.
    const path = String(HTMLAttributes.pageName || "");
    const display = path.split("/").pop() || path;
    return [
      "span",
      mergeAttributes(HTMLAttributes, {
        "data-wiki-link": path,
        class: "wiki-link-internal",
      }),
      display,
    ];
  },

  addNodeView() {
    return ReactNodeViewRenderer(WikiLinkNodeView);
  },
});

// --- WikiLink Suggestion Extension (autocomplete with [[ trigger) ---

export interface WikiLinkOptions {
  /** Every page available for linking — same index used for resolution
   *  and autocomplete. */
  pageIndex: WorkspacePageEntry[];
  /** Where the link lives, so bare [[name]] lookups scope to the
   *  surrounding folder. */
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
    const path = formatPagePath(p, ctx);
    const hint =
      p.notebook_id === ctx.notebookId && p.folder_id === ctx.folderId
        ? ""
        : p.notebook_id === ctx.notebookId
          ? `in ${p.folder_name ?? "notebook root"}`
          : `in ${p.notebook_name}${p.folder_name ? ` / ${p.folder_name}` : ""}`;
    return { path, label: p.name, hint };
  });
}

export const WikiLink = Extension.create<WikiLinkOptions>({
  name: "wikiLink",

  addOptions() {
    return {
      pageIndex: [],
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
          ed.chain()
            .focus()
            .deleteRange(range as { from: number; to: number })
            .insertContent({
              type: "wikiLinkNode",
              attrs: { pageName: (props as { id: string }).id },
            })
            .insertContent(" ")
            .run();
        },
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
      } as any),
    ];
  },
});

export default WikiLink;
