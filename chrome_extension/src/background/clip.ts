// Web clipper: context menu / popup button → inject clipper.ts into the
// tab (activeTab grant) → CLIP_PAGE lands here and uploads. Pages Chrome
// won't inject into (its PDF viewer, chrome:// pages) take the direct
// byte-fetch path instead. Bulk imports (clip-all-tabs, bookmarks.html)
// also run here so credentials stay in the worker.

import { clearSurfaceError, setSurfaceError } from '../lib/errors';
import { flashOkBadge, setBadge, stashConfig } from '../lib/stash';
import { drainQueue } from './import_fetch';

// Must be an absolute extension URL. A relative path resolves against the
// service worker's own location — dist/ — so 'icons/icon128.png' asks for
// dist/icons/icon128.png, and chrome.notifications rejects the whole call
// with "Unable to download all specified images".
const NOTIFICATION_ICON = chrome.runtime.getURL('icons/icon128.png');

// While a bulk import is running, a periodic alarm keeps the action badge
// showing the remaining count and fires one OS notification the moment the
// import finishes — a days-long 41k grind gets a visible "done".
const IMPORT_WATCH_ALARM = 'stash-import-watch';

export function initImportWatch(): void {
  chrome.alarms.onAlarm.addListener((alarm) => {
    if (alarm.name === IMPORT_WATCH_ALARM) void watchImport();
  });
  void watchImport(); // resume after a worker restart mid-import
}

async function watchImport(): Promise<void> {
  const { lastImport } = await chrome.storage.local.get('lastImport');
  if (!lastImport?.id || lastImport.doneNotified) {
    await chrome.alarms.clear(IMPORT_WATCH_ALARM);
    return;
  }
  const result = await importProgress(lastImport.id);
  if (!result?.ok) return; // transient (offline, auth blip) — next alarm retries
  const p = result.progress;
  const remaining = p.pending + p.needs_client;
  if (remaining > 0) {
    await chrome.action.setBadgeText({ text: compactCount(remaining) });
    await chrome.action.setBadgeBackgroundColor({ color: '#6366f1' });
    await chrome.action.setTitle({ title: `Stash import: ${remaining} of ${p.total} remaining` });
    chrome.alarms.create(IMPORT_WATCH_ALARM, { periodInMinutes: 5 });
    return;
  }
  await chrome.alarms.clear(IMPORT_WATCH_ALARM);
  await setBadge('', 'Stash');
  chrome.notifications.create({
    type: 'basic',
    iconUrl: NOTIFICATION_ICON,
    title: 'Stash import finished',
    message:
      `${p.done} of ${p.total} saved` +
      (p.link_only > 0 ? `; ${p.link_only} kept as link-only (content unavailable).` : '.'),
  });
  await chrome.storage.local.set({ lastImport: { ...lastImport, doneNotified: true } });
}

function compactCount(n: number): string {
  return n >= 1000 ? `${Math.floor(n / 1000)}k` : String(n);
}

export interface PageClip {
  url: string;
  title: string;
  html: string;
  capturedAt: string;
}

export function initClipper(): void {
  // Context menus persist across browser sessions and service-worker restarts,
  // so onInstalled is the only place to (re)create them. Registering on
  // onStartup too made two removeAll→create calls race, and the loser hit an
  // already-created id ("Cannot create item with duplicate id stash-clip").
  chrome.runtime.onInstalled.addListener(createMenu);
  chrome.contextMenus.onClicked.addListener((info, tab) => {
    if (info.menuItemId === 'stash-clip' && tab?.id != null) void clipTab(tab);
  });
}

function createMenu(): void {
  chrome.contextMenus.removeAll(() => {
    chrome.contextMenus.create({
      id: 'stash-clip',
      title: 'Save page to Stash',
      contexts: ['page'],
    });
  });
}

export async function clipActiveTab(): Promise<any> {
  const [tab] = await chrome.tabs.query({ active: true, lastFocusedWindow: true });
  if (!tab) return clipFailed('unknown', 'No active tab');
  return clipTab(tab);
}

async function clipTab(tab: chrome.tabs.Tab): Promise<any> {
  try {
    await chrome.scripting.executeScript({
      target: { tabId: tab.id! },
      files: ['dist/clipper.js'],
    });
    // The injected script reports back via CLIP_PAGE.
    return { ok: true, started: true };
  } catch {
    // Injection is impossible in Chrome's PDF viewer — this is the PDF
    // dispatch, not a fallback: fetch the bytes directly (activeTab covers
    // the origin, credentials included for auth-gated PDFs).
    return clipPdf(tab);
  }
}

async function clipPdf(tab: chrome.tabs.Tab): Promise<any> {
  const url = tab.url || '';
  const response = await fetch(url, { credentials: 'include' });
  const contentType = response.headers.get('content-type') || '';
  if (!response.ok || !contentType.includes('application/pdf')) {
    return clipFailed(
      url,
      `Not a clippable page (status ${response.status}, ${contentType || 'unknown type'})`
    );
  }
  const cfg = await stashConfig();
  if (!cfg.apiKey) return notConnected();

  let filename = new URL(url).pathname.split('/').pop() || 'clip';
  if (!filename.toLowerCase().endsWith('.pdf')) filename = `${filename}.pdf`;
  const form = new FormData();
  form.append('file', await response.blob(), filename);
  form.append('url', url);

  const upload = await fetch(`${cfg.apiBase}/api/v1/me/clips/file`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${cfg.apiKey}` },
    body: form,
  });
  if (!upload.ok) {
    return clipFailed(url, `Upload failed (${upload.status}): ${(await upload.text()).slice(0, 180)}`);
  }
  const data = await upload.json();
  return clipSucceeded({ title: data.name, appUrl: data.app_url });
}

export async function uploadPageClip(clip: PageClip): Promise<any> {
  const cfg = await stashConfig();
  if (!cfg.apiKey) return notConnected();

  const response = await fetch(`${cfg.apiBase}/api/v1/me/clips/page`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${cfg.apiKey}`, 'Content-Type': 'application/json' },
    body: JSON.stringify({ url: clip.url, html: clip.html, title: clip.title }),
  });
  if (response.status === 202) {
    // YouTube/arXiv: the server fetches out-of-band (transcript, paper PDF).
    const { import_id } = await response.json();
    return clipSucceeded({ title: clip.title, importId: import_id });
  }
  if (!response.ok) {
    let detail = (await response.text()).slice(0, 180);
    try {
      detail = JSON.parse(detail).detail ?? detail;
    } catch {
      // not JSON — keep the raw body
    }
    return clipFailed(clip.url, `(${response.status}) ${detail}`);
  }
  const data = await response.json();
  return clipSucceeded({ title: data.name, appUrl: data.app_url });
}

async function clipSucceeded(clip: {
  title: string;
  appUrl?: string;
  importId?: string;
}): Promise<any> {
  await chrome.storage.local.set({ lastClip: { ...clip, at: Date.now() } });
  await clearSurfaceError('clip');
  await flashOkBadge(`Saved "${clip.title}" to Stash`);
  // The badge alone isn't enough confirmation: a context-menu save has no
  // popup open, and a popup save covers the toolbar icon the badge sits on.
  chrome.notifications.create({
    type: 'basic',
    iconUrl: NOTIFICATION_ICON,
    title: 'Saved to Stash',
    message: clip.title,
  });
  return { ok: true, clip };
}

async function clipFailed(url: string, error: string): Promise<any> {
  await setSurfaceError('clip', `Clip failed: ${error}`);
  await setBadge('!', 'Stash clip failed — click for details');
  chrome.notifications.create({
    type: 'basic',
    iconUrl: NOTIFICATION_ICON,
    title: 'Stash clip failed',
    message: error.slice(0, 180),
  });
  return { ok: false, error };
}

async function notConnected(): Promise<any> {
  await setBadge('!', 'Not connected to Stash — click to sign in');
  return { ok: false, error: 'not_connected' };
}

// ---------------------------------------------------------------------------
// Bulk imports (clip-all-tabs, bookmarks.html)
// ---------------------------------------------------------------------------

// The popup labels its button with this count, so it has to be the same set
// clipAllTabs will actually send — chrome:// and extension pages can't be
// clipped, and promising to save them would be a lie on the button face.
export async function clippableTabUrls(): Promise<string[]> {
  const tabs = await chrome.tabs.query({ lastFocusedWindow: true });
  return tabs.map((t) => t.url).filter((u): u is string => Boolean(u && /^https?:/.test(u)));
}

export async function clipAllTabs(): Promise<any> {
  const cfg = await stashConfig();
  if (!cfg.apiKey) return notConnected();

  const urls = await clippableTabUrls();
  if (urls.length === 0) return { ok: false, error: 'No clippable tabs' };

  const response = await fetch(`${cfg.apiBase}/api/v1/me/imports/tabs`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${cfg.apiKey}`, 'Content-Type': 'application/json' },
    body: JSON.stringify({ urls }),
  });
  if (!response.ok) {
    return clipFailed('tabs', `(${response.status}) ${(await response.text()).slice(0, 180)}`);
  }
  const data = await response.json();
  if (data.total === 0) return nothingNew(data.skipped, 'tabs');

  await chrome.storage.local.set({ lastImport: { id: data.import_id, kind: 'tabs' } });
  void watchImport();
  notifySaved(data.total, data.skipped);
  return { ok: true, importId: data.import_id, total: data.total, skipped: data.skipped };
}

// Saving a link and capturing its contents are two different things finishing
// at two different times. The link is already durable when this fires; only
// the page text is still coming.
function notifySaved(total: number, skipped: number): void {
  chrome.notifications.create({
    type: 'basic',
    iconUrl: NOTIFICATION_ICON,
    title: `${total} link${total === 1 ? '' : 's'} saved to Stash`,
    message: `Downloading page contents now${skippedNote(skipped)}.`,
  });
}

// Every URL was already imported. There is no batch to watch and nothing to
// download, so saying "0 saved" and pointing at a progress bar is just wrong.
function nothingNew(skipped: number, noun: string): any {
  chrome.notifications.create({
    type: 'basic',
    iconUrl: NOTIFICATION_ICON,
    title: 'Nothing new to save',
    message: `All ${skipped} ${noun} are already in your Stash.`,
  });
  return { ok: true, importId: null, total: 0, skipped };
}

function skippedNote(skipped: number): string {
  return skipped > 0 ? ` (${skipped} already in your Stash)` : '';
}

export async function importBookmarks(name: string, content: string): Promise<any> {
  const cfg = await stashConfig();
  if (!cfg.apiKey) return notConnected();

  const form = new FormData();
  form.append('file', new Blob([content], { type: 'text/html' }), name || 'bookmarks.html');
  const response = await fetch(`${cfg.apiBase}/api/v1/me/imports/bookmarks`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${cfg.apiKey}` },
    body: form,
  });
  if (!response.ok) {
    let detail = (await response.text()).slice(0, 180);
    try {
      detail = JSON.parse(detail).detail ?? detail;
    } catch {
      // not JSON — keep the raw body
    }
    return { ok: false, error: `Import failed (${response.status}): ${detail}` };
  }
  const data = await response.json();
  if (data.total === 0) return nothingNew(data.skipped, 'bookmarks');

  await chrome.storage.local.set({ lastImport: { id: data.import_id, kind: 'bookmarks' } });
  void watchImport();
  notifySaved(data.total, data.skipped);
  return { ok: true, importId: data.import_id, total: data.total, skipped: data.skipped };
}

export async function importProgress(importId: string): Promise<any> {
  const cfg = await stashConfig();
  if (!cfg.apiKey) return notConnected();
  const response = await fetch(`${cfg.apiBase}/api/v1/me/imports/${importId}`, {
    headers: { Authorization: `Bearer ${cfg.apiKey}` },
  });
  if (!response.ok) return { ok: false, error: `Progress check failed (${response.status})` };
  const progress = await response.json();
  if (progress.needs_client > 0) {
    // Rows are waiting on this browser's session — no need to wait for the
    // next 5-minute alarm.
    void drainQueue();
  }
  return { ok: true, progress };
}
