// Pure parser for x.com's Bookmarks GraphQL response. Kept separate from
// the main-world interceptor (which patches fetch/XHR on import) so it can
// be tested without a DOM. We only pull the tweet IDs — the server hydrates
// the full content, thread, and media from the link via ScrapeCreators. The
// shape is defensive: x.com renames these fields periodically, and a miss
// should drop one tweet, not throw.

export function parseBookmarkIds(json: any): string[] {
  const instructions =
    json?.data?.bookmark_timeline_v2?.timeline?.instructions ??
    json?.data?.bookmark_timeline?.timeline?.instructions ??
    [];
  const out: string[] = [];
  for (const instruction of instructions) {
    for (const entry of instruction?.entries ?? []) {
      const result = entry?.content?.itemContent?.tweet_results?.result;
      const id = tweetId(result);
      if (id) out.push(id);
    }
  }
  return out;
}

export function tweetId(result: any): string | null {
  // Some results wrap the tweet in a "TweetWithVisibilityResults" shell.
  const t = result?.tweet ?? result;
  return t?.rest_id ?? null;
}
