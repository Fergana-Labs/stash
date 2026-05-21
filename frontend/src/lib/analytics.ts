"use client";

// Batched product telemetry for the web app. Mirrors cli/telemetry.py:
// fire-and-forget, swallows network errors. Auth token read directly to
// avoid a circular import with ./api (which calls track() on some helpers).
const TOKEN_KEY = "stash_token";

function readToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(TOKEN_KEY);
}

type Event = {
  surface: "web";
  event_name: string;
  properties?: Record<string, unknown>;
};

const FLUSH_MS = 1000;
const MAX_BATCH = 20;

let queue: Event[] = [];
let timer: ReturnType<typeof setTimeout> | null = null;

function flush() {
  timer = null;
  if (queue.length === 0) return;
  const batch = queue.splice(0, MAX_BATCH);
  const token = readToken();
  if (!token) return; // unauth'd — drop. Onboarding always runs authed.
  fetch("/api/v1/analytics/events", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({ events: batch }),
    keepalive: true,
  }).catch(() => {});
  if (queue.length > 0) schedule();
}

function schedule() {
  if (timer !== null) return;
  timer = setTimeout(flush, FLUSH_MS);
}

export function track(
  event: string,
  properties?: Record<string, unknown>,
): void {
  if (typeof window === "undefined") return;
  queue.push({ surface: "web", event_name: event, properties });
  if (queue.length >= MAX_BATCH) flush();
  else schedule();
}

// Page-unload flush so the last events in a session aren't lost.
if (typeof window !== "undefined") {
  window.addEventListener("pagehide", () => flush());
}
