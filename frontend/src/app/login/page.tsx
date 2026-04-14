"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Header from "../../components/Header";
import { useAuth } from "../../hooks/useAuth";
import { setToken } from "../../lib/api";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:3456";

export default function LoginPage() {
  const router = useRouter();
  const { user, logout, refresh } = useAuth();
  const [name, setName] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (user) {
      router.push("/memory");
    }
  }, [user, router]);

  if (user) {
    return null;
  }

  async function handlePasswordLogin(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setSubmitting(true);
    try {
      const res = await fetch(`${API_URL}/api/v1/users/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name, password }),
      });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.detail || "Login failed");
      }
      const data = await res.json();
      setToken(data.api_key);
      refresh();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Login failed");
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
            <h2 className="text-base font-semibold text-foreground mb-1">Sign in</h2>
            <p className="text-sm text-dim mb-6">
              Secure login via Auth0 — Google, GitHub, email and more.
            </p>
            <a
              href="/api/auth/login"
              className="block w-full text-center bg-brand hover:bg-brand-hover text-foreground py-2.5 rounded-xl text-sm font-medium transition-colors"
            >
              Continue with Auth0
            </a>
          </div>

          <div className="rounded-2xl border border-border bg-surface p-6">
            <h2 className="text-base font-semibold text-foreground mb-4">Password login</h2>
            <form onSubmit={handlePasswordLogin} className="space-y-3">
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
                {submitting ? "Signing in..." : "Sign in"}
              </button>
            </form>
          </div>
        </div>
      </main>
    </div>
  );
}
