"use client";

import { useCallback, useEffect, useState } from "react";
import { clearToken, getMe, getToken } from "../lib/api";
import { User } from "../lib/types";

/**
 * Auth hook. Reads the API key from localStorage and loads /users/me.
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
    } catch {
      setUser(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadUser();
  }, [loadUser]);

  const logout = useCallback(() => {
    clearToken();
    setUser(null);
  }, []);

  return {
    user,
    loading,
    logout,
    refresh: loadUser,
  };
}
