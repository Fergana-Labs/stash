// Background service worker: owns the Stash credentials and does all
// backend I/O. Content scripts send conversation snapshots here; we skip
// unchanged ones (content hash, kept in session storage) and upload the
// rest as replace-mode transcripts so a growing chat keeps updating the
// same Stash session.

import { initChatPoll } from './background/chat_poll';
import {
  clipActiveTab,
  clipAllTabs,
  importBookmarks,
  importProgress,
  initClipper,
  uploadPageClip,
} from './background/clip';
import type { ConversationSnapshot } from './content/sync';

const DEFAULT_API_BASE = 'https://api.joinstash.ai';

initClipper();
initChatPoll(syncConversation);
// Auth sessions live 15 min server-side. The poll loop covers most of that,
// and checkPendingConnect() collects an approval that lands after the loop
// gave up (e.g. MV3 suspended the worker mid-wait).
const CONNECT_POLL_TIMEOUT_MS = 600_000;

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  handle(message)
    .then(sendResponse)
    .catch((e) => sendResponse({ ok: false, error: String(e?.message || e) }));
  return true;
});

async function handle(message: any): Promise<any> {
  switch (message.type) {
    case 'SYNC_CONVERSATION':
      return syncConversation(message.snapshot);
    case 'CLIP_TAB':
      return clipActiveTab();
    case 'CLIP_PAGE':
      return uploadPageClip(message.clip);
    case 'CLIP_ALL_TABS':
      return clipAllTabs();
    case 'IMPORT_BOOKMARKS':
      return importBookmarks(message.name, message.content);
    case 'IMPORT_PROGRESS':
      return importProgress(message.id);
    case 'CONNECT':
      return connect();
    case 'DISCONNECT':
      await chrome.storage.local.remove(['apiKey', 'username', 'folderId', 'folderName', 'folders', 'lastSync', 'lastClip', 'lastImport', 'lastError']);
      return { ok: true };
    case 'GET_STATUS':
      return getStatus();
    case 'SET_FOLDER':
      await chrome.storage.local.set({ folderId: message.id, folderName: message.name });
      return { ok: true };
    case 'SET_API_BASE':
      // Changing backends invalidates the key, folders, and dedup state.
      await chrome.storage.local.clear();
      await chrome.storage.session.clear();
      await chrome.storage.local.set({ apiBase: message.apiBase });
      return { ok: true };
    default:
      return { ok: false, error: `Unknown message type: ${message.type}` };
  }
}

// ---------------------------------------------------------------------------
// Sync
// ---------------------------------------------------------------------------

async function syncConversation(snapshot: ConversationSnapshot): Promise<any> {
  const cfg = await chrome.storage.local.get(['apiBase', 'apiKey', 'folderId']);
  if (!cfg.apiKey) {
    await setBadge('!', 'Not connected to Stash — click to sign in');
    return { ok: false, error: 'not_connected' };
  }

  const sessionId = `${snapshot.platform}-${snapshot.conversationId}`;
  const jsonl = snapshot.lines.map((l) => JSON.stringify(l)).join('\n');
  const hash = await sha256(jsonl);

  const hashKey = `hash:${sessionId}`;
  const prev = await chrome.storage.session.get(hashKey);
  if (prev[hashKey] === hash) {
    return { ok: true, skipped: true };
  }

  const apiBase = cfg.apiBase || DEFAULT_API_BASE;

  // Upsert the session into the chosen folder before uploading events.
  // The transcript endpoint's own upsert doesn't assign a folder; this one
  // does (the backend falls back to the user's Default folder when folderId
  // is unset). A folder is only set once server-side, so manual re-homing in
  // the app sticks across later syncs.
  const upsert = await fetch(`${apiBase}/api/v1/me/sessions`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${cfg.apiKey}`, 'Content-Type': 'application/json' },
    body: JSON.stringify({
      session_id: sessionId,
      agent_name: snapshot.platform,
      ...(cfg.folderId ? { session_folder_id: cfg.folderId } : {}),
    }),
  });
  if (!upsert.ok) {
    const detail = (await upsert.text()).slice(0, 200);
    await chrome.storage.local.set({ lastError: `Session upsert failed (${upsert.status}): ${detail}` });
    await setBadge('!', `Stash sync failing (${upsert.status}) — click for details`);
    return { ok: false, error: `upsert_failed_${upsert.status}` };
  }

  const form = new FormData();
  form.append('file', new Blob([jsonl], { type: 'application/jsonl' }), `${sessionId}.jsonl`);
  form.append('session_id', sessionId);
  form.append('agent_name', snapshot.platform);
  form.append('replace', 'true');

  const res = await fetch(`${apiBase}/api/v1/me/transcripts`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${cfg.apiKey}` },
    body: form,
  });
  if (!res.ok) {
    const detail = (await res.text()).slice(0, 200);
    await chrome.storage.local.set({ lastError: `Upload failed (${res.status}): ${detail}` });
    await setBadge('!', `Stash sync failing (${res.status}) — click for details`);
    return { ok: false, error: `upload_failed_${res.status}` };
  }

  await chrome.storage.session.set({ [hashKey]: hash });
  await chrome.storage.local.set({
    lastSync: { title: snapshot.title, sessionId, at: Date.now() },
    lastError: null,
  });
  await setBadge('', 'Stash Chat Sync');
  return { ok: true };
}

async function sha256(text: string): Promise<string> {
  const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(text));
  return Array.from(new Uint8Array(digest))
    .map((b) => b.toString(16).padStart(2, '0'))
    .join('');
}

async function setBadge(text: string, title: string): Promise<void> {
  await chrome.action.setBadgeText({ text });
  if (text) await chrome.action.setBadgeBackgroundColor({ color: '#ef4444' });
  await chrome.action.setTitle({ title });
}

// ---------------------------------------------------------------------------
// Connect (same device-auth flow the stash CLI uses)
// ---------------------------------------------------------------------------

function signinPage(apiBase: string): string {
  const api = apiBase.replace(/\/$/, '');
  if (api === 'https://api.joinstash.ai') return 'https://joinstash.ai/connect-token';
  if (api.includes('localhost') || api.includes('127.0.0.1')) {
    return api.replace(':3456', ':3457') + '/connect-token';
  }
  return api + '/connect-token';
}

async function connect(): Promise<any> {
  const cfg = await chrome.storage.local.get(['apiBase']);
  const apiBase = cfg.apiBase || DEFAULT_API_BASE;

  const created = await fetch(`${apiBase}/api/v1/users/cli-auth/sessions`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ device_name: 'Chrome extension' }),
  });
  if (!created.ok) {
    return { ok: false, error: `Could not reach ${apiBase} (${created.status})` };
  }
  const { session_id } = await created.json();

  await chrome.storage.local.set({ pendingConnect: { sessionId: session_id, apiBase } });
  await chrome.tabs.create({
    url: `${signinPage(apiBase)}?session=${session_id}&device=${encodeURIComponent('Chrome extension')}`,
  });

  const deadline = Date.now() + CONNECT_POLL_TIMEOUT_MS;
  while (Date.now() < deadline) {
    await new Promise((r) => setTimeout(r, 2000));
    if (await checkPendingConnect()) {
      const { username } = await chrome.storage.local.get(['username']);
      return { ok: true, username };
    }
    const { pendingConnect } = await chrome.storage.local.get(['pendingConnect']);
    if (!pendingConnect) return { ok: false, error: 'Sign-in link expired — click Connect again' };
  }
  return { ok: false, error: 'Timed out waiting for sign-in' };
}

// One poll of the pending auth session. Completes the connect if the user
// has approved; clears the pending state if the link expired. Called from
// the connect() loop and from getStatus(), so an approval that happens
// after the loop ends is still collected the next time the popup opens.
async function checkPendingConnect(): Promise<boolean> {
  const { pendingConnect } = await chrome.storage.local.get(['pendingConnect']);
  if (!pendingConnect) return false;

  const res = await fetch(
    `${pendingConnect.apiBase}/api/v1/users/cli-auth/sessions/${pendingConnect.sessionId}`
  );
  if (res.status === 404) {
    await chrome.storage.local.remove(['pendingConnect']);
    return false;
  }
  if (!res.ok) return false;
  const data = await res.json();
  if (data.status !== 'complete') return false;

  await chrome.storage.local.set({ apiKey: data.api_key, username: data.username, lastError: null });
  await chrome.storage.local.remove(['pendingConnect']);
  await setBadge('', 'Stash Chat Sync');
  await refreshFolders();
  return true;
}

async function refreshFolders(): Promise<void> {
  const cfg = await chrome.storage.local.get(['apiBase', 'apiKey', 'folderId']);
  if (!cfg.apiKey) return;
  const apiBase = cfg.apiBase || DEFAULT_API_BASE;
  const res = await fetch(`${apiBase}/api/v1/me/session-folders`, {
    headers: { Authorization: `Bearer ${cfg.apiKey}` },
  });
  if (!res.ok) return;
  const data = await res.json();
  const folders = (data.folders || []).map((f: any) => ({
    id: f.id,
    name: f.name,
    isDefault: Boolean(f.is_default),
  }));
  const updates: Record<string, any> = { folders };
  const current = folders.find((f: any) => f.id === cfg.folderId);
  if (!current && folders.length > 0) {
    const pick = folders.find((f: any) => f.isDefault) || folders[0];
    updates.folderId = pick.id;
    updates.folderName = pick.name;
  }
  await chrome.storage.local.set(updates);
}

// ---------------------------------------------------------------------------
// Status (popup)
// ---------------------------------------------------------------------------

async function getStatus(): Promise<any> {
  await checkPendingConnect();
  await refreshFolders();
  const cfg = await chrome.storage.local.get([
    'apiBase',
    'apiKey',
    'username',
    'folderId',
    'folderName',
    'folders',
    'lastSync',
    'lastClip',
    'lastImport',
    'lastError',
  ]);
  return {
    ok: true,
    connected: Boolean(cfg.apiKey),
    apiBase: cfg.apiBase || DEFAULT_API_BASE,
    username: cfg.username || null,
    folderId: cfg.folderId || null,
    folders: cfg.folders || [],
    lastSync: cfg.lastSync || null,
    lastClip: cfg.lastClip || null,
    lastImport: cfg.lastImport || null,
    lastError: cfg.lastError || null,
  };
}
