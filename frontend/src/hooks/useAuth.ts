"use client";

import { useCallback, useEffect, useState } from "react";
import { clearToken, getMe, setToken } from "../lib/api";
import { User } from "../lib/types";

export function useAuth() {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  const loadUser = useCallback(async () => {
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
    const token = localStorage.getItem("moltchat_token");
    if (token) {
      loadUser();
    } else {
      setLoading(false);
    }
  }, [loadUser]);

  const login = useCallback(
    (apiKey: string) => {
      setToken(apiKey);
      loadUser();
    },
    [loadUser]
  );

  const logout = useCallback(() => {
    clearToken();
    setUser(null);
  }, []);

  return { user, loading, login, logout, refresh: loadUser };
}
