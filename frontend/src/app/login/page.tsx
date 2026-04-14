"use client";

import { useRouter } from "next/navigation";
import Header from "../../components/Header";
import { useAuth } from "../../hooks/useAuth";

export default function LoginPage() {
  const router = useRouter();
  const { user, logout } = useAuth();

  if (user) {
    router.push("/memory");
    return null;
  }

  return (
    <div className="min-h-screen flex flex-col">
      <Header user={user} onLogout={logout} />
      <main className="flex-1 flex items-center justify-center px-4 py-12">
        <div className="w-full max-w-sm">
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
            <p className="text-xs text-muted text-center mt-4">
              New accounts are created automatically on first login.
            </p>
          </div>
        </div>
      </main>
    </div>
  );
}
