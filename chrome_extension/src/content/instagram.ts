// Instagram saved-posts capture: reads the user's saved list via
// Instagram's own same-origin API (the pattern every saved-posts exporter
// extension uses — cookies attach automatically, no signed params).
// Only the list of post URLs leaves the page; content hydration happens
// server-side via ScrapeCreators. The background worker owns the 24h
// throttle and the upload.

const SAVED_FEED_PATH = '/api/v1/feed/saved/posts/';
// Instagram's public web-app id, required on internal API calls.
const IG_APP_ID = '936619743392459';
const MAX_ITEMS = 200;

async function harvest(): Promise<void> {
  const check = await chrome.runtime.sendMessage({
    type: 'SHOULD_FETCH_SAVES',
    platform: 'instagram',
  });
  if (!check?.fetch) return;

  const csrf = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/)?.[1];
  if (!csrf) {
    void chrome.runtime.sendMessage({
      type: 'SAVED_ITEMS_FAILED',
      platform: 'instagram',
      error: 'not signed in to instagram.com',
    });
    return;
  }

  const items: { url: string }[] = [];
  let maxId = '';
  while (items.length < MAX_ITEMS) {
    const query = maxId ? `?max_id=${encodeURIComponent(maxId)}` : '';
    const res = await fetch(`${SAVED_FEED_PATH}${query}`, {
      headers: {
        'x-ig-app-id': IG_APP_ID,
        'x-csrftoken': csrf,
        'x-requested-with': 'XMLHttpRequest',
      },
    });
    if (!res.ok) {
      void chrome.runtime.sendMessage({
        type: 'SAVED_ITEMS_FAILED',
        platform: 'instagram',
        error: `saved-posts API returned ${res.status}`,
      });
      return;
    }
    const data = await res.json();
    for (const wrapper of data.items || []) {
      const media = wrapper?.media || wrapper;
      if (media?.code) items.push({ url: `https://www.instagram.com/p/${media.code}/` });
    }
    if (!data.more_available || !data.next_max_id) break;
    maxId = data.next_max_id;
  }

  // Empty is a valid harvest (no saves yet) — the background still records
  // the pass so the throttle works.
  void chrome.runtime.sendMessage({ type: 'SAVED_ITEMS', platform: 'instagram', items });
}

void harvest();
