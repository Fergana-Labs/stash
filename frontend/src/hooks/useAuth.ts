"use client";

import { useCallback, useEffect, useState } from "react";
import { ApiError, clearToken, getMe, getToken } from "../lib/api";
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

  const logout = useCallback(() => {
    clearToken();
    setUser(null);
    if (AUTH0_ENABLED) {
      // Destroys the Next.js app-session cookie and redirects to Auth0's
      // /v2/logout so the tenant SSO cookie is also cleared — otherwise "sign
      // in again" silently re-auths into the same account.
      window.location.href = "/auth/logout";
    }
  }, []);

  return {
    user,
    loading,
    logout,
    refresh: loadUser,
  };
}
