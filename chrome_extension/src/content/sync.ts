// Shared sync loop for the chatgpt.com / claude.ai content scripts.
//
// The extension has no save button: while a conversation tab is visible we
// periodically snapshot the full conversation (via the site's own JSON API,
// so virtualized/scrolled-out messages are included) and hand it to the
// background worker, which dedupes by content hash and uploads the rest.

export interface TranscriptLine {
  type: 'user' | 'assistant';
  message: { content: string };
  timestamp?: string;
}

export interface ConversationSnapshot {
  platform: 'chatgpt' | 'claude-web';
  conversationId: string;
  title: string;
  lines: TranscriptLine[];
}

const SYNC_INTERVAL_MS = 15_000;

export function watchConversation(extract: () => Promise<ConversationSnapshot | null>): void {
  let syncing = false;

  const sync = async () => {
    if (syncing) return;
    syncing = true;
    try {
      const snapshot = await extract();
      if (snapshot && snapshot.lines.length > 0) {
        await chrome.runtime.sendMessage({ type: 'SYNC_CONVERSATION', snapshot });
      }
    } catch (e) {
      console.warn('[stash-chat-sync] sync failed:', e);
    } finally {
      syncing = false;
    }
  };

  setInterval(() => {
    if (!document.hidden) void sync();
  }, SYNC_INTERVAL_MS);

  // Flush when the user switches away so the tail of a conversation isn't
  // lost to the polling interval.
  document.addEventListener('visibilitychange', () => {
    if (document.hidden) void sync();
  });

  void sync();
}
