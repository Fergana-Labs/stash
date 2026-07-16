// Per-platform status + "Sync now" for the four background pollers the popup
// shows: ChatGPT, Claude, Instagram, X. "Connected" means the user is signed
// in to that site (so a sync would actually work) — checked live via a
// session fetch (chat) or the site's login cookie (IG/X).

import { chatLastSyncAt, chatSignedIn, syncChat } from './chat_poll';
import { instagramLastSyncAt, syncInstagramNow } from './instagram';
import { syncXNow, xLastSyncAt } from './twitter';

export type Platform = 'chatgpt' | 'claude' | 'instagram' | 'x';

export interface PlatformState {
  connected: boolean;
  lastSyncAt: number | null;
}

async function cookieExists(url: string, name: string): Promise<boolean> {
  try {
    return Boolean(await chrome.cookies.get({ url, name }));
  } catch {
    return false;
  }
}

async function connected(p: Platform): Promise<boolean> {
  if (p === 'chatgpt' || p === 'claude') return chatSignedIn(p);
  if (p === 'instagram') return cookieExists('https://www.instagram.com', 'sessionid');
  return cookieExists('https://x.com', 'auth_token'); // x
}

async function lastSyncAt(p: Platform): Promise<number | null> {
  if (p === 'chatgpt' || p === 'claude') return chatLastSyncAt(p);
  if (p === 'instagram') return instagramLastSyncAt();
  return xLastSyncAt(); // x
}

export async function platformStatus(): Promise<Record<Platform, PlatformState>> {
  const platforms: Platform[] = ['chatgpt', 'claude', 'instagram', 'x'];
  const entries = await Promise.all(
    platforms.map(
      async (p) =>
        [p, { connected: await connected(p), lastSyncAt: await lastSyncAt(p) }] as const
    )
  );
  return Object.fromEntries(entries) as Record<Platform, PlatformState>;
}

export async function syncNow(p: Platform): Promise<any> {
  if (p === 'chatgpt' || p === 'claude') return syncChat(p);
  if (p === 'instagram') return syncInstagramNow();
  return syncXNow(); // x
}
