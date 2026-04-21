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
  const [submitting, setSubmitting] = useState(false);

  async function exchange(): Promise<string> {
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
    setToken(data.api_key);
    return data.api_key;
  }

  // Non-CLI path: exchange silently and redirect. The user is already signed
  // into Auth0 — getting the mc_ key is a bookkeeping step, not a decision.
  useEffect(() => {
    if (cliSession) return;
    let cancelled = false;
    (async () => {
      try {
        await exchange();
        if (cancelled) return;
        const { workspaces } = await listMyWorkspaces();
        router.push(workspaces.length === 1 ? `/workspaces/${workspaces[0].id}` : "/");
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : "Sign-in failed");
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [cliSession, router]);

  async function handleAuthorizeCli() {
    if (!cliSession) return;
    setError("");
    setSubmitting(true);
    try {
      const apiKey = await exchange();
      const approveRes = await fetch(
        `${API_URL}/api/v1/users/cli-auth/sessions/${cliSession}/approve`,
        {
          method: "POST",
          headers: { Authorization: `Bearer ${apiKey}` },
        },
      );
      if (!approveRes.ok) throw new Error("CLI session expired. Re-run `stash signin`.");
      onCliApproved?.();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not authorize CLI");
    } finally {
      setSubmitting(false);
    }
  }

  if (cliSession) {
    return (
      <div className="text-center space-y-3">
        <p className="text-sm text-foreground">Authorize CLI with your Auth0 account?</p>
        <p className="text-[11px] text-muted">
          A new API key scoped to this terminal will be created. You can revoke it anytime from account settings.
        </p>
        {error && <p className="text-xs text-red-400">{error}</p>}
        <button
          type="button"
          onClick={handleAuthorizeCli}
          disabled={submitting}
          className="w-full bg-brand hover:bg-brand-hover text-white py-2.5 rounded-xl text-sm font-semibold transition-all disabled:opacity-60"
        >
          {submitting ? "Authorizing..." : "Authorize CLI"}
        </button>
        <a href="/auth/logout" className="text-[11px] text-muted hover:text-foreground">
          Use a different account
        </a>
      </div>
    );
  }

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
