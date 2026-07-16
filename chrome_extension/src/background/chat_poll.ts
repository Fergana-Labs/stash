// Tab-less chat sync: the visible-tab content scripts only see conversations
// the user has open, so once a day (and on demand via "Sync now") the worker
// lists recent ChatGPT/Claude conversations directly (cookie-attached fetches
// — the origins are in host_permissions) and syncs anything updated since the
// last successful pass. Each platform tracks its own watermark.

import {
  chatgptAccessToken,
  chatgptExtract,
  chatgptListConversations,
  claudeExtract,
  claudeListConversations,
  claudeOrgIds,
} from '../lib/chat_apis';
import type { ConversationSnapshot } from '../content/sync';
import { setBadge } from '../lib/stash';

const ALARM_NAME = 'chat-poll';
const POLL_PERIOD_MINUTES = 24 * 60;
const MAX_CONVERSATIONS_PER_PLATFORM = 50;

export type ChatPlatform = 'chatgpt' | 'claude';
type SyncFn = (snapshot: ConversationSnapshot) => Promise<any>;

const WATERMARK_KEY: Record<ChatPlatform, string> = {
  chatgpt: 'lastChatgptSyncAt',
  claude: 'lastClaudeSyncAt',
};

let syncFn: SyncFn | null = null;

export function initChatPoll(sync: SyncFn): void {
  syncFn = sync;
  chrome.runtime.onInstalled.addListener(schedule);
  chrome.runtime.onStartup.addListener(schedule);
  chrome.alarms.onAlarm.addListener((alarm) => {
    if (alarm.name === ALARM_NAME) void pollAll();
  });
}

function schedule(): void {
  chrome.alarms.create(ALARM_NAME, { periodInMinutes: POLL_PERIOD_MINUTES });
}

async function pollAll(): Promise<void> {
  const { apiKey } = await chrome.storage.local.get(['apiKey']);
  if (!apiKey) return;
  const results = await Promise.all([syncChat('chatgpt'), syncChat('claude')]);
  const errors = results.filter((r) => !r.ok);
  if (errors.length > 0) {
    // No notification — a logged-out site would nag daily. Badge + popup error.
    await chrome.storage.local.set({
      lastError: `Daily chat sync failed — ${errors.map((e) => e.error).join('; ')}`,
    });
    await setBadge('!', 'Stash daily sync failed — click for details');
  }
}

/** Sync one chat platform now; advances its watermark on success. */
export async function syncChat(platform: ChatPlatform): Promise<{ ok: boolean; error?: string }> {
  if (!syncFn) return { ok: false, error: 'not ready' };
  const key = WATERMARK_KEY[platform];
  const stored = await chrome.storage.local.get([key]);
  const since = stored[key] || 0;
  try {
    if (platform === 'chatgpt') await pollChatgpt(syncFn, since);
    else await pollClaude(syncFn, since);
    await chrome.storage.local.set({ [key]: Date.now() });
    return { ok: true };
  } catch (e: any) {
    return { ok: false, error: `${platform}: ${e?.message || e}` };
  }
}

/** Whether the user is signed in to the platform (so a sync would work). */
export async function chatSignedIn(platform: ChatPlatform): Promise<boolean> {
  try {
    if (platform === 'chatgpt') {
      const ctx = { origin: 'https://chatgpt.com', init: { credentials: 'include' as const } };
      return Boolean(await chatgptAccessToken(ctx));
    }
    const ctx = { origin: 'https://claude.ai', init: { credentials: 'include' as const } };
    return (await claudeOrgIds(ctx)).length > 0;
  } catch {
    return false;
  }
}

export async function chatLastSyncAt(platform: ChatPlatform): Promise<number | null> {
  const key = WATERMARK_KEY[platform];
  const stored = await chrome.storage.local.get([key]);
  return stored[key] || null;
}

async function pollChatgpt(sync: SyncFn, since: number): Promise<void> {
  const ctx = { origin: 'https://chatgpt.com', init: { credentials: 'include' as const } };
  const token = await chatgptAccessToken(ctx);
  if (!token) throw new Error('not signed in to chatgpt.com');
  const conversations = await chatgptListConversations(ctx, token, MAX_CONVERSATIONS_PER_PLATFORM);
  for (const conv of conversations) {
    if (new Date(conv.updatedAt).getTime() <= since) continue;
    const snapshot = await chatgptExtract(ctx, token, conv.id);
    if (snapshot) await sync(snapshot);
  }
}

async function pollClaude(sync: SyncFn, since: number): Promise<void> {
  const ctx = { origin: 'https://claude.ai', init: { credentials: 'include' as const } };
  const orgIds = await claudeOrgIds(ctx);
  if (orgIds.length === 0) throw new Error('not signed in to claude.ai');
  for (const orgId of orgIds) {
    const conversations = (await claudeListConversations(ctx, orgId)).slice(
      0,
      MAX_CONVERSATIONS_PER_PLATFORM
    );
    for (const conv of conversations) {
      if (new Date(conv.updatedAt).getTime() <= since) continue;
      const snapshot = await claudeExtract(ctx, conv.id, orgId);
      if (snapshot) await sync(snapshot);
    }
  }
}
