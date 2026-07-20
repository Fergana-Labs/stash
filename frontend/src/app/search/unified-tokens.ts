export type ContentScope = "all" | "sessions" | "pages" | "tables" | "skills";

// Which include_sources tokens the unified search call should carry: the
// source chip's selection narrowed by the content-type filter (the content
// chip picks a result KIND, the sources chip picks an ORIGIN — the call
// searches their intersection). null skips the unified call entirely.
// A folder/page filter only makes sense for pages, so it narrows to the files
// token (matching the old behavior of skipping sessions under a filter).
export function unifiedSearchTokens(
  scope: ContentScope,
  opts: { filtered: boolean },
  selected: string[]
): string[] | null {
  if (scope === "tables" || scope === "skills") return null;
  if (opts.filtered && scope === "sessions") return null;
  let tokens = selected;
  if (opts.filtered || scope === "pages") tokens = selected.filter((t) => t === "files");
  else if (scope === "sessions") tokens = selected.filter((t) => t === "sessions");
  return tokens.length ? tokens : null;
}
