// Client for the page-events SSE stream (/pages/events). Lets an open page view
// react when an agent or another user edits a page on the backend. Uses
// fetch+ReadableStream (not EventSource) so it can send the Bearer token.

import { API_BASE, getToken } from "@/lib/api";

export type PageUpdateEvent = {
  type: "page.updated";
  page_id: string;
  content_hash: string | null;
  agent_name: string | null;
};

// Subscribe to a workspace's page-update stream. Returns an unsubscribe fn.
// Reconnects on drop with a short backoff until unsubscribed.
export function subscribePageEvents(
  workspaceId: string,
  onEvent: (event: PageUpdateEvent) => void,
): () => void {
  const controller = new AbortController();
  let stopped = false;

  async function run() {
    while (!stopped) {
      try {
        const res = await fetch(`${API_BASE}/api/v1/workspaces/${workspaceId}/pages/events`, {
          headers: { Authorization: `Bearer ${getToken() ?? ""}` },
          signal: controller.signal,
        });
        if (!res.ok || !res.body) throw new Error(`page events failed: ${res.status}`);
        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";
        for (;;) {
          const { done, value } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });
          const frames = buffer.split("\n\n");
          buffer = frames.pop() ?? "";
          for (const raw of frames) {
            const line = raw.trim();
            if (!line.startsWith("data:")) continue; // skip heartbeats / comments
            const payload = line.slice(5).trim();
            if (!payload) continue;
            try {
              onEvent(JSON.parse(payload) as PageUpdateEvent);
            } catch {
              // partial frame — resume next read
            }
          }
        }
      } catch {
        if (stopped) return;
      }
      // Stream ended or errored — wait briefly, then reconnect.
      if (!stopped) await new Promise((r) => setTimeout(r, 2000));
    }
  }

  run();
  return () => {
    stopped = true;
    controller.abort();
  };
}
