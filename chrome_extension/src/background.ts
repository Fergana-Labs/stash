// Background service worker: owns the Stash credentials and does all
// backend I/O. Content scripts send conversation snapshots here; we skip
// unchanged ones (content hash, kept in session storage) and upload the
// rest as replace-mode transcripts so a growing chat keeps updating the
// same Stash session.

import type { ConversationSnapshot } from './content/sync';

const DEFAULT_API_BASE = 'https://api.joinstash.ai';
const CONNECT_POLL_TIMEOUT_MS = 180_000;

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
    case 'CONNECT':
      return connect();
    case 'DISCONNECT':
      await chrome.storage.local.remove(['apiKey', 'username', 'workspaceId', 'workspaceName', 'workspaces', 'lastSync', 'lastError']);
      return { ok: true };
    case 'GET_STATUS':
      return getStatus();
    case 'SET_WORKSPACE':
      await chrome.storage.local.set({ workspaceId: message.id, workspaceName: message.name });
      return { ok: true };
    case 'SET_API_BASE':
      // Changing backends invalidates the key, workspaces, and dedup state.
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
  const cfg = await chrome.storage.local.get(['apiBase', 'apiKey', 'workspaceId']);
  if (!cfg.apiKey || !cfg.workspaceId) {
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

  const form = new FormData();
  form.append('file', new Blob([jsonl], { type: 'application/jsonl' }), `${sessionId}.jsonl`);
  form.append('session_id', sessionId);
  form.append('agent_name', snapshot.platform);
  form.append('replace', 'true');

  const apiBase = cfg.apiBase || DEFAULT_API_BASE;
  const res = await fetch(`${apiBase}/api/v1/workspaces/${cfg.workspaceId}/transcripts`, {
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

  await chrome.tabs.create({
    url: `${signinPage(apiBase)}?session=${session_id}&device=${encodeURIComponent('Chrome extension')}`,
  });

  const deadline = Date.now() + CONNECT_POLL_TIMEOUT_MS;
  while (Date.now() < deadline) {
    await new Promise((r) => setTimeout(r, 1000));
    const res = await fetch(`${apiBase}/api/v1/users/cli-auth/sessions/${session_id}`);
    if (!res.ok) continue;
    const data = await res.json();
    if (data.status === 'complete') {
      await chrome.storage.local.set({ apiKey: data.api_key, username: data.username, lastError: null });
      await setBadge('', 'Stash Chat Sync');
      await refreshWorkspaces();
      return { ok: true, username: data.username };
    }
  }
  return { ok: false, error: 'Timed out waiting for sign-in' };
}

async function refreshWorkspaces(): Promise<void> {
  const cfg = await chrome.storage.local.get(['apiBase', 'apiKey', 'workspaceId']);
  if (!cfg.apiKey) return;
  const apiBase = cfg.apiBase || DEFAULT_API_BASE;
  const res = await fetch(`${apiBase}/api/v1/workspaces/mine`, {
    headers: { Authorization: `Bearer ${cfg.apiKey}` },
  });
  if (!res.ok) return;
  const data = await res.json();
  const workspaces = (data.workspaces || []).map((w: any) => ({
    id: w.id,
    name: w.name,
    isPrimary: Boolean(w.is_primary),
  }));
  const updates: Record<string, any> = { workspaces };
  const current = workspaces.find((w: any) => w.id === cfg.workspaceId);
  if (!current && workspaces.length > 0) {
    const pick = workspaces.find((w: any) => w.isPrimary) || workspaces[0];
    updates.workspaceId = pick.id;
    updates.workspaceName = pick.name;
  }
  await chrome.storage.local.set(updates);
}

// ---------------------------------------------------------------------------
// Status (popup)
// ---------------------------------------------------------------------------

async function getStatus(): Promise<any> {
  await refreshWorkspaces();
  const cfg = await chrome.storage.local.get([
    'apiBase',
    'apiKey',
    'username',
    'workspaceId',
    'workspaceName',
    'workspaces',
    'lastSync',
    'lastError',
  ]);
  return {
    ok: true,
    connected: Boolean(cfg.apiKey),
    apiBase: cfg.apiBase || DEFAULT_API_BASE,
    username: cfg.username || null,
    workspaceId: cfg.workspaceId || null,
    workspaces: cfg.workspaces || [],
    lastSync: cfg.lastSync || null,
    lastError: cfg.lastError || null,
  };
}
