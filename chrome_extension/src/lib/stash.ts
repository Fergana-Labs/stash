// Shared Stash-backend plumbing for the background worker's modules.

export const DEFAULT_API_BASE = 'https://api.joinstash.ai';

export interface StashConfig {
  apiBase: string;
  apiKey: string | null;
  folderId: string | null;
}

export async function stashConfig(): Promise<StashConfig> {
  const cfg = await chrome.storage.local.get(['apiBase', 'apiKey', 'folderId']);
  return {
    apiBase: cfg.apiBase || DEFAULT_API_BASE,
    apiKey: cfg.apiKey || null,
    folderId: cfg.folderId || null,
  };
}

export async function setBadge(text: string, title: string): Promise<void> {
  await chrome.action.setBadgeText({ text });
  if (text === '!') await chrome.action.setBadgeBackgroundColor({ color: '#ef4444' });
  if (text === '✓') await chrome.action.setBadgeBackgroundColor({ color: '#16a34a' });
  await chrome.action.setTitle({ title });
}

export async function flashOkBadge(title: string): Promise<void> {
  await setBadge('✓', title);
  setTimeout(() => void setBadge('', 'Stash Sync'), 3000);
}
