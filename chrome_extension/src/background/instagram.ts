// Instagram saves: throttle + upload + daily auto-visit.
//
// The content script harvests the saved-posts list whenever the user is on
// instagram.com and the 24h throttle allows; a daily alarm additionally
// opens a background (non-active) tab to instagram.com so capture happens
// even when the user hasn't visited. The pushed URLs go to
// POST /me/saved-items, which auto-creates the source and hydrates
// server-side.

import { clearSurfaceError, setSurfaceError } from '../lib/errors';
import { setBadge, stashConfig } from '../lib/stash';

const VISIT_ALARM = 'instagram-saves-visit';
const VISIT_TIMEOUT_ALARM = 'instagram-saves-visit-timeout';
const HARVEST_INTERVAL_MS = 24 * 60 * 60 * 1000;

export function initInstagram(): void {
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

export async function shouldFetchSaves(): Promise<any> {
  const { apiKey } = await chrome.storage.local.get(['apiKey']);
  if (!apiKey) return { fetch: false };
  const { igFetchedAt } = await chrome.storage.local.get(['igFetchedAt']);
  return { fetch: !igFetchedAt || Date.now() - igFetchedAt > HARVEST_INTERVAL_MS };
}

export async function receiveSavedItems(
  items: { url: string }[],
  sender: chrome.runtime.MessageSender
): Promise<any> {
  await chrome.storage.local.set({ igFetchedAt: Date.now() });
  await closeVisitTab(sender.tab?.id);

  if (items.length === 0) return { ok: true, new: 0 };
  const cfg = await stashConfig();
  if (!cfg.apiKey) return { ok: false, error: 'not_connected' };

  const response = await fetch(`${cfg.apiBase}/api/v1/me/saved-items`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${cfg.apiKey}`, 'Content-Type': 'application/json' },
    body: JSON.stringify({ platform: 'instagram', items }),
  });
  if (!response.ok) {
    const detail = (await response.text()).slice(0, 180);
    await setSurfaceError(
      'instagram',
      `Instagram saves push failed (${response.status}): ${detail}`
    );
    await setBadge('!', 'Instagram saves push failed — click for details');
    return { ok: false, error: `push_failed_${response.status}` };
  }
  const data = await response.json();
  await clearSurfaceError('instagram');
  return { ok: true, ...data };
}

export async function savedItemsFailed(
  error: string,
  sender: chrome.runtime.MessageSender
): Promise<any> {
  await closeVisitTab(sender.tab?.id);
  await setSurfaceError('instagram', `Instagram saves harvest failed: ${error}`);
  await setBadge('!', 'Instagram saves harvest failed — click for details');
  return { ok: false, error };
}

async function autoVisit(): Promise<void> {
  const { fetch: due } = await shouldFetchSaves();
  if (!due) return;
  await openVisitTab();
}

async function openVisitTab(): Promise<void> {
  const { apiKey } = await chrome.storage.local.get(['apiKey']);
  if (!apiKey) return;
  const tab = await chrome.tabs.create({ url: 'https://www.instagram.com/', active: false });
  await chrome.storage.session.set({ igVisitTabId: tab.id });
  chrome.alarms.create(VISIT_TIMEOUT_ALARM, { delayInMinutes: 2 });
}

/** "Sync now" for Instagram: open the site in the background and harvest
 *  saves immediately, ignoring the daily throttle. */
export async function syncInstagramNow(): Promise<{ ok: boolean }> {
  await openVisitTab();
  return { ok: true };
}

export async function instagramLastSyncAt(): Promise<number | null> {
  const { igFetchedAt } = await chrome.storage.local.get(['igFetchedAt']);
  return igFetchedAt || null;
}

async function visitTimedOut(): Promise<void> {
  const { igVisitTabId } = await chrome.storage.session.get(['igVisitTabId']);
  if (igVisitTabId == null) return;
  await chrome.storage.session.remove(['igVisitTabId']);
  await chrome.tabs.remove(igVisitTabId).catch(() => undefined);
  await setSurfaceError(
    'instagram',
    'Instagram saves harvest timed out — are you signed in to instagram.com?'
  );
  await setBadge('!', 'Instagram saves harvest timed out — click for details');
}

async function closeVisitTab(senderTabId: number | undefined): Promise<void> {
  if (senderTabId == null) return;
  const { igVisitTabId } = await chrome.storage.session.get(['igVisitTabId']);
  if (igVisitTabId !== senderTabId) return;
  await chrome.storage.session.remove(['igVisitTabId']);
  chrome.alarms.clear(VISIT_TIMEOUT_ALARM);
  await chrome.tabs.remove(senderTabId).catch(() => undefined);
}
