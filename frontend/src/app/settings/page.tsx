"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Header from "../../components/Header";
import { useAuth } from "../../hooks/useAuth";
import {
  ApiError,
  ApiKeyInfo,
  listMyKeys,
  revokeMyKey,
  updateMe,
} from "../../lib/api";
import { User } from "../../lib/types";

const AUTH0_ENABLED = process.env.NEXT_PUBLIC_AUTH0_ENABLED === "true";

export default function SettingsPage() {
  const router = useRouter();
  const { user, loading, logout, refresh } = useAuth();

  useEffect(() => {
    if (!loading && !user) router.replace("/login");
  }, [loading, user, router]);

  if (loading || !user) {
    return (
      <div className="min-h-screen flex items-center justify-center text-muted">Loading...</div>
    );
  }

  return (
    <div className="min-h-screen flex flex-col">
      <Header user={user} onLogout={logout} />
      <main className="flex-1 px-4 py-10">
        <div className="w-full max-w-2xl mx-auto space-y-8">
          <div>
            <h1 className="text-2xl font-semibold text-foreground">Account settings</h1>
            <p className="text-sm text-muted mt-1">
              Update your profile, manage active sessions, and change your password.
            </p>
          </div>
          <Profile user={user} onUpdated={refresh} />
          <ActiveSessions />
          {!AUTH0_ENABLED && <ChangePassword />}
        </div>
      </main>
    </div>
  );
}

function Profile({ user, onUpdated }: { user: User; onUpdated: () => void }) {
  const [displayName, setDisplayName] = useState(user.display_name || "");
  const [description, setDescription] = useState(user.description || "");
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState<{ kind: "ok" | "err"; text: string } | null>(null);

  useEffect(() => {
    setDisplayName(user.display_name || "");
    setDescription(user.description || "");
  }, [user]);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    setMsg(null);
    try {
      await updateMe({
        display_name: displayName || undefined,
        description: description || undefined,
      });
      onUpdated();
      setMsg({ kind: "ok", text: "Saved." });
    } catch (e) {
      const text = e instanceof ApiError ? e.message : "Could not save";
      setMsg({ kind: "err", text });
    } finally {
      setSaving(false);
    }
  }

  return (
    <section className="rounded-2xl border border-border bg-surface p-6 space-y-4">
      <div>
        <h2 className="text-base font-semibold text-foreground">Profile</h2>
        <p className="text-xs text-muted mt-0.5">
          Signed in as <span className="font-mono">{user.name}</span>.
        </p>
      </div>
      <form onSubmit={handleSubmit} className="space-y-3">
        <TextField
          placeholder="Display name"
          value={displayName}
          onChange={setDisplayName}
        />
        <TextField
          placeholder="Description"
          value={description}
          onChange={setDescription}
        />
        {msg && (
          <p className={`text-xs ${msg.kind === "ok" ? "text-green-500" : "text-error"}`}>
            {msg.text}
          </p>
        )}
        <button
          type="submit"
          disabled={saving}
          className="bg-brand hover:bg-brand-hover disabled:opacity-60 text-white text-sm font-semibold px-4 py-2 rounded-lg transition-colors"
        >
          {saving ? "Saving…" : "Save profile"}
        </button>
      </form>
    </section>
  );
}

function TextField({
  placeholder,
  value,
  onChange,
}: {
  placeholder: string;
  value: string;
  onChange: (v: string) => void;
}) {
  return (
    <input
      type="text"
      placeholder={placeholder}
      value={value}
      onChange={(e) => onChange(e.target.value)}
      className="w-full px-3.5 py-2.5 rounded-lg border border-border bg-background text-foreground text-sm placeholder:text-muted focus:outline-none focus:border-brand focus:ring-2 focus:ring-brand/20 transition-all"
    />
  );
}

function ActiveSessions() {
  const [keys, setKeys] = useState<ApiKeyInfo[] | null>(null);
  const [error, setError] = useState("");
  const [revoking, setRevoking] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const data = await listMyKeys();
      setKeys(data);
      setError("");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not load sessions");
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  async function handleRevoke(keyId: string) {
    if (!confirm("Revoke this session? Any CLI or browser using it will be signed out.")) return;
    setRevoking(keyId);
    try {
      await revokeMyKey(keyId);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not revoke");
    } finally {
      setRevoking(null);
    }
  }

  return (
    <section className="rounded-2xl border border-border bg-surface p-6 space-y-4">
      <div className="flex items-baseline justify-between">
        <div>
          <h2 className="text-base font-semibold text-foreground">Active sessions</h2>
          <p className="text-xs text-muted mt-0.5">
            Each browser tab and CLI install holds its own API key. Revoke anything you don&apos;t recognize.
          </p>
        </div>
        <button
          onClick={load}
          className="text-xs text-muted hover:text-foreground"
          type="button"
        >
          Refresh
        </button>
      </div>
      {error && <p className="text-xs text-error">{error}</p>}
      {keys === null ? (
        <p className="text-sm text-muted">Loading…</p>
      ) : keys.length === 0 ? (
        <p className="text-sm text-muted">No active sessions.</p>
      ) : (
        <ul className="divide-y divide-border rounded-lg border border-border overflow-hidden">
          {keys.map((k) => (
            <li key={k.id} className="flex items-center gap-3 p-3">
              <div className="flex-1 min-w-0">
                <div className="text-sm text-foreground truncate">{k.name || "(unnamed)"}</div>
                <div className="text-[11px] text-muted font-mono">
                  created {formatDate(k.created_at)}
                  {k.last_used_at ? ` · last used ${formatRelative(k.last_used_at)}` : " · never used"}
                </div>
              </div>
              <button
                onClick={() => handleRevoke(k.id)}
                disabled={revoking === k.id}
                className="text-xs px-3 py-1.5 rounded-md border border-border hover:border-error hover:text-error disabled:opacity-60 transition-colors"
                type="button"
              >
                {revoking === k.id ? "Revoking…" : "Revoke"}
              </button>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function ChangePassword() {
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [msg, setMsg] = useState<{ kind: "ok" | "err"; text: string } | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setMsg(null);
    if (next !== confirm) {
      setMsg({ kind: "err", text: "New passwords don't match." });
      return;
    }
    if (next.length < 8) {
      setMsg({ kind: "err", text: "New password must be at least 8 characters." });
      return;
    }
    setSubmitting(true);
    try {
      await updateMe({ password: next, current_password: current });
      setCurrent("");
      setNext("");
      setConfirm("");
      setMsg({
        kind: "ok",
        text: "Password changed. All other sessions have been signed out.",
      });
    } catch (e) {
      const text = e instanceof ApiError ? e.message : "Could not change password";
      setMsg({ kind: "err", text });
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <section className="rounded-2xl border border-border bg-surface p-6 space-y-4">
      <div>
        <h2 className="text-base font-semibold text-foreground">Change password</h2>
        <p className="text-xs text-muted mt-0.5">
          Changing your password signs out every other browser and CLI.
        </p>
      </div>
      <form onSubmit={handleSubmit} className="space-y-3">
        <PasswordField placeholder="Current password" value={current} onChange={setCurrent} autoComplete="current-password" />
        <PasswordField placeholder="New password" value={next} onChange={setNext} autoComplete="new-password" />
        <PasswordField placeholder="Confirm new password" value={confirm} onChange={setConfirm} autoComplete="new-password" />
        {msg && (
          <p className={`text-xs ${msg.kind === "ok" ? "text-green-500" : "text-error"}`}>
            {msg.text}
          </p>
        )}
        <button
          type="submit"
          disabled={submitting || !current || !next || !confirm}
          className="bg-brand hover:bg-brand-hover disabled:opacity-60 text-white text-sm font-semibold px-4 py-2 rounded-lg transition-colors"
        >
          {submitting ? "Saving…" : "Change password"}
        </button>
      </form>
    </section>
  );
}

function PasswordField({
  placeholder,
  value,
  onChange,
  autoComplete,
}: {
  placeholder: string;
  value: string;
  onChange: (v: string) => void;
  autoComplete: string;
}) {
  return (
    <input
      type="password"
      placeholder={placeholder}
      value={value}
      onChange={(e) => onChange(e.target.value)}
      autoComplete={autoComplete}
      className="w-full px-3.5 py-2.5 rounded-lg border border-border bg-background text-foreground text-sm placeholder:text-muted focus:outline-none focus:border-brand focus:ring-2 focus:ring-brand/20 transition-all"
    />
  );
}

function formatDate(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}

function formatRelative(iso: string): string {
  const diffMs = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diffMs / 60_000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  if (days < 30) return `${days}d ago`;
  return formatDate(iso);
}
