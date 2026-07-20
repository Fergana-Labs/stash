// The sources chip mixes API source tokens (files, sessions, providers) with
// two client-side result kinds — skills and tables are searched in the browser
// and never reach /sources/search.
export const CLIENT_SIDE_TOKENS = ["skills", "tables"];

// Which include_sources tokens the unified search call should carry: the
// chip's selection minus the client-side kinds. null skips the call entirely.
// A folder/page filter only makes sense for pages, so it narrows to the files
// token (matching the old behavior of skipping sessions under a filter).
export function unifiedSearchTokens(
  opts: { filtered: boolean },
  selected: string[]
): string[] | null {
  const tokens = opts.filtered
    ? selected.filter((t) => t === "files")
    : selected.filter((t) => !CLIENT_SIDE_TOKENS.includes(t));
  return tokens.length ? tokens : null;
}
