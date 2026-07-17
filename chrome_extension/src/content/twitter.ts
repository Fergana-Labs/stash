// Isolated-world companion on x.com. The main-world interceptor
// (twitter_main.ts) reads x.com's Bookmarks responses but can't reach
// chrome.runtime; this script bridges its window messages to the background
// worker. On a background harvest tab it also scrolls the bookmarks list so
// every cursor page loads — x.com returns only ~20 bookmarks per page, so
// without scrolling only the first page is ever captured.

const MAX_SCROLLS = 80; // ~80 pages * ~20 = up to ~1600 bookmarks per run
const SCROLL_INTERVAL_MS = 1200;

let reachedEnd = false;

window.addEventListener('message', (event) => {
  if (event.source !== window) return;
  const data = event.data;
  if (data?.source !== 'stash-x-bookmarks') return;
  if (Array.isArray(data.ids) && data.ids.length) {
    void chrome.runtime.sendMessage({ type: 'X_BOOKMARKS', ids: data.ids });
  }
  if (data.done) reachedEnd = true;
});

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function harvestIfBackgroundTab(): Promise<void> {
  if (!location.pathname.startsWith('/i/bookmarks')) return;
  // A manual visit captures pages as the user scrolls on their own; only the
  // background harvest tab should auto-scroll.
  const res = await chrome.runtime.sendMessage({ type: 'IS_HARVEST_TAB' });
  if (!res?.harvest) return;

  for (let i = 0; i < MAX_SCROLLS && !reachedEnd; i++) {
    window.scrollTo(0, document.documentElement.scrollHeight);
    await sleep(SCROLL_INTERVAL_MS);
  }
  void chrome.runtime.sendMessage({ type: 'X_HARVEST_DONE' });
}

void harvestIfBackgroundTab();
