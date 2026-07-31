// Per-platform status + "Sync now" for the background pollers the popup shows:
// ChatGPT, Claude, Instagram. "Connected" means the user is signed in to that
// site (so a sync would actually work) — checked live via a session fetch
// (chat) or the site's login cookie (Instagram). "Enabled" is the user's own
// switch for the platform. X is handled server-side over OAuth now, so it
// isn't an extension platform.

import { chatLastSyncAt, chatSignedIn, syncChat } from './chat_poll';
import { instagramLastSyncAt, syncInstagramNow } from './instagram';
import { PLATFORMS, type Platform, syncEnabled } from './sync_settings';

export type { Platform };

export interface PlatformState {
  connected: boolean;
  enabled: boolean;
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
  return cookieExists('https://www.instagram.com', 'sessionid'); // instagram
}

async function lastSyncAt(p: Platform): Promise<number | null> {
  if (p === 'chatgpt' || p === 'claude') return chatLastSyncAt(p);
  return instagramLastSyncAt(); // instagram
}

export async function platformStatus(): Promise<Record<Platform, PlatformState>> {
  const enabled = await syncEnabled();
  const entries = await Promise.all(
    PLATFORMS.map(
      async (p) =>
        [
          p,
          { connected: await connected(p), enabled: enabled[p], lastSyncAt: await lastSyncAt(p) },
        ] as const
    )
  );
  return Object.fromEntries(entries) as Record<Platform, PlatformState>;
}

export async function syncNow(p: Platform): Promise<any> {
  if (p === 'chatgpt' || p === 'claude') return syncChat(p);
  return syncInstagramNow(); // instagram
}
