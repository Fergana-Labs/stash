// Runs in the PAGE's main world on x.com. X's Bookmarks endpoint is a
// GraphQL call signed with headers (x-client-transaction-id) that a plain
// content-script fetch can't reproduce — so instead of calling it, we let
// x.com's own client make the request and intercept the RESPONSE by
// patching fetch + XHR. The parsed tweets are handed to the isolated-world
// companion via window.postMessage (main-world scripts can't use
// chrome.runtime).

import { parseBookmarks } from '../lib/x_bookmarks';

const BOOKMARKS_RE = /\/graphql\/[^/]+\/Bookmarks/;

function post(tweets: unknown[]): void {
  if (tweets.length === 0) return;
  window.postMessage({ source: 'stash-x-bookmarks', tweets }, window.location.origin);
}

function handleBody(url: string, body: string): void {
  if (!BOOKMARKS_RE.test(url)) return;
  try {
    post(parseBookmarks(JSON.parse(body)));
  } catch {
    // A non-JSON or shape-changed response is not fatal — the next page load
    // tries again. Staying silent avoids console noise on every x.com fetch.
  }
}

const originalFetch = window.fetch;
window.fetch = async function (...args) {
  const response = await originalFetch.apply(this, args as any);
  const url = typeof args[0] === 'string' ? args[0] : (args[0] as Request)?.url;
  if (url && BOOKMARKS_RE.test(url)) {
    response
      .clone()
      .text()
      .then((body) => handleBody(url, body))
      .catch(() => undefined);
  }
  return response;
};

const originalOpen = XMLHttpRequest.prototype.open;
const originalSend = XMLHttpRequest.prototype.send;
XMLHttpRequest.prototype.open = function (this: XMLHttpRequest, method: string, url: string) {
  (this as any).__stashUrl = url;
  // eslint-disable-next-line prefer-rest-params -- forward XHR.open's full arg list verbatim
  return (originalOpen as any).apply(this, arguments);
};
XMLHttpRequest.prototype.send = function (...args) {
  this.addEventListener('load', () => {
    const url = (this as any).__stashUrl as string | undefined;
    if (url && BOOKMARKS_RE.test(url) && typeof this.responseText === 'string') {
      handleBody(url, this.responseText);
    }
  });
  return originalSend.apply(this, args as any);
};
