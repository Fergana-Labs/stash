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
  const [octopusUser, setOctopusUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  const loadOctopusUser = useCallback(async () => {
    try {
      const me = await getMe();
      setOctopusUser(me);
    } catch {
      setOctopusUser(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (auth0Loading) return;

    if (auth0User) {
      // Auth0 session present. AuthTokenBridge has already put the access
      // token into the api.ts token store, so getMe() will be authenticated.
      loadOctopusUser();
      return;
    }

    // No Auth0 session — check for a legacy mc_ API key.
    if (getToken()) {
      loadOctopusUser();
    } else {
      setLoading(false);
    }
  }, [auth0User, auth0Loading, loadOctopusUser]);

  const logout = useCallback(() => {
    clearToken();
    setOctopusUser(null);
    if (auth0User) {
      window.location.href = "/api/auth/logout";
    }
  }, [auth0User]);

  return {
    user: octopusUser,
    loading: loading || auth0Loading,
    logout,
    refresh: loadOctopusUser,
  };
}
