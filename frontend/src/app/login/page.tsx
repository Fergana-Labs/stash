"use client";

import { Suspense, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Header from "../../components/Header";
import { AuthPageSkeleton, SkeletonBlock } from "../../components/SkeletonStates";
import { useAuth } from "../../hooks/useAuth";
import { track } from "../../lib/analytics";
import { API_BASE, getToken, setToken, listMyWorkspaces } from "../../lib/api";
import { consumeManualAuth0Logout } from "../../lib/authLogout";

const AUTH0_ENABLED = process.env.NEXT_PUBLIC_AUTH0_ENABLED === "true";

// Dev-only: set in frontend/.env.local to land on /onboarding after every
// login (not just first registration), so the wizard can be iterated on.
const FORCE_ONBOARDING = process.env.NEXT_PUBLIC_FORCE_ONBOARDING === "true";

// FastAPI returns `detail` as either a string or an array of validation errors
// like [{ loc, msg, type }]. Flatten to a human-readable string.
function formatApiError(detail: unknown, fallback: string): string {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    const msgs = detail
      .map((d) => (d && typeof d === "object" && "msg" in d ? String(d.msg) : ""))
      .filter(Boolean);
    if (msgs.length > 0) return msgs.join("; ");
  }
  return fallback;
}

export default function LoginPage() {
  return (
    <Suspense fallback={<AuthPageSkeleton />}>
      <LoginPageInner />
    </Suspense>
  );
}

function LoginPageInner() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const cliSession = searchParams.get("cli");
  const nextPath = localNextPath(searchParams.get("next"));
  const { user, loading, logout, refresh } = useAuth();
  const [mode, setMode] = useState<"login" | "register">("login");
  const [name, setName] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [cliApproved, setCliApproved] = useState(false);
  const [justRegistered, setJustRegistered] = useState(false);

  // Normal redirect for non-CLI logins
  useEffect(() => {
    if (loading || !user || cliSession) return;

    if (justRegistered || FORCE_ONBOARDING) {
      router.push("/onboarding");
      return;
    }

    if (nextPath) {
      router.push(nextPath);
      return;
    }

    listMyWorkspaces().then(({ workspaces }) => {
      if (workspaces.length === 1) {
        router.push(`/workspaces/${workspaces[0].id}`);
      } else {
        router.push("/");
      }
    }).catch(() => {
      router.push("/");
    });
  }, [user, loading, cliSession, nextPath, router, justRegistered]);

  // Wait for useAuth to load before rendering — otherwise the signed-out form
  // flashes on every /login hit even for already-signed-in users.
  if (loading) {
    return <AuthPageSkeleton />;
  }

  if (cliApproved) {
    return <CliSuccess user={user} logout={logout} cliSession={cliSession} />;
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
      const endpoint = mode === "login" ? "login" : "register";
      const body = mode === "login"
        ? { name, password }
        : { name, display_name: name, description: "", password };
      const res = await fetch(`${API_BASE}/api/v1/users/${endpoint}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });

      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(formatApiError(data.detail, "Sign-in failed"));
      }

      const data = await res.json();
      setToken(data.api_key);
      if (mode === "register") {
        track("auth.signed_up", { via_cli: !!cliSession });
      }
      if (mode === "register" && !cliSession) {
        setJustRegistered(true);
      }

      if (cliSession) {
        const approveRes = await fetch(
          `${API_BASE}/api/v1/users/cli-auth/sessions/${cliSession}/approve`,
          {
            method: "POST",
            headers: { Authorization: `Bearer ${data.api_key}` },
          },
        );
        if (!approveRes.ok) {
          throw new Error("CLI session expired. Re-run `stash login` and try again.");
        }
        setCliApproved(true);
      }

      refresh();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Something went wrong");
    } finally {
      setSubmitting(false);
    }
  }

  // Already-signed-in + CLI session: show a dedicated authorize button instead
  // of silently approving. This way the user confirms which account the CLI
  // gets, and a fresh named key is minted rather than leaking the browser's.
  if (user && cliSession) {
    return (
      <CliShell user={user} logout={logout} cliSession={cliSession}>
        <AuthorizeCliPanel
          username={user.name}
          cliSession={cliSession}
          onApproved={() => setCliApproved(true)}
          onUseDifferentAccount={logout}
        />
      </CliShell>
    );
  }

  const ctaLabel = submitting
    ? (mode === "login" ? "Signing in..." : "Creating account...")
    : cliSession
    ? (mode === "login" ? "Sign in & authorize CLI" : "Create account & authorize CLI")
    : (mode === "login" ? "Sign in" : "Create account");

  const formBody = (
    <>
      <form onSubmit={handleSubmit} className="space-y-4">
        <FormField label="Username" type="text" placeholder="yourname" value={name} onChange={setName} autoFocus />
        <FormField label="Password" type="password" placeholder="••••••••" value={password} onChange={setPassword} />
        {error && <ErrorLine message={error} />}
        <BrandButton submitting={submitting} label={ctaLabel} />
      </form>
      <p className="text-[11px] text-muted text-center pt-1">
        {mode === "login" ? (
          <>
            New here?{" "}
            <button type="button" onClick={() => { setMode("register"); setError(""); }} className="text-brand hover:underline">
              Create an account
            </button>
          </>
        ) : (
          <>
            Already have an account?{" "}
            <button type="button" onClick={() => { setMode("login"); setError(""); }} className="text-brand hover:underline">
              Sign in
            </button>
          </>
        )}
      </p>
    </>
  );

  if (cliSession) {
    return (
      <CliShell user={user} logout={logout} cliSession={cliSession}>
        <FormCard>{formBody}</FormCard>
        <p className="text-center text-[11px] text-muted leading-relaxed max-w-[340px] mx-auto">
          By authorizing, you grant this terminal session a personal API key on your behalf.
          You can revoke it any time from your account settings.
        </p>
      </CliShell>
    );
  }

  return (
    <AuthShell
      title={mode === "login" ? "Welcome back" : "Create your stash"}
      subtitle={
        mode === "login"
          ? "Sign in to the workspace you share with your agents."
          : "One account for you and your agents."
      }
    >
      <FormCard>{formBody}</FormCard>
    </AuthShell>
  );
}

function localNextPath(value: string | null): string {
  if (!value) return "";
  if (!value.startsWith("/") || value.startsWith("//")) return "";
  return value;
}

// --- Authorize CLI (already signed-in) ---------------------------------------

function AuthorizeCliPanel({
  username,
  cliSession,
  onApproved,
  onUseDifferentAccount,
}: {
  username: string;
  cliSession: string;
  onApproved: () => void;
  onUseDifferentAccount: () => void;
}) {
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  async function handleAuthorize() {
    setError("");
    setSubmitting(true);
    try {
      const token = getToken();
      if (!token) throw new Error("Not signed in");
      const res = await fetch(
        `${API_BASE}/api/v1/users/cli-auth/sessions/${cliSession}/approve`,
        {
          method: "POST",
          headers: { Authorization: `Bearer ${token}` },
        },
      );
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(formatApiError(data.detail, "Could not authorize CLI"));
      }
      onApproved();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Something went wrong");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <FormCard>
      <div className="space-y-3 text-center">
        <p className="text-sm text-foreground">
          Authorize CLI as <span className="font-semibold">{username}</span>?
        </p>
        <p className="text-[11px] text-muted">
          A new API key scoped to this terminal will be created. You can revoke it anytime from account settings.
        </p>
        {error && <ErrorLine message={error} />}
        <button
          type="button"
          onClick={handleAuthorize}
          disabled={submitting}
          className="w-full bg-brand hover:bg-brand-hover text-white py-2.5 rounded-xl text-sm font-semibold transition-all disabled:opacity-60"
        >
          {submitting ? "Authorizing..." : "Authorize CLI"}
        </button>
        <button
          type="button"
          onClick={onUseDifferentAccount}
          className="text-[11px] text-muted hover:text-foreground"
        >
          Use a different account
        </button>
      </div>
    </FormCard>
  );
}

// --- Auth0 panel (managed deployment) ----------------------------------------

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
    if (consumeManualAuth0Logout()) {
      setHasSession(false);
      return;
    }

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

  const body =
    hasSession === null ? (
      <div className="space-y-3">
        <SkeletonBlock className="h-10 w-full rounded-lg" />
        <SkeletonBlock className="h-10 w-full rounded-xl" />
      </div>
    ) : hasSession ? (
      <Auth0Exchange cliSession={cliSession} onCliApproved={onCliApproved} />
    ) : (
      <Auth0LoginButton cliSession={cliSession} />
    );

  if (cliSession) {
    return (
      <CliShell user={user} logout={logout} cliSession={cliSession}>
        <FormCard>{body}</FormCard>
        <p className="text-center text-[11px] text-muted leading-relaxed max-w-[340px] mx-auto">
          By authorizing, you grant this terminal session a personal API key on your behalf.
          You can revoke it any time from your account settings.
        </p>
      </CliShell>
    );
  }

  return (
    <AuthShell
      title="Welcome back"
      subtitle="Sign in to the workspace you share with your agents."
    >
      <FormCard>{body}</FormCard>
    </AuthShell>
  );
}

// Lazy re-exports so the managed/ code is never loaded in OSS builds.
function Auth0LoginButton(props: { cliSession: string | null }) {
  const [Comp, setComp] = useState<React.ComponentType<{ cliSession: string | null }> | null>(null);
  useEffect(() => {
    import("@managed/auth0/LoginButton").then((m) => setComp(() => m.default));
  }, []);
  if (!Comp) return <SkeletonBlock className="h-10 w-full rounded-xl" />;
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
  if (!Comp) return <SkeletonBlock className="h-10 w-full rounded-xl" />;
  return <Comp cliSession={props.cliSession} onCliApproved={props.onCliApproved} />;
}

// --- Branded auth shell (plain login + Auth0) ----------------------------------

// The auth shell only ever renders for signed-out visitors, so it skips the app
// Header (whose only signed-out affordance is a link right back to /login).
function AuthShell({
  title,
  subtitle,
  children,
}: {
  title: string;
  subtitle: string;
  children: React.ReactNode;
}) {
  return (
    <div className="min-h-screen flex flex-col relative overflow-hidden">
      <AuthBackdrop />
      <main className="flex-1 flex items-center justify-center px-4 py-12 relative">
        <div className="w-full max-w-[400px] space-y-7 animate-in fade-in slide-in-from-bottom-3 duration-500">
          <div className="space-y-3 text-center">
            <Wordmark />
            <h1 className="font-display text-[32px] leading-[1.05] font-bold tracking-tight text-foreground">
              {title}
            </h1>
            <p className="text-sm text-dim">{subtitle}</p>
          </div>
          {children}
        </div>
      </main>
    </div>
  );
}

function Wordmark() {
  return (
    <div className="flex items-center justify-center gap-2 font-display text-[19px] font-bold tracking-[-0.03em] text-foreground">
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img src="/octopus.svg" alt="" width={24} height={27} />
      stash
    </div>
  );
}

// --- CLI hero shell ----------------------------------------------------------

function CliShell({
  user,
  logout,
  cliSession,
  children,
}: {
  user: ReturnType<typeof useAuth>["user"];
  logout: ReturnType<typeof useAuth>["logout"];
  cliSession: string;
  children: React.ReactNode;
}) {
  return (
    <div className="min-h-screen flex flex-col relative overflow-hidden">
      <AuthBackdrop />
      <Header user={user} onLogout={logout} />
      <main className="flex-1 flex items-center justify-center px-4 py-10 relative">
        <div className="w-full max-w-[420px] space-y-7 animate-in fade-in slide-in-from-bottom-3 duration-500">
          <div className="space-y-3 text-center">
            <div className="inline-flex items-center gap-2 px-2.5 py-1 rounded-full bg-surface/80 backdrop-blur border border-border text-[10px] font-mono uppercase tracking-[0.18em] text-muted">
              <span className="w-1 h-1 rounded-full bg-brand animate-pulse" />
              Secure handshake
            </div>
            <h1 className="font-display text-[32px] leading-[1.05] font-bold tracking-tight text-foreground">
              Authorize the <span className="text-brand">Stash CLI</span>
            </h1>
            <p className="text-sm text-dim max-w-[340px] mx-auto">
              Your terminal is waiting for a signature. Sign in below to complete the connection.
            </p>
          </div>
          <SessionCodePanel code={cliSession} />
          {children}
        </div>
      </main>
    </div>
  );
}

function CliSuccess({
  user,
  logout,
  cliSession,
}: {
  user: ReturnType<typeof useAuth>["user"];
  logout: ReturnType<typeof useAuth>["logout"];
  cliSession: string | null;
}) {
  return (
    <div className="min-h-screen flex flex-col relative overflow-hidden">
      <AuthBackdrop />
      <Header user={user} onLogout={logout} />
      <main className="flex-1 flex items-center justify-center px-4 py-12 relative">
        <div className="w-full max-w-md text-center space-y-5 animate-in fade-in slide-in-from-bottom-2 duration-500">
          <div className="inline-flex items-center justify-center w-14 h-14 rounded-2xl bg-brand/10 border border-brand/30 text-brand text-2xl">
            &#10003;
          </div>
          <div className="space-y-1.5">
            <h2 className="font-display text-2xl font-bold tracking-tight text-foreground">
              CLI authorized
            </h2>
            <p className="text-sm text-dim">
              Your terminal is now signed in. You can close this tab and head back.
            </p>
          </div>
          <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-surface border border-border text-[11px] font-mono text-muted">
            <span className="w-1.5 h-1.5 rounded-full bg-brand animate-pulse" />
            session {shortCode(cliSession)} verified
          </div>
        </div>
      </main>
    </div>
  );
}

// --- Building blocks ---------------------------------------------------------

function FormCard({ children }: { children: React.ReactNode }) {
  return (
    <div className="rounded-2xl border border-border bg-surface/70 backdrop-blur shadow-sm p-6 space-y-4">
      {children}
    </div>
  );
}

function FormField({
  label,
  type,
  placeholder,
  value,
  onChange,
  autoFocus,
}: {
  label: string;
  type: string;
  placeholder: string;
  value: string;
  onChange: (v: string) => void;
  autoFocus?: boolean;
}) {
  return (
    <label className="block space-y-1.5">
      <span className="block text-[10px] font-mono uppercase tracking-[0.14em] text-muted">
        {label}
      </span>
      <input
        type={type}
        placeholder={placeholder}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        autoFocus={autoFocus}
        className="w-full px-3.5 py-2.5 rounded-lg border border-border bg-background text-foreground text-sm placeholder:text-muted focus:outline-none focus:border-brand focus:ring-2 focus:ring-brand/20 transition-all"
        required
      />
    </label>
  );
}

function BrandButton({ submitting, label }: { submitting: boolean; label: string }) {
  return (
    <button
      type="submit"
      disabled={submitting}
      className="group relative w-full bg-brand hover:bg-brand-hover text-white py-2.5 rounded-xl text-sm font-semibold transition-all disabled:opacity-60 shadow-[0_8px_24px_-8px_oklch(0.7_0.14_55_/_0.5)] hover:shadow-[0_10px_28px_-6px_oklch(0.7_0.14_55_/_0.6)]"
    >
      <span className="inline-flex items-center justify-center gap-2">
        {label}
        {!submitting && (
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" className="transition-transform group-hover:translate-x-0.5">
            <path d="M5 12h14M13 5l7 7-7 7" />
          </svg>
        )}
      </span>
    </button>
  );
}

function ErrorLine({ message }: { message: string }) {
  return (
    <p className="text-xs text-error flex items-center gap-1.5">
      <span className="w-1 h-1 rounded-full bg-error" />
      {message}
    </p>
  );
}

function SessionCodePanel({ code }: { code: string }) {
  return (
    <div className="rounded-xl border border-border bg-background/80 backdrop-blur p-4 flex items-center justify-between gap-3">
      <div className="space-y-1">
        <div className="text-[10px] font-mono uppercase tracking-[0.2em] text-muted">CLI session</div>
        <div className="font-mono text-base font-semibold text-foreground tracking-wide">{formatCode(code)}</div>
      </div>
      <div className="flex items-center gap-1.5 text-[10px] font-mono uppercase tracking-wider text-dim shrink-0">
        <span className="relative flex w-2 h-2">
          <span className="absolute inset-0 rounded-full bg-brand opacity-60 animate-ping" />
          <span className="relative w-2 h-2 rounded-full bg-brand" />
        </span>
        Awaiting
      </div>
    </div>
  );
}

function AuthBackdrop() {
  return (
    <div aria-hidden className="absolute inset-0 -z-10 overflow-hidden">
      <div
        className="absolute inset-0"
        style={{
          background:
            "radial-gradient(900px 500px at 80% -10%, oklch(0.7 0.14 55 / 0.18), transparent 60%), radial-gradient(700px 400px at -10% 110%, oklch(0.7 0.14 55 / 0.10), transparent 55%)",
        }}
      />
      <div
        className="absolute inset-0 opacity-[0.35]"
        style={{
          backgroundImage:
            "linear-gradient(to right, var(--border-subtle-color) 1px, transparent 1px), linear-gradient(to bottom, var(--border-subtle-color) 1px, transparent 1px)",
          backgroundSize: "32px 32px",
          maskImage: "radial-gradient(ellipse 70% 55% at 50% 45%, black, transparent 80%)",
          WebkitMaskImage: "radial-gradient(ellipse 70% 55% at 50% 45%, black, transparent 80%)",
        }}
      />
    </div>
  );
}

function shortCode(code: string | null): string {
  if (!code) return "";
  return code.length > 8 ? `${code.slice(0, 4)}\u2026${code.slice(-4)}` : code;
}

function formatCode(code: string): string {
  const trimmed = code.length > 12 ? code.slice(0, 12) : code;
  return trimmed.match(/.{1,4}/g)?.join(" \u2014 ") ?? trimmed;
}
