const AUTH0_MANUAL_LOGOUT_KEY = "stash_auth0_manual_logout";

export function markManualAuth0Logout() {
  sessionStorage.setItem(AUTH0_MANUAL_LOGOUT_KEY, "1");
}

export function consumeManualAuth0Logout() {
  const marked = sessionStorage.getItem(AUTH0_MANUAL_LOGOUT_KEY) === "1";
  if (marked) {
    sessionStorage.removeItem(AUTH0_MANUAL_LOGOUT_KEY);
  }
  return marked;
}
