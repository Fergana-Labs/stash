// Per-platform sync switch, toggled from the popup.
//
// Every path that would send data for a platform checks this first — the
// daily alarms, the content scripts pushing from an open tab, and the
// popup's "Sync now" — so turning a source off actually stops it rather
// than just hiding the button.

export type Platform = 'chatgpt' | 'claude' | 'instagram';

export const PLATFORMS: Platform[] = ['chatgpt', 'claude', 'instagram'];

const KEY = 'syncEnabled';

const DEFAULTS: Record<Platform, boolean> = { chatgpt: true, claude: true, instagram: true };

/** The switch map, writing the defaults the first time anything asks for it.
 * Every reader goes through here, so no caller has to know what an absent
 * key means. */
export async function syncEnabled(): Promise<Record<Platform, boolean>> {
  const stored = await chrome.storage.local.get([KEY]);
  if (stored[KEY]) return stored[KEY];
  await chrome.storage.local.set({ [KEY]: DEFAULTS });
  return DEFAULTS;
}

export async function isSyncEnabled(platform: Platform): Promise<boolean> {
  return (await syncEnabled())[platform];
}

export async function setSyncEnabled(platform: Platform, on: boolean): Promise<void> {
  await chrome.storage.local.set({ [KEY]: { ...(await syncEnabled()), [platform]: on } });
}
