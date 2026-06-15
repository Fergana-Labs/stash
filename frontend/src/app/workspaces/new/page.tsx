"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import AppShell from "../../../components/AppShell";
import { BasicPageSkeleton } from "../../../components/SkeletonStates";
import { useAuth } from "../../../hooks/useAuth";
import { track } from "../../../lib/analytics";
import { createWorkspace } from "../../../lib/api";
import { resetSkillNavigationCache } from "../../../lib/skillNavigationCache";

export default function NewWorkspacePage() {
  const router = useRouter();
  const { user, loading, logout } = useAuth();
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  if (loading) return <BasicPageSkeleton />;
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
      const ws = await createWorkspace(name.trim(), description.trim());
      track("web.workspace_created", { workspace_id: ws.id });
      resetSkillNavigationCache();
      router.push(`/workspaces/${ws.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create workspace");
      setBusy(false);
    }
  }

  return (
    <AppShell user={user} onLogout={logout}>
      <div className="mx-auto max-w-2xl px-8 py-12">
        <div className="text-[11px] uppercase tracking-wider text-brand">New workspace</div>
        <h1 className="mt-2 font-display text-[34px] font-bold tracking-tight text-foreground">
          Create a workspace
        </h1>
        <p className="mt-3 text-[15px] leading-relaxed text-foreground/80">
          A Skill Workspace is your team&apos;s shared home for agent work: sessions,
          Files, folders, and the Skills you publish from them.
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
              placeholder="What is this workspace for?"
              className="resize-none rounded-lg border border-border bg-base px-3 py-2 text-[14px] text-foreground placeholder:text-muted focus:border-brand focus:outline-none"
            />
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
              className="cursor-pointer text-[13px] text-muted hover:text-foreground"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={busy || !name.trim()}
              className="cursor-pointer rounded-md bg-brand px-4 py-2 text-[13px] font-medium text-white hover:bg-[var(--color-brand-hover)] disabled:opacity-40"
            >
              {busy ? "Creating…" : "Create workspace"}
            </button>
          </div>
        </form>

        <div className="mt-12 rounded-2xl border border-border-subtle bg-surface p-5">
          <div className="text-[11px] uppercase tracking-wider text-muted">
            What this workspace can collect
          </div>
          <ul className="mt-3 flex flex-col gap-2 text-[13px] text-dim">
            <li>
              📜 <strong className="text-foreground">Skills</strong> —{" "}
              <code className="rounded bg-raised px-1 py-0.5 text-[12px]">stash skills add</code>{" "}
              uploads a local Claude Code skill folder.
            </li>
            <li>
              ▤ <strong className="text-foreground">Sessions</strong> — agent transcripts pushed
              from your CLI / MCP integration.
            </li>
            <li>
              ▦ <strong className="text-foreground">Files</strong> — drop PDFs, slides, sheets;
              text gets extracted and indexed for the Ask agent.
            </li>
          </ul>
        </div>
      </div>
    </AppShell>
  );
}
