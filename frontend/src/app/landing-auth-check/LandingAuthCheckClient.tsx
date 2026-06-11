"use client";

import { useSearchParams } from "next/navigation";
import { useEffect } from "react";

import {
  allowedLandingParentOrigin,
  landingAuthStatusMessage,
} from "@/lib/landingAuthCheck";
import { API_BASE, getToken } from "@/lib/api";

const AUTH0_ENABLED = process.env.NEXT_PUBLIC_AUTH0_ENABLED === "true";

export default function LandingAuthCheckClient() {
  const searchParams = useSearchParams();

  useEffect(() => {
    const parentOrigin = allowedLandingParentOrigin(searchParams.get("origin"));
    if (!parentOrigin) return;
    const targetOrigin = parentOrigin;

    let cancelled = false;

    async function postStatus() {
      const signedIn = await hasStashSession();
      if (cancelled) return;

      window.parent.postMessage(landingAuthStatusMessage(signedIn), targetOrigin);
    }

    void postStatus();

    return () => {
      cancelled = true;
    };
  }, [searchParams]);

  return null;
}

async function hasStashSession(): Promise<boolean> {
  if (await hasApiKeySession()) return true;
  if (await hasAuth0Session()) return true;
  return false;
}

async function hasApiKeySession(): Promise<boolean> {
  let token: string | null;
  try {
    token = getToken();
  } catch {
    return false;
  }

  if (!token) return false;

  try {
    const response = await fetch(`${API_BASE}/api/v1/users/me`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    return response.ok;
  } catch {
    return false;
  }
}

async function hasAuth0Session(): Promise<boolean> {
  if (!AUTH0_ENABLED) return false;

  try {
    const response = await fetch("/auth/profile", { credentials: "include" });
    return response.ok;
  } catch {
    return false;
  }
}
