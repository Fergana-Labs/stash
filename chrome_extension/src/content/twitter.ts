// Isolated-world companion on x.com. The main-world interceptor
// (twitter_main.ts) can read x.com's Bookmarks responses but can't reach
// chrome.runtime; this script bridges its window messages to the
// background worker.

window.addEventListener('message', (event) => {
  if (event.source !== window) return;
  const data = event.data;
  if (data?.source !== 'stash-x-bookmarks' || !Array.isArray(data.ids)) return;
  void chrome.runtime.sendMessage({ type: 'X_BOOKMARKS', ids: data.ids });
});
