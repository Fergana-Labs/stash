// Instagram saved-posts capture: reads the user's saved list via
// Instagram's own same-origin API (the pattern every saved-posts exporter
// extension uses — cookies attach automatically, no signed params).
// Only the list of post URLs leaves the page; content hydration happens
// server-side via ScrapeCreators. The background worker owns the 24h
// throttle and the upload.

const SAVED_FEED_PATH = '/api/v1/feed/saved/posts/';
// Instagram's public web-app id, required on internal API calls.
const IG_APP_ID = '936619743392459';

// The saved feed returns ~18 posts per page, so the old MAX_ITEMS = 200 cap
// stopped after a dozen requests and reported ~210 saves to anyone with more
// — silently, because a truncated harvest looks identical to a complete one.
// These bounds exist to stop a runaway loop, not to cap a real library:
// PAGE_LIMIT is what actually ends the walk, and MAX_ITEMS is a backstop in
// case Instagram keeps setting more_available forever.
const MAX_ITEMS = 20000;
const PAGE_LIMIT = 400;
// Instagram rate-limits the saved feed aggressively. A short pause between
// pages is the difference between walking a large library and getting a 429
// partway through, which would truncate just as silently as the old cap.
const PAGE_DELAY_MS = 350;

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

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
  const seen = new Set<string>();
  let maxId = '';
  let truncated = false;

  for (let page = 0; ; page += 1) {
    if (page >= PAGE_LIMIT || items.length >= MAX_ITEMS) {
      truncated = true;
      break;
    }
    if (page > 0) await sleep(PAGE_DELAY_MS);

    const query = maxId ? `?max_id=${encodeURIComponent(maxId)}` : '';
    const res = await fetch(`${SAVED_FEED_PATH}${query}`, {
      headers: {
        'x-ig-app-id': IG_APP_ID,
        'x-csrftoken': csrf,
        'x-requested-with': 'XMLHttpRequest',
      },
    });
    if (!res.ok) {
      // Partway through a long walk, a failure means the harvest is
      // incomplete. Keeping what we have and saying so beats discarding
      // hundreds of good URLs, and beats reporting it as a clean pass.
      void chrome.runtime.sendMessage({
        type: 'SAVED_ITEMS_FAILED',
        platform: 'instagram',
        error: `saved-posts API returned ${res.status} after ${items.length} saves`,
      });
      return;
    }
    const data = await res.json();
    for (const wrapper of data.items || []) {
      const media = wrapper?.media || wrapper;
      // Instagram repeats posts across page boundaries when the list changes
      // mid-walk; without this a long harvest inflates its own count.
      if (media?.code && !seen.has(media.code)) {
        seen.add(media.code);
        items.push({ url: `https://www.instagram.com/p/${media.code}/` });
      }
    }
    if (!data.more_available || !data.next_max_id) break;
    maxId = data.next_max_id;
  }

  if (truncated) {
    void chrome.runtime.sendMessage({
      type: 'SAVED_ITEMS_FAILED',
      platform: 'instagram',
      error: `stopped at ${items.length} saves — hit the safety limit, re-run to continue`,
    });
  }

  // Empty is a valid harvest (no saves yet) — the background still records
  // the pass so the throttle works.
  void chrome.runtime.sendMessage({ type: 'SAVED_ITEMS', platform: 'instagram', items });
}

void harvest();
