"use client";

import { Suspense, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Header from "../../components/Header";
import { useAuth } from "../../hooks/useAuth";
import { setToken, listMyWorkspaces } from "../../lib/api";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:3456";
const AUTH0_ENABLED = process.env.NEXT_PUBLIC_AUTH0_ENABLED === "true";

export default function LoginPage() {
  return (
    <Suspense fallback={<div className="min-h-screen flex items-center justify-center text-muted">Loading...</div>}>
      <LoginPageInner />
    </Suspense>
  );
}

function LoginPageInner() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const cliSession = searchParams.get("cli");
  const { user, logout, refresh } = useAuth();
  const [name, setName] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [cliApproved, setCliApproved] = useState(false);
  const [isRegister, setIsRegister] = useState(false);

  // If already logged in and this is a CLI auth request, approve immediately
  useEffect(() => {
    if (!user || !cliSession || cliApproved) return;
    const token = localStorage.getItem("stash_token");
    if (!token) return;

    fetch(`${API_URL}/api/v1/users/cli-auth/sessions/${cliSession}/approve`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ api_key: token, username: user.name }),
    })
      .then((res) => {
        if (res.ok) setCliApproved(true);
      })
      .catch(() => {});
  }, [user, cliSession, cliApproved]);

  // Normal redirect for non-CLI logins
  useEffect(() => {
    if (!user || cliSession) return;

    listMyWorkspaces().then(({ workspaces }) => {
      if (workspaces.length === 1) {
        router.push(`/workspaces/${workspaces[0].id}`);
      } else {
        router.push("/");
      }
    }).catch(() => {
      router.push("/");
    });
  }, [user, cliSession, router]);

  if (cliApproved) {
    return (
      <div className="min-h-screen flex flex-col">
        <Header user={user} onLogout={logout} />
        <main className="flex-1 flex items-center justify-center px-4 py-12">
          <div className="w-full max-w-sm text-center space-y-3">
            <div className="text-3xl">&#10003;</div>
            <h2 className="text-base font-semibold text-foreground">CLI authenticated</h2>
            <p className="text-sm text-muted">You can close this tab and return to your terminal.</p>
          </div>
        </main>
      </div>
    );
  }

  if (user && !cliSession) {
    return null;
  }

  if (AUTH0_ENABLED) {
    return (
      <Auth0LoginPanel
        user={user}
        logout={logout}
        cliSession={cliSession}
        onCliApproved={() => setCliApproved(true)}
      />
    );
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setSubmitting(true);
    try {
      const endpoint = isRegister ? "/api/v1/users/register" : "/api/v1/users/login";
      const body = isRegister
        ? { name, display_name: name, description: "", password }
        : { name, password };
      const res = await fetch(`${API_URL}${endpoint}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.detail || (isRegister ? "Registration failed" : "Login failed"));
      }
      const data = await res.json();
      setToken(data.api_key);

      // If this is a CLI auth flow, approve the session
      if (cliSession) {
        await fetch(`${API_URL}/api/v1/users/cli-auth/sessions/${cliSession}/approve`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ api_key: data.api_key, username: data.name }),
        });
        setCliApproved(true);
      }

      refresh();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Something went wrong");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="min-h-screen flex flex-col">
      <Header user={user} onLogout={logout} />
      <main className="flex-1 flex items-center justify-center px-4 py-12">
        <div className="w-full max-w-sm space-y-4">
          <div className="rounded-2xl border border-border bg-surface p-6">
            <h2 className="text-base font-semibold text-foreground mb-4">
              {cliSession
                ? isRegister ? "Create an account to authorize the CLI" : "Sign in to authorize the CLI"
                : isRegister ? "Create an account" : "Sign in"}
            </h2>
            <form onSubmit={handleSubmit} className="space-y-3">
              <input
                type="text"
                placeholder="Username"
                value={name}
                onChange={(e) => setName(e.target.value)}
                className="w-full px-3 py-2 rounded-lg border border-border bg-background text-foreground text-sm focus:outline-none focus:ring-1 focus:ring-brand"
                required
              />
              <input
                type="password"
                placeholder="Password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="w-full px-3 py-2 rounded-lg border border-border bg-background text-foreground text-sm focus:outline-none focus:ring-1 focus:ring-brand"
                required
              />
              {error && <p className="text-xs text-red-400">{error}</p>}
              <button
                type="submit"
                disabled={submitting}
                className="w-full bg-surface-hover hover:bg-border text-foreground py-2.5 rounded-xl text-sm font-medium transition-colors disabled:opacity-50"
              >
                {submitting ? (isRegister ? "Creating account..." : "Signing in...") : (isRegister ? "Create account" : "Sign in")}
              </button>
            </form>
            <p className="mt-3 text-center text-xs text-muted">
              {isRegister ? "Already have an account?" : "Don\u2019t have an account?"}{" "}
              <button
                type="button"
                onClick={() => { setIsRegister(!isRegister); setError(""); }}
                className="text-brand hover:underline"
              >
                {isRegister ? "Sign in" : "Create one"}
              </button>
            </p>
          </div>
        </div>
      </main>
    </div>
  );
}

type Auth0PanelProps = {
  user: ReturnType<typeof useAuth>["user"];
  logout: ReturnType<typeof useAuth>["logout"];
  cliSession: string | null;
  onCliApproved: () => void;
};

function Auth0LoginPanel({ user, logout, cliSession, onCliApproved }: Auth0PanelProps) {
  const [hasSession, setHasSession] = useState<boolean | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await fetch("/auth/profile", { credentials: "include" });
        if (!cancelled) setHasSession(res.ok);
      } catch {
        if (!cancelled) setHasSession(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <div className="min-h-screen flex flex-col">
      <Header user={user} onLogout={logout} />
      <main className="flex-1 flex items-center justify-center px-4 py-12">
        <div className="w-full max-w-sm space-y-4">
          <div className="rounded-2xl border border-border bg-surface p-6">
            <h2 className="text-base font-semibold text-foreground mb-4">
              {cliSession ? "Sign in to authorize the CLI" : "Sign in"}
            </h2>
            {hasSession === null ? (
              <p className="text-sm text-muted text-center">Loading…</p>
            ) : hasSession ? (
              <Auth0Exchange cliSession={cliSession} onCliApproved={onCliApproved} />
            ) : (
              <Auth0LoginButton cliSession={cliSession} />
            )}
          </div>
        </div>
      </main>
    </div>
  );
}

// Lazy re-exports so the managed/ code is never loaded in OSS builds.
function Auth0LoginButton(props: { cliSession: string | null }) {
  const [Comp, setComp] = useState<React.ComponentType<{ cliSession: string | null }> | null>(null);
  useEffect(() => {
    import("@managed/auth0/LoginButton").then((m) => setComp(() => m.default));
  }, []);
  if (!Comp) return null;
  return <Comp cliSession={props.cliSession} />;
}

function Auth0Exchange(props: { cliSession: string | null; onCliApproved: () => void }) {
  const [Comp, setComp] = useState<React.ComponentType<{
    cliSession: string | null;
    onCliApproved: () => void;
  }> | null>(null);
  useEffect(() => {
    import("@managed/auth0/ExchangeAndRedirect").then((m) => setComp(() => m.default));
  }, []);
  if (!Comp) return null;
  return <Comp cliSession={props.cliSession} onCliApproved={props.onCliApproved} />;
}
