const AUTH0_MANUAL_LOGOUT_KEY = "stash_auth0_manual_logout";

// Sends Auth0 back to /logged-out, where the middleware deletes any session
// cookie a concurrent request resurrected mid-logout, then forwards to /login.
// The absolute /logged-out URL must be listed in the Auth0 application's
// Allowed Logout URLs.
export function auth0LogoutUrl() {
  return `/auth/logout?returnTo=${encodeURIComponent(`${window.location.origin}/logged-out`)}`;
}

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
