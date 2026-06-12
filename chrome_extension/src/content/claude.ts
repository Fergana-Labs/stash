// Claude.ai extractor: reads the full conversation from claude.ai's own
// JSON API (cookie-authed, same-origin). The conversation belongs to one
// org; we try the active org from the cookie first, then the rest.

import { ConversationSnapshot, TranscriptLine, watchConversation } from './sync';

let cachedOrgId: string | null = null;

function orgFromCookie(): string | null {
  const match = document.cookie.match(/(?:^|;\s*)lastActiveOrg=([0-9a-f-]{36})/);
  return match ? match[1] : null;
}

async function candidateOrgIds(): Promise<string[]> {
  const ids: string[] = [];
  const known = cachedOrgId || orgFromCookie();
  if (known) ids.push(known);
  const res = await fetch('/api/organizations');
  if (res.ok) {
    const orgs = await res.json();
    for (const org of Array.isArray(orgs) ? orgs : []) {
      if (org?.uuid && !ids.includes(org.uuid)) ids.push(org.uuid);
    }
  }
  return ids;
}

async function fetchConversation(convId: string): Promise<any | null> {
  for (const orgId of await candidateOrgIds()) {
    const res = await fetch(
      `/api/organizations/${orgId}/chat_conversations/${convId}?tree=True&rendering_mode=messages&render_all_tools=true`
    );
    if (res.ok) {
      cachedOrgId = orgId;
      return res.json();
    }
  }
  return null;
}

function textFromMessage(msg: any): string {
  const blocks = Array.isArray(msg?.content) ? msg.content : [];
  const parts = blocks
    .filter((b: any) => b?.type === 'text' && typeof b.text === 'string' && b.text.trim())
    .map((b: any) => b.text);
  if (parts.length > 0) return parts.join('\n\n');
  return typeof msg?.text === 'string' ? msg.text : '';
}

async function extract(): Promise<ConversationSnapshot | null> {
  const convId = location.pathname.match(/\/chat\/([0-9a-f-]{36})/)?.[1];
  if (!convId) return null;
  const data = await fetchConversation(convId);
  if (!data) return null;

  const lines: TranscriptLine[] = [];
  for (const msg of data.chat_messages || []) {
    const role = msg.sender === 'human' ? 'user' : msg.sender === 'assistant' ? 'assistant' : null;
    if (!role) continue;
    const text = textFromMessage(msg).trim();
    if (!text) continue;
    lines.push({
      type: role,
      message: { content: text },
      timestamp: msg.created_at || undefined,
    });
  }
  if (lines.length === 0) return null;

  return {
    platform: 'claude-web',
    conversationId: convId,
    title: data.name || 'Claude conversation',
    lines,
  };
}

watchConversation(extract);
