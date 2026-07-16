// X bookmarks: capture bookmark links, push to Stash, daily auto-visit.
//
// The content scripts on x.com read the user's Bookmarks response whenever
// they visit the bookmarks page; a daily alarm also opens a background
// (non-active) tab to x.com/i/bookmarks so capture happens without a manual
// visit. We push only the tweet LINKS to POST /me/x-items — the server
// hydrates the full content, thread, and media from each link via
// ScrapeCreators, and get-or-creates the x_saves source on first push.

import { setBadge, stashConfig } from '../lib/stash';

const VISIT_ALARM = 'x-bookmarks-visit';
const VISIT_TIMEOUT_ALARM = 'x-bookmarks-visit-timeout';
const BOOKMARKS_URL = 'https://x.com/i/bookmarks';

export function initTwitter(): void {
  chrome.runtime.onInstalled.addListener(schedule);
  chrome.runtime.onStartup.addListener(schedule);
  chrome.alarms.onAlarm.addListener((alarm) => {
    if (alarm.name === VISIT_ALARM) void autoVisit();
    if (alarm.name === VISIT_TIMEOUT_ALARM) void visitTimedOut();
  });
}

function schedule(): void {
  chrome.alarms.create(VISIT_ALARM, { periodInMinutes: 24 * 60 });
}

export async function receiveBookmarks(
  ids: unknown[],
  sender: chrome.runtime.MessageSender
): Promise<any> {
  await chrome.storage.local.set({ xBookmarksFetchedAt: Date.now() });
  await closeVisitTab(sender.tab?.id);

  if (!Array.isArray(ids) || ids.length === 0) return { ok: true, new: 0 };
  const cfg = await stashConfig();
  if (!cfg.apiKey) return { ok: false, error: 'not_connected' };

  const items = ids.map((id) => ({ url: `https://x.com/i/status/${id}`, kind: 'Bookmark' }));
  const response = await fetch(`${cfg.apiBase}/api/v1/me/x-items`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${cfg.apiKey}`, 'Content-Type': 'application/json' },
    body: JSON.stringify({ items }),
  });
  if (!response.ok) {
    const detail = (await response.text()).slice(0, 180);
    await chrome.storage.local.set({
      lastError: `X bookmarks push failed (${response.status}): ${detail}`,
    });
    await setBadge('!', 'X bookmarks push failed — click for details');
    return { ok: false, error: `push_failed_${response.status}` };
  }
  const data = await response.json();
  await chrome.storage.local.set({ lastError: null });
  return { ok: true, ...data };
}

async function autoVisit(): Promise<void> {
  const { apiKey } = await chrome.storage.local.get(['apiKey']);
  if (!apiKey) return;
  const tab = await chrome.tabs.create({ url: BOOKMARKS_URL, active: false });
  await chrome.storage.session.set({ xVisitTabId: tab.id });
  chrome.alarms.create(VISIT_TIMEOUT_ALARM, { delayInMinutes: 2 });
}

/** "Sync now" for X: open the bookmarks page in the background and harvest. */
export async function syncXNow(): Promise<{ ok: boolean }> {
  await autoVisit();
  return { ok: true };
}

export async function xLastSyncAt(): Promise<number | null> {
  const { xBookmarksFetchedAt } = await chrome.storage.local.get(['xBookmarksFetchedAt']);
  return xBookmarksFetchedAt || null;
}

async function visitTimedOut(): Promise<void> {
  const { xVisitTabId } = await chrome.storage.session.get(['xVisitTabId']);
  if (xVisitTabId == null) return;
  await chrome.storage.session.remove(['xVisitTabId']);
  await chrome.tabs.remove(xVisitTabId).catch(() => undefined);
  await chrome.storage.local.set({
    lastError: 'X bookmarks harvest timed out — are you signed in to x.com?',
  });
  await setBadge('!', 'X bookmarks harvest timed out — click for details');
}

async function closeVisitTab(senderTabId: number | undefined): Promise<void> {
  if (senderTabId == null) return;
  const { xVisitTabId } = await chrome.storage.session.get(['xVisitTabId']);
  if (xVisitTabId !== senderTabId) return;
  await chrome.storage.session.remove(['xVisitTabId']);
  chrome.alarms.clear(VISIT_TIMEOUT_ALARM);
  await chrome.tabs.remove(senderTabId).catch(() => undefined);
}
