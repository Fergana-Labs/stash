"use client";

import { useEffect, useRef, useState, type RefObject } from "react";
import { MINIMAP_TONE_CLASS, minimapTone } from "./minimap";
import type { MessageTurn } from "./transcript";

// Blocks are laid out by message INDEX (block i spans i/count → (i+1)/count of
// the strip), not by rendered pixel height — collapsing or expanding a tool
// turn must not reshuffle the map. The lens is derived from which message
// elements are actually visible, so it stays honest as heights change.

interface LensRange {
  first: number;
  last: number;
}

export default function MinimapStrip({
  turns,
  loaded,
  scrollRef,
  matches,
  onJump,
}: {
  turns: MessageTurn[];
  // False while the full-transcript drain is still running; the strip shows a
  // placeholder until the whole session's shape is known.
  loaded: boolean;
  scrollRef: RefObject<HTMLDivElement | null>;
  // Turn indices matching the in-session search, shown as tick marks.
  matches: number[];
  onJump: (index: number) => void;
}) {
  const count = turns.length;
  const stripRef = useRef<HTMLDivElement>(null);
  const [lens, setLens] = useState<LensRange | null>(null);

  useEffect(() => {
    const container = scrollRef.current;
    if (!loaded || !container || count === 0) return;

    let raf = 0;
    const update = () => {
      raf = 0;
      setLens(visibleTurnRange(container, count));
    };
    const schedule = () => {
      if (!raf) raf = requestAnimationFrame(update);
    };

    schedule();
    container.addEventListener("scroll", schedule, { passive: true });
    // Expanding a tool turn changes content height without a scroll event;
    // watching the scroll content keeps the lens in step.
    const observer = new ResizeObserver(schedule);
    observer.observe(container);
    if (container.firstElementChild) observer.observe(container.firstElementChild);
    return () => {
      container.removeEventListener("scroll", schedule);
      observer.disconnect();
      if (raf) cancelAnimationFrame(raf);
    };
  }, [loaded, count, scrollRef]);

  const jumpToPointer = (e: React.PointerEvent) => {
    const strip = stripRef.current;
    if (!strip || count === 0) return;
    const rect = strip.getBoundingClientRect();
    const fraction = (e.clientY - rect.top) / rect.height;
    onJump(Math.min(count - 1, Math.max(0, Math.floor(fraction * count))));
  };

  return (
    <div className="w-5 shrink-0 px-[3px] py-2">
      {!loaded ? (
        <div className="h-full w-full animate-pulse rounded-sm bg-[var(--color-border)] opacity-60" />
      ) : (
        <div
          ref={stripRef}
          title="Jump to a point in the session"
          className="relative h-full w-full cursor-pointer touch-none select-none"
          onPointerDown={(e) => {
            e.preventDefault();
            e.currentTarget.setPointerCapture(e.pointerId);
            jumpToPointer(e);
          }}
          onPointerMove={(e) => {
            if (e.buttons & 1) jumpToPointer(e);
          }}
        >
          {turns.map((turn, i) => {
            const tone = minimapTone(turn);
            return (
              <div
                key={i}
                className={"absolute inset-x-0 " + MINIMAP_TONE_CLASS[tone]}
                style={{
                  top: `${(i / count) * 100}%`,
                  height: `${(1 / count) * 100}%`,
                  // Human turns are the landmarks: never let one vanish into a
                  // sub-pixel sliver in a long session.
                  minHeight: tone === "human" ? 3 : undefined,
                }}
              />
            );
          })}
          {matches.map((i) => (
            <div
              key={`match-${i}`}
              className="absolute left-[-3px] h-[2px] w-[3px] bg-[var(--color-brand-500)]"
              style={{ top: `${((i + 0.5) / count) * 100}%` }}
            />
          ))}
          {lens && (
            <div
              className="pointer-events-none absolute inset-x-[-3px] rounded-[2px] bg-foreground/10"
              style={{
                top: `${(lens.first / count) * 100}%`,
                height: `${((lens.last - lens.first + 1) / count) * 100}%`,
              }}
            />
          )}
        </div>
      )}
    </div>
  );
}

// First and last turn indices whose elements intersect the scroll viewport.
// Message elements are in document order, so their edges are monotonic and a
// binary search over bounding rects is enough (~2·log2(n) layout reads per
// scroll frame). Returns null if an element is missing — React has not
// committed the drained turns yet; the next scheduled update catches up.
function visibleTurnRange(container: HTMLElement, count: number): LensRange | null {
  const rect = container.getBoundingClientRect();

  let lo = 0;
  let hi = count - 1;
  while (lo < hi) {
    const mid = (lo + hi) >> 1;
    const el = document.getElementById(`turn-${mid}`);
    if (!el) return null;
    if (el.getBoundingClientRect().bottom <= rect.top) lo = mid + 1;
    else hi = mid;
  }
  const first = lo;

  hi = count - 1;
  while (lo < hi) {
    const mid = (lo + hi + 1) >> 1;
    const el = document.getElementById(`turn-${mid}`);
    if (!el) return null;
    if (el.getBoundingClientRect().top >= rect.bottom) hi = mid - 1;
    else lo = mid;
  }
  return { first, last: lo };
}
