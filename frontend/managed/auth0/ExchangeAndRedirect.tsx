"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { API_BASE, clearToken, getAuth0AccessToken, listMyWorkspaces } from "@/lib/api";

type Props = {
  cliSession?: string | null;
  onCliApproved?: () => void;
};

export default function ExchangeAndRedirect({ cliSession, onCliApproved }: Props) {
  const router = useRouter();
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const auth0Token = useCallback(async (): Promise<string> => {
    const token = await getAuth0AccessToken();
    if (!token) throw new Error("Auth0 session missing");
    return token;
  }, []);

  const provisionBrowserSession = useCallback(async (): Promise<{
    token: string;
    created: boolean;
  }> => {
    const token = await auth0Token();
    const res = await fetch(`${API_BASE}/api/v1/auth0/session`, {
      method: "POST",
      headers: { Authorization: `Bearer ${token}` },
    });
    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      throw new Error(data.detail || "Session provisioning failed");
    }
    const data = await res.json();
    clearToken();
    return { token, created: !!data.created };
  }, [auth0Token]);

  // Non-CLI path: provision silently and redirect. The user is already signed
  // into Auth0; this only makes sure their backend user row exists.
  useEffect(() => {
    if (cliSession) return;
    let cancelled = false;
    (async () => {
      let created = false;
      try {
        ({ created } = await provisionBrowserSession());
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : "Sign-in failed");
        return;
      }
      if (cancelled) return;
      // First-time sign-in goes through onboarding, same as the password
      // register flow. The exchange already created their workspace.
      if (created) {
        router.push("/onboarding");
        return;
      }
      // Returning user. If the workspace lookup hiccups (transient backend),
      // don't flash a "sign-in failed" error; just land on /, which can
      // reload the list itself.
      const target = await listMyWorkspaces()
        .then(({ workspaces }) =>
          workspaces.length === 1 ? `/workspaces/${workspaces[0].id}` : "/",
        )
        .catch(() => "/");
      if (!cancelled) router.push(target);
    })();
    return () => {
      cancelled = true;
    };
  }, [cliSession, provisionBrowserSession, router]);

  async function handleAuthorizeCli() {
    if (!cliSession) return;
    setError("");
    setSubmitting(true);
    try {
      const { token } = await provisionBrowserSession();
      const approveRes = await fetch(
        `${API_BASE}/api/v1/users/cli-auth/sessions/${cliSession}/approve`,
        {
          method: "POST",
          headers: { Authorization: `Bearer ${token}` },
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
