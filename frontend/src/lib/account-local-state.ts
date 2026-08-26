import { setScope } from "./scope-store";

// localStorage that belongs to one account: the workspace layout (open tabs,
// pane split, cached tab titles) and the selected scope. On a shared browser a
// new sign-in must not inherit the previous account's state — a stale tab
// renders another account's file id as "File not found", and a stale scope
// narrows every list to a workspace the new user may not even be in.
const OWNER_KEY = "stash_state_owner";
export const WORKSPACE_STORAGE_KEY = "moltchat_workspace";

/** Call with the signed-in user's id before the workspace mounts. The first
 *  time a different account signs in, the previous account's layout and scope
 *  are dropped. Idempotent and synchronous, so it can run during render —
 *  ahead of any child effect that would hydrate or fetch with the stale state. */
export function claimLocalStateForUser(userId: string): void {
  if (typeof window === "undefined") return;
  if (localStorage.getItem(OWNER_KEY) === userId) return;
  localStorage.removeItem(WORKSPACE_STORAGE_KEY);
  // Through the store, not removeItem: its module cache may already hold the
  // stale scope and would keep stamping it onto requests.
  setScope(null);
  localStorage.setItem(OWNER_KEY, userId);
}

/** Signing out drops account-scoped state so the next sign-in starts clean. */
export function clearAccountLocalState(): void {
  localStorage.removeItem(WORKSPACE_STORAGE_KEY);
  localStorage.removeItem(OWNER_KEY);
  setScope(null);
}
