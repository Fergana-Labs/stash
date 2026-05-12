"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import AppShell from "../../../components/AppShell";
import { useAuth } from "../../../hooks/useAuth";
import { createWorkspace } from "../../../lib/api";

export default function NewStashPage() {
  const router = useRouter();
  const { user, loading, logout } = useAuth();
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [isPublic, setIsPublic] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  if (loading) return <div className="flex h-screen items-center justify-center text-muted">Loading…</div>;
  if (!user) {
    if (typeof window !== "undefined") router.push("/login");
    return null;
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!name.trim()) return;
    setBusy(true);
    setError("");
    try {
      const ws = await createWorkspace(name.trim(), description.trim(), isPublic);
      router.push(`/stashes/${ws.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create stash");
      setBusy(false);
    }
  }

  return (
    <AppShell user={user} onLogout={logout}>
      <div className="mx-auto max-w-2xl px-8 py-12">
        <div className="text-[11px] uppercase tracking-wider text-brand">New stash</div>
        <h1 className="mt-2 font-display text-[34px] font-bold tracking-tight text-foreground">
          Create a stash
        </h1>
        <p className="mt-3 text-[14px] text-dim">
          Every stash has two main spaces —{" "}
          <strong className="text-foreground">Sessions</strong> for agent transcripts,{" "}
          and <strong className="text-foreground">Wiki</strong> for pages, files, folders, and
          skills.
        </p>

        <form onSubmit={submit} className="mt-8 flex flex-col gap-4">
          <label className="flex flex-col gap-1.5">
            <span className="text-[12px] font-medium text-foreground">Name</span>
            <input
              autoFocus
              value={name}
              onChange={(e) => setName(e.target.value)}
              required
              placeholder="e.g. Q3 Investor Diligence"
              className="rounded-lg border border-border bg-base px-3 py-2 text-[14px] text-foreground placeholder:text-muted focus:border-brand focus:outline-none"
            />
          </label>
          <label className="flex flex-col gap-1.5">
            <span className="text-[12px] font-medium text-foreground">Description</span>
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={3}
              placeholder="What is this stash for?"
              className="resize-none rounded-lg border border-border bg-base px-3 py-2 text-[14px] text-foreground placeholder:text-muted focus:border-brand focus:outline-none"
            />
          </label>
          <label className="flex items-center gap-2 text-[13px] text-foreground">
            <input
              type="checkbox"
              checked={isPublic}
              onChange={(e) => setIsPublic(e.target.checked)}
              className="accent-[var(--color-brand)]"
            />
            Make discoverable in the public catalog
          </label>

          {error && (
            <div className="rounded-lg border border-red-300/40 bg-red-500/10 px-3 py-2 text-[13px] text-red-400">
              {error}
            </div>
          )}

          <div className="mt-4 flex items-center justify-between">
            <button
              type="button"
              onClick={() => router.back()}
              className="text-[13px] text-muted hover:text-foreground"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={busy || !name.trim()}
              className="rounded-md bg-brand px-4 py-2 text-[13px] font-medium text-white hover:bg-[var(--color-brand-hover)] disabled:opacity-40"
            >
              {busy ? "Creating…" : "Create stash"}
            </button>
          </div>
        </form>

        <div className="mt-12 rounded-2xl border border-border-subtle bg-surface p-5">
          <div className="text-[11px] uppercase tracking-wider text-muted">
            What you can drop in next
          </div>
          <ul className="mt-3 flex flex-col gap-2 text-[13px] text-dim">
            <li>
              ▤ <strong className="text-foreground">Sessions</strong> — agent transcripts pushed
              from your CLI / MCP integration.
            </li>
            <li>
              ▦ <strong className="text-foreground">Wiki</strong> — pages, PDFs, slides, sheets,
              and skill folders; text gets indexed for the Ask agent.
            </li>
          </ul>
        </div>
      </div>
    </AppShell>
  );
}
