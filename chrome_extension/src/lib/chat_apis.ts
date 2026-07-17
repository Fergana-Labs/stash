// Chat-platform API clients shared by the content scripts and the
// background service worker. Content scripts fetch same-origin (cookies
// attach automatically); the worker passes an absolute origin plus
// credentials: 'include' (cookie-attached because the origins are in
// host_permissions).

import type { ConversationSnapshot, TranscriptLine } from '../content/sync';

export interface FetchCtx {
  origin: string; // '' in content scripts; 'https://chatgpt.com' etc. in the worker
  init?: RequestInit;
}

function get(ctx: FetchCtx, path: string, headers?: Record<string, string>): Promise<Response> {
  return fetch(`${ctx.origin}${path}`, { ...ctx.init, headers });
}

// ---------------------------------------------------------------------------
// ChatGPT
// ---------------------------------------------------------------------------

let cachedToken: { value: string; fetchedAt: number } | null = null;

export async function chatgptAccessToken(ctx: FetchCtx): Promise<string | null> {
  if (cachedToken && Date.now() - cachedToken.fetchedAt < 5 * 60_000) {
    return cachedToken.value;
  }
  const res = await get(ctx, '/api/auth/session');
  if (!res.ok) return null;
  const data = await res.json();
  if (!data?.accessToken) return null;
  cachedToken = { value: data.accessToken, fetchedAt: Date.now() };
  return cachedToken.value;
}

export async function chatgptListConversations(
  ctx: FetchCtx,
  token: string,
  limit: number
): Promise<{ id: string; title: string; updatedAt: string }[]> {
  const res = await get(ctx, `/backend-api/conversations?offset=0&limit=${limit}&order=updated`, {
    Authorization: `Bearer ${token}`,
  });
  if (!res.ok) throw new Error(`conversation list failed (${res.status})`);
  const data = await res.json();
  return (data.items || []).map((item: any) => ({
    id: item.id,
    title: item.title || 'ChatGPT conversation',
    updatedAt: item.update_time,
  }));
}

function chatgptTextFromMessage(message: any): string {
  const content = message?.content;
  if (!content) return '';
  if (content.content_type === 'text') {
    return (content.parts || []).filter((p: any) => typeof p === 'string').join('\n\n');
  }
  if (content.content_type === 'code') {
    const lang = content.language && content.language !== 'unknown' ? content.language : '';
    return '```' + lang + '\n' + (content.text || '') + '\n```';
  }
  if (content.content_type === 'multimodal_text') {
    return (content.parts || [])
      .map((p: any) => (typeof p === 'string' ? p : '[image]'))
      .join('\n\n');
  }
  return '';
}

function chatgptIsHidden(message: any): boolean {
  return Boolean(
    message?.metadata?.is_visually_hidden_from_conversation ||
      message?.content?.content_type === 'user_editable_context'
  );
}

export async function chatgptExtract(
  ctx: FetchCtx,
  token: string,
  convId: string
): Promise<ConversationSnapshot | null> {
  const res = await get(ctx, `/backend-api/conversation/${convId}`, {
    Authorization: `Bearer ${token}`,
  });
  if (!res.ok) return null;
  const data = await res.json();

  // `mapping` is a tree of message nodes; the chain from current_node up to
  // the root is the branch the user currently sees.
  const lines: TranscriptLine[] = [];
  let nodeId: string | undefined = data.current_node;
  while (nodeId) {
    const node = data.mapping?.[nodeId];
    if (!node) break;
    const message = node.message;
    const role = message?.author?.role;
    if ((role === 'user' || role === 'assistant') && !chatgptIsHidden(message)) {
      const text = chatgptTextFromMessage(message).trim();
      if (text) {
        lines.push({
          type: role,
          message: { content: text },
          timestamp: message.create_time
            ? new Date(message.create_time * 1000).toISOString()
            : undefined,
        });
      }
    }
    nodeId = node.parent;
  }
  lines.reverse();
  if (lines.length === 0) return null;

  return {
    platform: 'chatgpt',
    conversationId: convId,
    title: data.title || 'ChatGPT conversation',
    lines,
  };
}

// ---------------------------------------------------------------------------
// Claude
// ---------------------------------------------------------------------------

let cachedOrgId: string | null = null;

export async function claudeOrgIds(ctx: FetchCtx, knownOrgId?: string | null): Promise<string[]> {
  const ids: string[] = [];
  const known = cachedOrgId || knownOrgId;
  if (known) ids.push(known);
  const res = await get(ctx, '/api/organizations');
  if (res.ok) {
    const orgs = await res.json();
    for (const org of Array.isArray(orgs) ? orgs : []) {
      if (org?.uuid && !ids.includes(org.uuid)) ids.push(org.uuid);
    }
  }
  return ids;
}

export async function claudeListConversations(
  ctx: FetchCtx,
  orgId: string
): Promise<{ id: string; title: string; updatedAt: string }[]> {
  const res = await get(ctx, `/api/organizations/${orgId}/chat_conversations`);
  if (!res.ok) throw new Error(`conversation list failed (${res.status})`);
  const data = await res.json();
  return (Array.isArray(data) ? data : []).map((conv: any) => ({
    id: conv.uuid,
    title: conv.name || 'Claude conversation',
    updatedAt: conv.updated_at,
  }));
}

function claudeTextFromMessage(msg: any): string {
  const blocks = Array.isArray(msg?.content) ? msg.content : [];
  const parts = blocks
    .filter((b: any) => b?.type === 'text' && typeof b.text === 'string' && b.text.trim())
    .map((b: any) => b.text);
  if (parts.length > 0) return parts.join('\n\n');
  return typeof msg?.text === 'string' ? msg.text : '';
}

export async function claudeExtract(
  ctx: FetchCtx,
  convId: string,
  knownOrgId?: string | null
): Promise<ConversationSnapshot | null> {
  let data: any = null;
  for (const orgId of await claudeOrgIds(ctx, knownOrgId)) {
    const res = await get(
      ctx,
      `/api/organizations/${orgId}/chat_conversations/${convId}?tree=True&rendering_mode=messages&render_all_tools=true`
    );
    if (res.ok) {
      cachedOrgId = orgId;
      data = await res.json();
      break;
    }
  }
  if (!data) return null;

  const lines: TranscriptLine[] = [];
  for (const msg of data.chat_messages || []) {
    const role = msg.sender === 'human' ? 'user' : msg.sender === 'assistant' ? 'assistant' : null;
    if (!role) continue;
    const text = claudeTextFromMessage(msg).trim();
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
