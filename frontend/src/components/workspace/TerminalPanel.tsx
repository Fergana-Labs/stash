"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { getAuthToken } from "@/lib/api";

import "@xterm/xterm/css/xterm.css";

// A real shell on the user's cloud computer. The backend proxies this
// WebSocket to the machine, so closing the tab just drops the view — the
// box (and anything running on it) lives on.
export default function TerminalPanel() {
  const containerRef = useRef<HTMLDivElement>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const [state, setState] = useState<"connecting" | "open" | "closed">("connecting");
  const [generation, setGeneration] = useState(0);

  const reconnect = useCallback(() => setGeneration((g) => g + 1), []);

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;

    let disposed = false;
    let ws: WebSocket | null = null;
    let cleanup = () => {};

    (async () => {
      const [{ Terminal }, { FitAddon }, token] = await Promise.all([
        import("@xterm/xterm"),
        import("@xterm/addon-fit"),
        getAuthToken(),
      ]);
      if (disposed) return;

      const term = new Terminal({
        fontSize: 13,
        fontFamily: "var(--font-mono, monospace)",
        cursorBlink: true,
        theme: { background: "#0a0a0a" },
      });
      const fit = new FitAddon();
      term.loadAddon(fit);
      term.open(el);
      fit.fit();

      const proto = window.location.protocol === "https:" ? "wss" : "ws";
      const params = new URLSearchParams({
        token: token ?? "",
        cols: String(term.cols),
        rows: String(term.rows),
      });
      ws = new WebSocket(
        `${proto}://${window.location.host}/api/v1/me/machine/terminal?${params}`,
      );
      ws.binaryType = "arraybuffer";
      wsRef.current = ws;
      setState("connecting");

      ws.onopen = () => setState("open");
      ws.onclose = () => setState("closed");
      ws.onmessage = (e) => term.write(new Uint8Array(e.data as ArrayBuffer));

      const inputSub = term.onData((data) => {
        ws?.send(JSON.stringify({ type: "input", data }));
      });
      const resizeObserver = new ResizeObserver(() => {
        fit.fit();
        if (ws?.readyState === WebSocket.OPEN) {
          ws.send(JSON.stringify({ type: "resize", cols: term.cols, rows: term.rows }));
        }
      });
      resizeObserver.observe(el);

      cleanup = () => {
        inputSub.dispose();
        resizeObserver.disconnect();
        ws?.close();
        term.dispose();
      };
    })();

    return () => {
      disposed = true;
      cleanup();
      wsRef.current = null;
    };
  }, [generation]);

  return (
    <div className="relative flex h-full min-h-[520px] flex-col overflow-hidden rounded-xl border border-border bg-[#0a0a0a]">
      <div ref={containerRef} className="min-h-0 flex-1 p-2" />
      {state === "closed" && (
        <div className="absolute inset-x-0 bottom-0 flex items-center justify-between gap-3 border-t border-border bg-surface px-3 py-2 text-[12.5px] text-dim">
          <span>Disconnected from your computer.</span>
          <button
            type="button"
            onClick={reconnect}
            className="cursor-pointer rounded-md border border-border px-2.5 py-1 font-medium text-foreground hover:bg-raised"
          >
            Reconnect
          </button>
        </div>
      )}
    </div>
  );
}
