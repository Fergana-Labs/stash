// Extension-fed hydration: URLs the server can't fetch (login walls, IP
// blocks) land in a needs_client queue server-side; this module polls the
// queue, refetches each URL with the user's own browser session (cookies
// attach via the <all_urls> host permission), and posts the raw HTML back
// — article extraction stays server-side. Claims are lease-based
// (locked_at), so a worker killed mid-batch is retried in 10 minutes.

import { stashConfig, type StashConfig } from '../lib/stash';

const ALARM_NAME = 'import-fetch';
const POLL_PERIOD_MINUTES = 5;
const BATCH_LIMIT = 5;
const FETCH_TIMEOUT_MS = 30_000;
const INTER_FETCH_DELAY_MS = 1000;
const MAX_HTML_BYTES = 20 * 1024 * 1024;

export function initImportFetch(): void {
  chrome.runtime.onInstalled.addListener(schedule);
  chrome.runtime.onStartup.addListener(schedule);
  chrome.alarms.onAlarm.addListener((alarm) => {
    if (alarm.name === ALARM_NAME) void drainQueue();
  });
}

function schedule(): void {
  chrome.alarms.create(ALARM_NAME, { periodInMinutes: POLL_PERIOD_MINUTES });
}

let draining = false;

/** Fetch-and-report until the server's queue is empty. Also called outside
 * the alarm (import progress checks) — the flag keeps runs from overlapping. */
export async function drainQueue(): Promise<void> {
  if (draining) return;
  draining = true;
  try {
    const cfg = await stashConfig();
    if (!cfg.apiKey) return;
    for (;;) {
      const response = await fetch(
        `${cfg.apiBase}/api/v1/me/imports/client-queue?limit=${BATCH_LIMIT}`,
        { headers: { Authorization: `Bearer ${cfg.apiKey}` } }
      );
      if (!response.ok) return;
      const { items } = await response.json();
      if (!items.length) return;
      for (const item of items) {
        await fetchAndReport(cfg, item);
        await new Promise((r) => setTimeout(r, INTER_FETCH_DELAY_MS));
      }
    }
  } finally {
    draining = false;
  }
}

async function fetchAndReport(cfg: StashConfig, item: { id: string; url: string }): Promise<void> {
  let body: { html?: string; error?: string };
  try {
    const page = await fetch(item.url, {
      credentials: 'include',
      signal: AbortSignal.timeout(FETCH_TIMEOUT_MS),
    });
    if (!page.ok) {
      body = { error: `HTTP ${page.status}` };
    } else {
      const html = await page.text();
      body = html.length > MAX_HTML_BYTES ? { error: 'page larger than 20 MB' } : { html };
    }
  } catch (e: any) {
    body = { error: String(e?.message || e).slice(0, 200) };
  }
  await fetch(`${cfg.apiBase}/api/v1/me/imports/${item.id}/client-result`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${cfg.apiKey}`, 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
}
