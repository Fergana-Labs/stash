"use client";

import { useEffect, useLayoutEffect, useRef, useCallback } from "react";
import { useUser } from "@auth0/nextjs-auth0/client";
import { fetchAccessToken } from "@/lib/accessToken";
import { setToken, clearToken } from "@/lib/api";

/**
 * Invisible component that keeps the in-memory auth token in sync with the
 * Auth0 session cookie. Mounts once inside <Auth0Provider>.
 *
 * - On login: fetches the access token and stores it for apiFetch calls.
 * - On logout: clears the stored token.
 * - Refreshes every 60 seconds so tokens never silently expire mid-session.
 * - Refreshes on tab focus (visibilitychange) to handle long-idle tabs.
 */
export default function AuthTokenBridge() {
  const { user, isLoading } = useUser();
  const didSync = useRef(false);

  const syncToken = useCallback(async () => {
    if (isLoading) return;
    if (!user) {
      clearToken();
      didSync.current = false;
      return;
    }
    const token = await fetchAccessToken();
    if (token) {
      setToken(token);
      didSync.current = true;
    } else {
      // Session cookie is gone server-side — send to login
      window.location.href = "/api/auth/login";
    }
  }, [isLoading, user]);

  // Sync immediately whenever auth state changes
  useLayoutEffect(() => {
    void syncToken();
  }, [syncToken]);

  // Periodic refresh + visibility-change refresh
  useEffect(() => {
    if (isLoading || !user) return;

    let cancelled = false;
    const refresh = async () => {
      const token = await fetchAccessToken();
      if (!cancelled) {
        if (token) {
          setToken(token);
        } else {
          window.location.href = "/api/auth/login";
        }
      }
    };

    const onVisibility = () => {
      if (document.visibilityState === "visible") void refresh();
    };

    const intervalId = window.setInterval(refresh, 60_000);
    document.addEventListener("visibilitychange", onVisibility);
    return () => {
      cancelled = true;
      window.clearInterval(intervalId);
      document.removeEventListener("visibilitychange", onVisibility);
    };
  }, [isLoading, user]);

  return null;
}
