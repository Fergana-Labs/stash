// Injected on demand by the background worker (never listed in the
// manifest). Runs Mozilla Readability on the live, logged-in DOM to
// extract the readable article as HTML — images kept, links/images
// resolved to absolute URLs — and hands it to the background to save.

import { Readability } from '@mozilla/readability';

// Readability mutates the document it's given, so parse a clone.
const article = new Readability(document.cloneNode(true) as Document).parse();

if (!article || !article.content) {
  void chrome.runtime.sendMessage({
    type: 'CLIP_FAILED',
    url: location.href,
    error: "Couldn't find an article to save on this page.",
  });
} else {
  void chrome.runtime.sendMessage({
    type: 'CLIP_PAGE',
    clip: {
      url: location.href,
      title: article.title || document.title,
      html: article.content,
      capturedAt: new Date().toISOString(),
    },
  });
}
