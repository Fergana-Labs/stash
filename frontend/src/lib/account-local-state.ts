import { setScope } from "./scope-store";

// The selected scope belongs to one account. On a shared browser, a new sign-in
// must not inherit a workspace the new user may not be in.
const OWNER_KEY = "stash_state_owner";

/** Call with the signed-in user's id before the workspace mounts. */
export function claimLocalStateForUser(userId: string): void {
  if (typeof window === "undefined") return;
  if (localStorage.getItem(OWNER_KEY) === userId) return;
  setScope(null);
  localStorage.setItem(OWNER_KEY, userId);
}

/** Signing out drops account-scoped state so the next sign-in starts clean. */
export function clearAccountLocalState(): void {
  localStorage.removeItem(OWNER_KEY);
  setScope(null);
}
