"use client";

import { useCallback, useEffect, useState } from "react";
import { API_BASE, ApiError, clearToken, getMe, getToken } from "../lib/api";
import { markManualAuth0Logout } from "../lib/authLogout";
import { User } from "../lib/types";

const AUTH0_ENABLED = process.env.NEXT_PUBLIC_AUTH0_ENABLED === "true";

/**
 * Auth hook. Reads the API key from localStorage and loads /users/me.
 *
 * Only a 401 from /users/me is treated as signed-out — other errors (network
 * blip, 5xx from a restarting backend) keep the last known user so a transient
 * failure doesn't bounce the user to the login page.
 */
export function useAuth() {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  const loadUser = useCallback(async () => {
    if (!getToken()) {
      setUser(null);
      setLoading(false);
      return;
    }
    try {
      const me = await getMe();
      setUser(me);
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        clearToken();
        setUser(null);
      }
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadUser();
  }, [loadUser]);

  // Cross-tab sync: when another tab writes/clears the token, re-check auth
  // so this tab's UI stays in sync instead of happily 401-ing every request.
  useEffect(() => {
    const onStorage = (e: StorageEvent) => {
      if (e.key === "stash_token" || e.key === null) {
        loadUser();
      }
    };
    window.addEventListener("storage", onStorage);
    return () => window.removeEventListener("storage", onStorage);
  }, [loadUser]);

  const logout = useCallback(async () => {
    if (AUTH0_ENABLED) {
      markManualAuth0Logout();
    }

    // Drop local state first so the UI flips to signed-out the moment the
    // user clicks. Revoke the active key before navigating so the browser
    // session cannot be restored by a still-valid local API key.
    const token = getToken();
    clearToken();
    setUser(null);
    if (token) {
      await fetch(`${API_BASE}/api/v1/users/logout`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
      }).catch(() => {});
    }
    // Hard navigation so module-level caches reset. `?federated` asks Auth0 to
    // clear upstream identity-provider state too.
    window.location.href = AUTH0_ENABLED ? "/auth/logout?federated" : "/login";
  }, []);

  return {
    user,
    loading,
    logout,
    refresh: loadUser,
  };
}
