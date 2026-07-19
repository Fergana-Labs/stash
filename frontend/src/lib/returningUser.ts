const SIGNED_IN_BEFORE_KEY = "stash_signed_in_before";

// The login page should only greet visitors with "Welcome back" if someone has
// actually signed in on this browser before. The server can't know that for a
// cookie-less visitor, so successful sign-ins leave this durable marker (it
// intentionally survives logout — a logged-out user is still a returning one).
export function markSignedInBefore() {
  if (typeof window === "undefined") return;
  localStorage.setItem(SIGNED_IN_BEFORE_KEY, "1");
}

export function hasSignedInBefore(): boolean {
  if (typeof window === "undefined") return false;
  return localStorage.getItem(SIGNED_IN_BEFORE_KEY) === "1";
}
