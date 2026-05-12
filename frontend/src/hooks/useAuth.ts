"use client";

import { useCallback, useEffect, useState } from "react";
import { ApiError, clearToken, getMe, getToken } from "../lib/api";
import { User } from "../lib/types";

const AUTH0_ENABLED = process.env.NEXT_PUBLIC_AUTH0_ENABLED === "true";
const API_URL = process.env.NEXT_PUBLIC_API_URL || "";

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

  const logout = useCallback(() => {
    // Drop local state first so the UI flips to signed-out the moment the
    // user clicks — don't make them wait on a server round-trip. Revoke the
    // key in the background; `keepalive` lets the request survive the
    // navigation we're about to do.
    const token = getToken();
    clearToken();
    setUser(null);
    if (token) {
      fetch(`${API_URL}/api/v1/users/logout`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
        keepalive: true,
      }).catch(() => {});
    }
    // Hard navigation so module-level caches reset. `?federated` makes the
    // Auth0 SDK kill the tenant SSO cookie too — without it, /login silently
    // re-auths via the surviving SSO cookie and lands the user back on their
    // workspace page.
    window.location.href = AUTH0_ENABLED ? "/auth/logout?federated" : "/login";
  }, []);

  return {
    user,
    loading,
    logout,
    refresh: loadUser,
  };
}
