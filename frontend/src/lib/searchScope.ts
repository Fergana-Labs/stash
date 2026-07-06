/** The scope a search runs in — drives the command palette's placeholder and
 *  which backend query params it sends. */
export interface SearchScope {
  kind: "page" | "folder" | "session" | "skill" | "sessions" | "skills" | "all";
  label: string;
  detail: string;
  params: Record<string, string>;
}
