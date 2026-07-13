// ChatGPT content script: same-origin extraction (cookie-authed via the
// site's own backend API — not DOM scraping, which drops virtualized
// messages and mangles code blocks). The shared client lives in
// lib/chat_apis so the background worker's daily poll uses the same code.

import { chatgptAccessToken, chatgptExtract } from '../lib/chat_apis';
import { watchConversation } from './sync';

const ctx = { origin: '' };

watchConversation(async () => {
  const convId = location.pathname.match(/\/c\/([0-9a-f-]{36})/)?.[1];
  if (!convId) return null;
  const token = await chatgptAccessToken(ctx);
  if (!token) return null;
  return chatgptExtract(ctx, token, convId);
});
