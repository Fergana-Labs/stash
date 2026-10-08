"use client";

import { useEffect, useId, useRef, useState, type KeyboardEvent, type PointerEvent, type RefObject } from "react";
import { cn } from "@/lib/utils";

export interface ConversationMarker {
  targetId: string;
  title: string;
  preview: string;
  label: string;
  emphasis?: boolean;
}

/** A plain-text excerpt: previews never render links, images, or trace HTML. */
export function conversationExcerpt(text: string, limit = 240): string {
  const plain = text.replace(/!\[([^\]]*)\]\([^)]*\)/g, "$1")
    .replace(/\[([^\]]+)\]\([^)]*\)/g, "$1")
    .replace(/(^|\n)\s{0,3}#{1,6}\s+/g, "$1")
    .replace(/[*_`]/g, "").replace(/\s+/g, " ").trim();
  return plain.length > limit ? `${plain.slice(0, limit).trimEnd()}…` : plain;
}

/** One marker per exchange; assistant-only transcripts still have destinations. */
export function conversationMarkers(messages: { targetId: string; role: string; content: string }[]): ConversationMarker[] {
  const markers: ConversationMarker[] = [];
  let prompt: ConversationMarker | null = null;
  for (const message of messages) {
    if (message.role === "user") {
      prompt = {
        targetId: message.targetId,
        title: conversationExcerpt(message.content, 120) || "User message",
        preview: "",
        label: `Message ${markers.length + 1}`,
        emphasis: true,
      };
      markers.push(prompt);
    } else if (message.role === "assistant" && message.content.trim()) {
      if (prompt) {
        if (!prompt.preview) prompt.preview = conversationExcerpt(message.content);
      } else {
        markers.push({ targetId: message.targetId, title: "Assistant", preview: conversationExcerpt(message.content), label: `Message ${markers.length + 1}` });
      }
    }
  }
  return markers;
}

/** Lives beside (not inside) the scroller so the rail stays put in long chats. */
export default function ConversationScrollRail({ items, scroller, header, onJump }: {
  items: ConversationMarker[];
  scroller: RefObject<HTMLDivElement | null>;
  header?: RefObject<HTMLDivElement | null>;
  onJump?: (item: ConversationMarker) => void;
}) {
  const [activeIndex, setActiveIndex] = useState(0);
  const [previewIndex, setPreviewIndex] = useState<number | null>(null);
  const rail = useRef<HTMLElement>(null);
  const drag = useRef<{ pointerId: number; index: number } | null>(null);
  const tooltipId = useId();

  useEffect(() => {
    const container = scroller.current;
    if (!container || items.length < 2) return;
    let frame = 0;
    let positions: { index: number; top: number }[] = [];
    const targets = items.map((item, index) => ({
      index, element: container.querySelector<HTMLElement>(`#${CSS.escape(item.targetId)}`),
    }));
    function update() {
      const top = container!.scrollTop + (header?.current?.offsetHeight ?? 0) + 24;
      let index = positions[0]?.index ?? 0;
      for (const position of positions) {
        if (position.top > top) break;
        index = position.index;
      }
      if (container!.scrollHeight > container!.clientHeight && container!.scrollHeight - container!.scrollTop - container!.clientHeight < 2) {
        index = positions.at(-1)?.index ?? index;
      }
      setActiveIndex(index);
    }
    function measure() {
      const origin = container!.getBoundingClientRect().top - container!.scrollTop;
      positions = targets.flatMap(({ index, element }) => element && element.getClientRects().length
        ? [{ index, top: element.getBoundingClientRect().top - origin }] : []);
      update();
    }
    function schedule() {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(update);
    }
    const observer = new ResizeObserver(measure);
    observer.observe(container);
    if (container.firstElementChild) observer.observe(container.firstElementChild);
    if (header?.current) observer.observe(header.current);
    targets.forEach(({ element }) => { if (element) observer.observe(element); });
    container.addEventListener("scroll", schedule, { passive: true });
    measure();
    return () => {
      cancelAnimationFrame(frame);
      observer.disconnect();
      container.removeEventListener("scroll", schedule);
    };
  }, [items, scroller, header]);

  if (items.length < 2) return null;

  function jump(index: number, scrubbing = false) {
    const item = items[index];
    if (onJump) onJump(item);
    else {
      const container = scroller.current;
      const target = container?.querySelector<HTMLElement>(`#${CSS.escape(item.targetId)}`);
      if (container && target) {
        container.scrollTo({
          top: container.scrollTop + target.getBoundingClientRect().top - container.getBoundingClientRect().top - (header?.current?.offsetHeight ?? 0) - 12,
          behavior: scrubbing || window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "instant" : "smooth",
        });
      }
    }
    setActiveIndex(index);
  }

  function indexAt(event: PointerEvent<HTMLDivElement>) {
    const bounds = event.currentTarget.getBoundingClientRect();
    return Math.max(0, Math.min(items.length - 1, Math.floor((event.clientY - bounds.top) / bounds.height * items.length)));
  }

  function scrub(index: number) {
    setPreviewIndex(index);
    rail.current?.querySelectorAll<HTMLButtonElement>("button")[index]?.focus({ preventScroll: true });
    jump(index, true);
  }

  function endDrag(event: PointerEvent<HTMLDivElement>) {
    if (drag.current?.pointerId !== event.pointerId) return;
    drag.current = null;
    if (event.currentTarget.hasPointerCapture(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId);
    const bounds = event.currentTarget.getBoundingClientRect();
    if (event.type !== "pointerup" || event.pointerType === "touch" || event.clientX < bounds.left || event.clientX > bounds.right || event.clientY < bounds.top || event.clientY > bounds.bottom) {
      setPreviewIndex(null);
    }
  }

  function onKeyDown(event: KeyboardEvent<HTMLButtonElement>, index: number) {
    if (event.key === "Escape") { setPreviewIndex(null); return; }
    const next = event.key === "ArrowDown" ? Math.min(items.length - 1, index + 1)
      : event.key === "ArrowUp" ? Math.max(0, index - 1)
      : event.key === "Home" ? 0 : event.key === "End" ? items.length - 1 : null;
    if (next === null) return;
    event.preventDefault();
    rail.current?.querySelectorAll<HTMLButtonElement>("button")[next]?.focus();
  }

  const preview = previewIndex === null ? null : items[previewIndex];
  const fraction = previewIndex === null ? 0 : (previewIndex + 0.5) / items.length;
  return (
    <nav ref={rail} aria-label="Conversation navigation" className="relative z-30 w-8 shrink-0 py-6"
      onMouseLeave={() => setPreviewIndex(null)} onBlur={(event) => {
        if (!event.currentTarget.contains(event.relatedTarget)) setPreviewIndex(null);
      }}>
      <div className="flex h-full max-h-full flex-col justify-center">
        <div className="relative flex min-h-0 touch-none select-none flex-col" style={{ height: items.length * 14, maxHeight: "100%" }}
          role="group" aria-label="Conversation scrubber"
          onPointerDown={(event) => {
            if (event.button !== 0 || drag.current !== null) return;
            event.preventDefault();
            const index = indexAt(event);
            drag.current = { pointerId: event.pointerId, index };
            event.currentTarget.setPointerCapture(event.pointerId);
            scrub(index);
          }}
          onPointerMove={(event) => {
            if (drag.current?.pointerId !== event.pointerId) return;
            const index = indexAt(event);
            if (index === drag.current.index) return;
            drag.current.index = index;
            scrub(index);
          }}
          onPointerUp={endDrag} onPointerCancel={endDrag} onLostPointerCapture={endDrag}>
          {items.map((item, index) => (
            <button key={item.targetId} type="button" aria-label={`${item.label}: ${item.title}`}
              aria-current={index === activeIndex ? "location" : undefined}
              aria-describedby={previewIndex === index ? tooltipId : undefined}
              tabIndex={index === activeIndex ? 0 : -1}
              onMouseEnter={() => setPreviewIndex(index)} onFocus={() => setPreviewIndex(index)}
              onClick={(event) => { if (event.detail === 0) jump(index); }} onKeyDown={(event) => onKeyDown(event, index)}
              className="group flex min-h-0 flex-1 cursor-pointer items-center px-2 outline-none focus-visible:rounded-sm focus-visible:ring-2 focus-visible:ring-brand-400">
              <span aria-hidden="true" className={cn("block h-[2px] shrink-0 rounded-full transition-[width,background-color] duration-150 motion-reduce:transition-none",
                index === activeIndex || previewIndex === index ? "w-5 bg-foreground" : item.emphasis ? "w-3 bg-muted-foreground/45 group-hover:w-5" : "w-2 bg-muted-foreground/30 group-hover:w-5")} />
            </button>
          ))}
          {preview && <div id={tooltipId} role="tooltip"
            className="pointer-events-none absolute left-full ml-2 w-72 max-w-[calc(100vw-5rem)] rounded-xl border border-border bg-base p-3 text-left shadow-lg"
            style={{ top: `${fraction * 100}%`, transform: `translateY(-${fraction * 100}%)` }}>
            <div className="mb-1 text-[10px] text-muted-foreground">{preview.label}</div>
            <div className="line-clamp-2 break-words text-[13px] font-medium leading-5 text-foreground">{preview.title}</div>
            {preview.preview && <p className="m-0 mt-1.5 line-clamp-4 break-words text-[12px] leading-5 text-dim">{preview.preview}</p>}
          </div>}
        </div>
      </div>
    </nav>
  );
}
