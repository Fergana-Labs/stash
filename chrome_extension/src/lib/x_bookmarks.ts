// Pure parser for x.com's Bookmarks GraphQL response. Kept separate from
// the main-world interceptor (which patches fetch/XHR on import) so it can
// be tested without a DOM. The shape is defensive: x.com changes these
// field names periodically, and a miss should drop one tweet, not throw.

export interface CapturedTweet {
  id: string;
  text: string;
  author_username: string | null;
  author_name: string | null;
  created_at: string | null;
}

export function parseBookmarks(json: any): CapturedTweet[] {
  const instructions =
    json?.data?.bookmark_timeline_v2?.timeline?.instructions ??
    json?.data?.bookmark_timeline?.timeline?.instructions ??
    [];
  const out: CapturedTweet[] = [];
  for (const instruction of instructions) {
    for (const entry of instruction?.entries ?? []) {
      const result = entry?.content?.itemContent?.tweet_results?.result;
      const tweet = normalizeTweet(result);
      if (tweet) out.push(tweet);
    }
  }
  return out;
}

export function normalizeTweet(result: any): CapturedTweet | null {
  // Some results wrap the tweet in a "TweetWithVisibilityResults" shell.
  const t = result?.tweet ?? result;
  const legacy = t?.legacy;
  const id = t?.rest_id;
  if (!id || !legacy) return null;
  const user = t?.core?.user_results?.result?.legacy;
  const createdAt = legacy.created_at ? new Date(legacy.created_at).toISOString() : null;
  return {
    id,
    text: legacy.full_text ?? '',
    author_username: user?.screen_name ?? null,
    author_name: user?.name ?? null,
    created_at: createdAt,
  };
}
