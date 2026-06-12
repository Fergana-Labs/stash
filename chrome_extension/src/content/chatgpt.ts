// ChatGPT extractor: reads the full conversation from ChatGPT's own
// backend API (cookie-authed, same-origin) instead of scraping the DOM,
// which drops virtualized messages and mangles code blocks.

import { ConversationSnapshot, TranscriptLine, watchConversation } from './sync';

let cachedToken: { value: string; fetchedAt: number } | null = null;

async function accessToken(): Promise<string | null> {
  if (cachedToken && Date.now() - cachedToken.fetchedAt < 5 * 60_000) {
    return cachedToken.value;
  }
  const res = await fetch('/api/auth/session');
  if (!res.ok) return null;
  const data = await res.json();
  if (!data?.accessToken) return null;
  cachedToken = { value: data.accessToken, fetchedAt: Date.now() };
  return cachedToken.value;
}

function textFromMessage(message: any): string {
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

function isHidden(message: any): boolean {
  return Boolean(
    message?.metadata?.is_visually_hidden_from_conversation ||
      message?.content?.content_type === 'user_editable_context'
  );
}

async function extract(): Promise<ConversationSnapshot | null> {
  const convId = location.pathname.match(/\/c\/([0-9a-f-]{36})/)?.[1];
  if (!convId) return null;
  const token = await accessToken();
  if (!token) return null;

  const res = await fetch(`/backend-api/conversation/${convId}`, {
    headers: { Authorization: `Bearer ${token}` },
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
    if ((role === 'user' || role === 'assistant') && !isHidden(message)) {
      const text = textFromMessage(message).trim();
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

watchConversation(extract);
