// Claude.ai content script: same-origin extraction via claude.ai's own
// JSON API. The active org from the cookie is tried first (only content
// scripts can read document.cookie; the worker's daily poll just
// enumerates orgs).

import { claudeExtract } from '../lib/chat_apis';
import { watchConversation } from './sync';

const ctx = { origin: '' };

function orgFromCookie(): string | null {
  const match = document.cookie.match(/(?:^|;\s*)lastActiveOrg=([0-9a-f-]{36})/);
  return match ? match[1] : null;
}

watchConversation(async () => {
  const convId = location.pathname.match(/\/chat\/([0-9a-f-]{36})/)?.[1];
  if (!convId) return null;
  return claudeExtract(ctx, convId, orgFromCookie());
});
