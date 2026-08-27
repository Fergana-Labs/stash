"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import WorkspaceShell from "@/components/workspace/workspace-shell";
import SubscriptionSection from "../../components/settings/SubscriptionSection";
import ExportSection from "../../components/settings/ExportSection";
import { AccountSettingsSkeleton } from "../../components/SkeletonStates";
import { useAuth } from "../../hooks/useAuth";
import { ApiError, updateMe } from "../../lib/api";
import { User } from "../../lib/types";

const AUTH0_ENABLED = process.env.NEXT_PUBLIC_AUTH0_ENABLED === "true";

type SettingsTab = "account" | "subscription" | "data";

const SETTINGS_TABS: Array<{
  id: SettingsTab;
  label: string;
  description: string;
}> = [
  {
    id: "account",
    label: "Account",
    description: "Your profile and sign-in settings.",
  },
  {
    id: "subscription",
    label: "Subscription",
    description: "View your plan and manage billing.",
  },
  {
    id: "data",
    label: "Data export",
    description: "Download a copy of everything in your Stash.",
  },
];

export default function SettingsPage() {
  const router = useRouter();
  const { user, loading, logout, refresh } = useAuth();
  const [activeTab, setActiveTab] = useState<SettingsTab>("account");

  useEffect(() => {
    if (!loading && !user) router.replace("/login");
  }, [loading, user, router]);

  if (loading || !user) {
    return <AccountSettingsSkeleton />;
  }

  return (
    <WorkspaceShell user={user} onLogout={logout}>
      <main className="flex-1 px-4 py-7">
        <div className="mx-auto w-full max-w-5xl">
          <button
            type="button"
            onClick={() => router.push("/")}
            className="cursor-pointer text-sm text-muted-foreground hover:text-foreground inline-flex items-center gap-1.5"
          >
            <span aria-hidden>←</span> Home
          </button>
          <div className="mt-7 grid gap-7 md:grid-cols-[180px_minmax(0,1fr)]">
            <aside>
              <h1 className="text-xl font-semibold text-foreground">
                Settings
              </h1>
              <nav
                aria-label="Settings sections"
                className="mt-4 flex gap-1 overflow-x-auto md:flex-col"
              >
                {SETTINGS_TABS.map((tab) => (
                  <button
                    key={tab.id}
                    type="button"
                    onClick={() => setActiveTab(tab.id)}
                    aria-current={activeTab === tab.id ? "page" : undefined}
                    className={`cursor-pointer whitespace-nowrap rounded-md px-3 py-2 text-left text-[13px] font-medium transition-colors ${
                      activeTab === tab.id
                        ? "bg-raised text-foreground"
                        : "text-muted-foreground hover:bg-raised/60 hover:text-foreground"
                    }`}
                  >
                    {tab.label}
                  </button>
                ))}
              </nav>
            </aside>

            <div className="min-w-0">
              <header className="mb-5">
                <h2 className="text-2xl font-semibold text-foreground">
                  {SETTINGS_TABS.find((tab) => tab.id === activeTab)?.label}
                </h2>
                <p className="mt-1 text-sm text-muted-foreground">
                  {
                    SETTINGS_TABS.find((tab) => tab.id === activeTab)
                      ?.description
                  }
                </p>
              </header>

              <div className="space-y-4">
                {activeTab === "account" && (
                  <>
                    <Profile user={user} onUpdated={refresh} />
                    {!AUTH0_ENABLED && <ChangePassword />}
                  </>
                )}
                {activeTab === "subscription" && <SubscriptionSection />}
                {activeTab === "data" && <ExportSection />}
              </div>
            </div>
          </div>
        </div>
      </main>
    </WorkspaceShell>
  );
}

function Profile({ user, onUpdated }: { user: User; onUpdated: () => void }) {
  const [displayName, setDisplayName] = useState(user.display_name);
  const [description, setDescription] = useState(user.description || "");
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState<{ kind: "ok" | "err"; text: string } | null>(
    null,
  );

  useEffect(() => {
    setDisplayName(user.display_name);
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
    <section className="overflow-hidden rounded-lg border border-border bg-surface">
      <div className="border-b border-border px-5 py-4">
        <h2 className="text-base font-semibold text-foreground">Profile</h2>
        <p className="text-xs text-muted-foreground mt-0.5">
          Signed in as <span className="font-mono">{user.name}</span>.
        </p>
      </div>
      <form onSubmit={handleSubmit} className="divide-y divide-border">
        <TextField
          label="Display name"
          placeholder="Display name"
          value={displayName}
          onChange={setDisplayName}
        />
        <TextField
          label="About"
          placeholder="Description"
          value={description}
          onChange={setDescription}
        />
        <div className="flex min-h-14 items-center justify-between gap-3 px-5 py-3">
          {msg ? (
            <p
              className={`text-xs ${msg.kind === "ok" ? "text-green-500" : "text-error"}`}
            >
              {msg.text}
            </p>
          ) : (
            <span />
          )}
          <button
            type="submit"
            disabled={saving}
            className="cursor-pointer rounded-md border border-border bg-background px-3 py-1.5 text-[13px] font-medium text-foreground transition-colors hover:bg-raised disabled:opacity-60"
          >
            {saving ? "Saving…" : "Save"}
          </button>
        </div>
      </form>
    </section>
  );
}

function TextField({
  label,
  placeholder,
  value,
  onChange,
}: {
  label: string;
  placeholder: string;
  value: string;
  onChange: (v: string) => void;
}) {
  return (
    <label className="flex flex-col gap-2 px-5 py-3.5 sm:flex-row sm:items-center sm:justify-between sm:gap-6">
      <span className="text-[13px] font-medium text-foreground">{label}</span>
      <input
        type="text"
        placeholder={placeholder}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground transition-colors focus:border-brand focus:outline-none sm:max-w-sm"
      />
    </label>
  );
}

function ChangePassword() {
  const [open, setOpen] = useState(false);
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [msg, setMsg] = useState<{ kind: "ok" | "err"; text: string } | null>(
    null,
  );

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setMsg(null);
    if (next !== confirm) {
      setMsg({ kind: "err", text: "New passwords don't match." });
      return;
    }
    if (next.length < 8) {
      setMsg({
        kind: "err",
        text: "New password must be at least 8 characters.",
      });
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
      setOpen(false);
    } catch (e) {
      const text =
        e instanceof ApiError ? e.message : "Could not change password";
      setMsg({ kind: "err", text });
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <section className="overflow-hidden rounded-lg border border-border bg-surface">
      <div className="flex items-center justify-between gap-4 px-5 py-4">
        <div>
          <h2 className="text-[13px] font-medium text-foreground">Password</h2>
          <p className="mt-0.5 text-xs text-muted-foreground">
            Changing it signs out every other browser and CLI.
          </p>
        </div>
        <button
          type="button"
          onClick={() => setOpen((value) => !value)}
          className="cursor-pointer rounded-md border border-border px-3 py-1.5 text-[13px] font-medium text-foreground hover:bg-raised"
        >
          {open ? "Cancel" : "Change password"}
        </button>
      </div>
      {open && (
        <form
          onSubmit={handleSubmit}
          className="space-y-2 border-t border-border px-5 py-4"
        >
          <PasswordField
            placeholder="Current password"
            value={current}
            onChange={setCurrent}
            autoComplete="current-password"
          />
          <PasswordField
            placeholder="New password"
            value={next}
            onChange={setNext}
            autoComplete="new-password"
          />
          <PasswordField
            placeholder="Confirm new password"
            value={confirm}
            onChange={setConfirm}
            autoComplete="new-password"
          />
          <div className="flex items-center justify-between gap-3 pt-1">
            {msg ? (
              <p
                className={`text-xs ${msg.kind === "ok" ? "text-green-500" : "text-error"}`}
              >
                {msg.text}
              </p>
            ) : (
              <span />
            )}
            <button
              type="submit"
              disabled={submitting || !current || !next || !confirm}
              className="cursor-pointer rounded-md border border-border bg-background px-3 py-1.5 text-[13px] font-medium text-foreground transition-colors hover:bg-raised disabled:opacity-60"
            >
              {submitting ? "Saving…" : "Save password"}
            </button>
          </div>
        </form>
      )}
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
      className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground transition-colors focus:border-brand focus:outline-none"
    />
  );
}
