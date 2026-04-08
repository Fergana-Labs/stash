"use client";

import { useCallback, useEffect, useState } from "react";
import { useUser } from "@auth0/nextjs-auth0/client";
import { clearToken, getMe, getToken } from "../lib/api";
import { User } from "../lib/types";

/**
 * Unified auth hook.
 *
 * Human accounts  → Auth0 session (httpOnly cookie). AuthTokenBridge keeps
 *                   the access token in memory; apiFetch picks it up.
 * Persona accounts → mc_ API key in localStorage (legacy path).
 */
export function useAuth() {
  const { user: auth0User, isLoading: auth0Loading } = useUser();
  const [boozleUser, setBoozleUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  const loadBoozleUser = useCallback(async () => {
    try {
      const me = await getMe();
      setBoozleUser(me);
    } catch {
      setBoozleUser(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (auth0Loading) return;

    if (auth0User) {
      // Auth0 session present. AuthTokenBridge has already put the access
      // token into the api.ts token store, so getMe() will be authenticated.
      loadBoozleUser();
      return;
    }

    // No Auth0 session — check for a legacy mc_ API key.
    if (getToken()) {
      loadBoozleUser();
    } else {
      setLoading(false);
    }
  }, [auth0User, auth0Loading, loadBoozleUser]);

  const logout = useCallback(() => {
    clearToken();
    setBoozleUser(null);
    if (auth0User) {
      window.location.href = "/api/auth/logout";
    }
  }, [auth0User]);

  return {
    user: boozleUser,
    loading: loading || auth0Loading,
    logout,
    refresh: loadBoozleUser,
  };
}
