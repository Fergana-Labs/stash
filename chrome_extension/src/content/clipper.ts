// Injected on demand by the background worker (never listed in the
// manifest). Captures the live DOM — logged-in and JS-rendered, which
// beats any server-side refetch — and hands it to the background; the
// server's single article extractor does the rest.

void chrome.runtime.sendMessage({
  type: 'CLIP_PAGE',
  clip: {
    url: location.href,
    title: document.title,
    html: document.documentElement.outerHTML,
    capturedAt: new Date().toISOString(),
  },
});
