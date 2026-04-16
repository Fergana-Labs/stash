"use client";

import { useCallback, useEffect, useState } from "react";
import { useUser } from "@auth0/nextjs-auth0/client";
import { getMe } from "../lib/api";
import { User } from "../lib/types";

/**
 * Unified auth hook.
 *
 * Human accounts  → Auth0 session (httpOnly cookie managed by the Auth0 SDK).
 * Persona accounts → API key stored in an httpOnly iron-session cookie via
 *                    the BFF (/api/persona/session). Never touches localStorage.
 *
 * The BFF proxy (/api/proxy/*) reads whichever cookie is present and attaches
 * the Authorization header server-side on every API call.
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
      // Auth0 session present — the BFF proxy will attach the JWT automatically.
      loadOctopusUser();
      return;
    }

    // No Auth0 session — check for a persona session cookie via the BFF.
    fetch("/api/persona/session")
      .then((r) => r.json())
      .then((data) => {
        if (data.authenticated) {
          loadOctopusUser();
        } else {
          setLoading(false);
        }
      })
      .catch(() => setLoading(false));
  }, [auth0User, auth0Loading, loadOctopusUser]);

  const logout = useCallback(async () => {
    setOctopusUser(null);
    if (auth0User) {
      // Clear persona session cookie as well (belt-and-suspenders)
      await fetch("/api/persona/session", { method: "DELETE" }).catch(() => {});
      window.location.href = "/api/auth/logout";
    } else {
      // Persona logout — clear the httpOnly session cookie
      await fetch("/api/persona/session", { method: "DELETE" });
      window.location.href = "/login";
    }
  }, [auth0User]);

  return {
    user: octopusUser,
    loading: loading || auth0Loading,
    logout,
    refresh: loadOctopusUser,
  };
}
