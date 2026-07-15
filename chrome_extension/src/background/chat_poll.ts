// Daily tab-less chat poll: the visible-tab content scripts only see
// conversations the user has open, so once a day the worker lists recent
// ChatGPT/Claude conversations directly (cookie-attached fetches — the
// origins are in host_permissions) and syncs anything updated since the
// last successful pass. The watermark only advances on a fully successful
// pass; a failed platform surfaces on the badge and retries next alarm.

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

type SyncFn = (snapshot: ConversationSnapshot) => Promise<any>;

export function initChatPoll(sync: SyncFn): void {
  chrome.runtime.onInstalled.addListener(schedule);
  chrome.runtime.onStartup.addListener(schedule);
  chrome.alarms.onAlarm.addListener((alarm) => {
    if (alarm.name === ALARM_NAME) void pollAll(sync);
  });
}

function schedule(): void {
  chrome.alarms.create(ALARM_NAME, { periodInMinutes: POLL_PERIOD_MINUTES });
}

async function pollAll(sync: SyncFn): Promise<void> {
  const { apiKey, lastChatPollAt } = await chrome.storage.local.get(['apiKey', 'lastChatPollAt']);
  if (!apiKey) return;
  const since = lastChatPollAt || 0;

  const errors: string[] = [];
  await pollChatgpt(sync, since).catch((e) => errors.push(`ChatGPT: ${e?.message || e}`));
  await pollClaude(sync, since).catch((e) => errors.push(`Claude: ${e?.message || e}`));

  if (errors.length > 0) {
    // No notification — a logged-out site would nag daily. Badge + popup error.
    await chrome.storage.local.set({ lastError: `Daily chat poll failed — ${errors.join('; ')}` });
    await setBadge('!', 'Stash daily poll failed — click for details');
    return;
  }
  await chrome.storage.local.set({ lastChatPollAt: Date.now(), lastError: null });
}

async function pollChatgpt(sync: SyncFn, since: number): Promise<void> {
  const ctx = {
    origin: 'https://chatgpt.com',
    init: { credentials: 'include' as RequestCredentials },
  };
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
  const ctx = {
    origin: 'https://claude.ai',
    init: { credentials: 'include' as RequestCredentials },
  };
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
