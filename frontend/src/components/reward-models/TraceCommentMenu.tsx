"use client";

import { useEffect, useRef, useState, type ReactElement } from "react";
import { ContextMenu } from "radix-ui";
import { Copy, MessageSquarePlus } from "lucide-react";
import { toast } from "sonner";
import type { RmStep } from "@/lib/types";
import type { ComposerTarget } from "./AnnotationComposer";
import { selectedCommentTarget } from "./trace-comment-selection";

/** Snapshot the selection before the menu or composer takes keyboard focus. */
export default function TraceCommentMenu({ children, steps, onComment }: {
  children: ReactElement;
  steps: RmStep[];
  onComment: (target: ComposerTarget) => void;
}) {
  const [target, setTarget] = useState<ComposerTarget>({ stepId: null, quote: null });
  const [copyText, setCopyText] = useState("");
  const canvas = useRef<HTMLDivElement>(null);
  const itemClass = "flex cursor-default select-none items-center gap-2 rounded-md px-2 py-1.5 text-sm outline-none focus:bg-accent focus:text-accent-foreground";

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if (event.key !== "ContextMenu" && !(event.shiftKey && event.key === "F10")) return;
      if ((event.target as HTMLElement).closest("input, textarea, [contenteditable=true]")) return;
      const selection = window.getSelection();
      const range = selection?.rangeCount && !selection.isCollapsed ? selection.getRangeAt(0) : null;
      const target = range?.startContainer.parentElement ?? event.target as HTMLElement;
      if (!canvas.current?.contains(target)) return;
      event.preventDefault();
      const rect = range?.getBoundingClientRect() ?? target.getBoundingClientRect();
      target.dispatchEvent(new MouseEvent("contextmenu", { bubbles: true, clientX: rect.left, clientY: rect.top }));
    }
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, []);

  return <ContextMenu.Root modal={false}>
    <ContextMenu.Trigger asChild ref={canvas}
      onContextMenuCapture={(event) => {
        // Keep native editing/link/image menus on those elements.
        if ((event.target as HTMLElement).closest("input, textarea, [contenteditable=true], a, img")) event.stopPropagation();
      }}
      onContextMenu={(event) => {
        const selection = window.getSelection();
        const selected = selectedCommentTarget(event.currentTarget, selection, steps);
        const element = (event.target as HTMLElement).closest<HTMLElement>("[data-step-content], [data-step-id]");
        const stepId = element?.dataset.stepContent ?? element?.dataset.stepId ?? null;
        setTarget(selected ?? { stepId, quote: null });
        setCopyText(selected ? selection!.toString() : "");
      }}
    >{children}</ContextMenu.Trigger>
    <ContextMenu.Portal>
      <ContextMenu.Content className="z-50 min-w-48 rounded-lg bg-popover p-1 text-popover-foreground shadow-md ring-1 ring-foreground/10" collisionPadding={8}
        onCloseAutoFocus={(event) => event.preventDefault()}>
        <ContextMenu.Item className={itemClass} onSelect={() => onComment(target)}>
          <MessageSquarePlus className="size-4" aria-hidden="true" />
          {target.quote ? "Comment on selection" : target.stepId ? "Comment on message" : "Comment on trace"}
        </ContextMenu.Item>
        {copyText && <ContextMenu.Item className={itemClass} onSelect={() => {
          void navigator.clipboard.writeText(copyText).catch(() => toast.error("Couldn’t copy the selected text."));
        }}><Copy className="size-4" aria-hidden="true" />Copy</ContextMenu.Item>}
      </ContextMenu.Content>
    </ContextMenu.Portal>
  </ContextMenu.Root>;
}
