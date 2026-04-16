"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { listMyWorkspaces, setToken } from "@/lib/api";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:3456";

type Props = {
  cliSession?: string | null;
  onCliApproved?: () => void;
};

export default function ExchangeAndRedirect({ cliSession, onCliApproved }: Props) {
  const router = useRouter();
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;

    async function run() {
      try {
        const tokenRes = await fetch("/auth/access-token");
        if (!tokenRes.ok) throw new Error("Auth0 session missing");
        const { token } = await tokenRes.json();

        const res = await fetch(`${API_URL}/api/v1/auth0/exchange`, {
          method: "POST",
          headers: { Authorization: `Bearer ${token}` },
        });
        if (!res.ok) {
          const data = await res.json().catch(() => ({}));
          throw new Error(data.detail || "Token exchange failed");
        }
        const data = await res.json();
        if (cancelled) return;

        setToken(data.api_key);

        if (cliSession) {
          await fetch(`${API_URL}/api/v1/users/cli-auth/sessions/${cliSession}/approve`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ api_key: data.api_key, username: data.name }),
          });
          onCliApproved?.();
          return;
        }

        const { workspaces } = await listMyWorkspaces();
        router.push(workspaces.length === 1 ? `/workspaces/${workspaces[0].id}` : "/");
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : "Sign-in failed");
      }
    }

    run();
    return () => {
      cancelled = true;
    };
  }, [cliSession, onCliApproved, router]);

  if (error) {
    return (
      <div className="text-center space-y-3">
        <p className="text-sm text-red-400">{error}</p>
        <a href="/auth/login" className="text-sm text-brand hover:underline">
          Try again
        </a>
      </div>
    );
  }

  return (
    <div className="text-center">
      <p className="text-sm text-muted">Finishing sign-in…</p>
    </div>
  );
}
