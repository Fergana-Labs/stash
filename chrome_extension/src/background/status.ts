// Per-platform status + "Sync now" for the background pollers the popup shows:
// ChatGPT and Claude. "Connected" means the user is signed in to that site (so
// a sync would actually work) — checked live via a session fetch. "Enabled" is
// the user's own switch for the platform.

import { chatLastSyncAt, chatSignedIn, syncChat } from './chat_poll';
import { PLATFORMS, type Platform, syncEnabled } from './sync_settings';

export type { Platform };

export interface PlatformState {
  connected: boolean;
  enabled: boolean;
  lastSyncAt: number | null;
}

export async function platformStatus(): Promise<Record<Platform, PlatformState>> {
  const enabled = await syncEnabled();
  const entries = await Promise.all(
    PLATFORMS.map(
      async (p) =>
        [
          p,
          {
            connected: await chatSignedIn(p),
            enabled: enabled[p],
            lastSyncAt: await chatLastSyncAt(p),
          },
        ] as const
    )
  );
  return Object.fromEntries(entries) as Record<Platform, PlatformState>;
}

export async function syncNow(p: Platform): Promise<any> {
  return syncChat(p);
}
