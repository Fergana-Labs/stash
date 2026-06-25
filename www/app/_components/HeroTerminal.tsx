"use client";

import { useEffect, useRef, useState } from "react";

// The hero's centrepiece: real `stash` CLI commands typing themselves out.
// Honest (these are the actual commands) and on-brand (the product is
// CLI-native). Replaces the old blurry funnel PNG that read "vibe coded".

type Seg = { t: string; c?: string };
type Line = { kind: "cmd" | "out" | "comment" | "quote"; segs: Seg[] };

const SCRIPT: Line[] = [
  { kind: "cmd", segs: [{ t: "stash vfs", c: "w" }, { t: ' "ls /"' }] },
  { kind: "out", segs: [{ t: "files/  sessions/  skills/  tables/  sources/" }] },
  { kind: "cmd", segs: [{ t: "stash search", c: "w" }, { t: ' "rate-limit fix"' }] },
  {
    kind: "out",
    segs: [
      { t: "✓ 8 hits", c: "g" },
      { t: " · sessions/sam:tue-14:22 · files/gateway-limits.md" },
    ],
  },
  { kind: "cmd", segs: [{ t: "stash skills create", c: "w" }, { t: ' "auth-patterns" --public' }] },
  {
    kind: "out",
    segs: [{ t: "✓ published", c: "g" }, { t: " joinstash.ai/v/auth-patterns-q2" }],
  },
  { kind: "comment", segs: [{ t: "# claude · self-eval" }] },
  { kind: "quote", segs: [{ t: "finally — a place to put my receipts." }] },
];

const segText = (l: Line) => l.segs.map((s) => s.t).join("");

function colorClass(c?: string) {
  if (c === "w") return "text-white";
  if (c === "g") return "text-[#22C55E]";
  return "text-on-inverted-dim";
}

export default function HeroTerminal() {
  const [visible, setVisible] = useState(0); // fully-revealed lines
  const [typed, setTyped] = useState(0); // chars typed on the current cmd line
  const reduced = useRef(false);

  useEffect(() => {
    reduced.current =
      typeof window !== "undefined" &&
      window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (reduced.current) {
      setVisible(SCRIPT.length);
      return;
    }

    let timer: ReturnType<typeof setTimeout>;
    let line = 0;
    let chars = 0;

    const tick = () => {
      if (line >= SCRIPT.length) return;
      const current = SCRIPT[line];

      if (current.kind === "cmd" && chars < segText(current).length) {
        chars += 1;
        setTyped(chars);
        timer = setTimeout(tick, 34);
        return;
      }

      line += 1;
      chars = 0;
      setVisible(line);
      setTyped(0);
      const pause = current.kind === "cmd" ? 360 : 520;
      timer = setTimeout(tick, line >= SCRIPT.length ? 0 : pause);
    };

    timer = setTimeout(tick, 500);
    return () => clearTimeout(timer);
  }, []);

  const typingLine = visible < SCRIPT.length ? SCRIPT[visible] : null;
  const showCursor = visible >= SCRIPT.length;

  return (
    <div
      className="w-full overflow-hidden rounded-[16px] border border-white/5 bg-inverted"
      style={{ boxShadow: "var(--shadow-terminal)" }}
    >
      <div className="flex items-center justify-between border-b border-white/5 px-4 py-3">
        <div className="flex items-center gap-3">
          <div className="flex gap-1.5">
            <span className="h-2.5 w-2.5 rounded-full bg-white/10" />
            <span className="h-2.5 w-2.5 rounded-full bg-white/10" />
            <span className="h-2.5 w-2.5 rounded-full bg-white/10" />
          </div>
          <span className="font-mono text-[11px] font-medium uppercase tracking-[0.14em] text-on-inverted-dim">
            agent · claude-code
          </span>
        </div>
        <span className="font-mono text-[10.5px] uppercase tracking-[0.12em] text-on-inverted-dim">
          stash mcp
        </span>
      </div>

      <div className="min-h-[280px] overflow-x-auto px-5 py-5 font-mono text-[13px] leading-[1.85] text-on-inverted">
        {SCRIPT.slice(0, visible).map((l, i) => (
          <LineRow key={i} line={l} />
        ))}
        {typingLine && typingLine.kind === "cmd" ? (
          <PartialCmd line={typingLine} typed={typed} />
        ) : null}
        {showCursor ? (
          <div className="mt-2 whitespace-pre">
            <span className="mr-2.5 select-none text-brand">›</span>
            <span
              className="inline-block h-[14px] w-2 align-[-2px] bg-brand"
              style={{ animation: "cursor-blink 1.2s steps(2) infinite" }}
            />
          </div>
        ) : null}
      </div>
    </div>
  );
}

function LineRow({ line }: { line: Line }) {
  if (line.kind === "cmd") {
    return (
      <div className="whitespace-pre">
        <span className="mr-2.5 select-none text-brand">›</span>
        {line.segs.map((s, i) => (
          <span key={i} className={colorClass(s.c)}>
            {s.t}
          </span>
        ))}
      </div>
    );
  }
  if (line.kind === "comment") {
    return <div className="mt-3 whitespace-pre text-on-inverted-dim">{segText(line)}</div>;
  }
  if (line.kind === "quote") {
    return (
      <div className="whitespace-pre-wrap text-on-inverted-dim">
        <span className="text-brand">“</span>
        <span className="italic text-on-inverted">{segText(line)}</span>
        <span className="text-brand">”</span>
      </div>
    );
  }
  return (
    <div className="whitespace-pre-wrap">
      {line.segs.map((s, i) => (
        <span key={i} className={colorClass(s.c)}>
          {s.t}
        </span>
      ))}
    </div>
  );
}

function PartialCmd({ line, typed }: { line: Line; typed: number }) {
  // Offset of each segment within the full command string, computed purely so
  // the render never reassigns a captured variable (React Compiler rule).
  const offsetOf = (i: number) =>
    line.segs.slice(0, i).reduce((n, s) => n + s.t.length, 0);
  return (
    <div className="whitespace-pre">
      <span className="mr-2.5 select-none text-brand">›</span>
      {line.segs.map((s, i) => (
        <span key={i} className={colorClass(s.c)}>
          {s.t.slice(0, Math.max(0, typed - offsetOf(i)))}
        </span>
      ))}
      <span
        className="inline-block h-[14px] w-2 align-[-2px] bg-brand"
        style={{ animation: "cursor-blink 1.2s steps(2) infinite" }}
      />
    </div>
  );
}
