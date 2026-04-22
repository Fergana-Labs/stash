"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import AppShell from "../components/AppShell";
import { useAuth } from "../hooks/useAuth";
import {
  listAllNotebooks,
  listMyWorkspaces,
  listPublicWorkspaces,
  createWorkspace,
  joinWorkspace,
} from "../lib/api";
import {
  NotebookWithWorkspace,
  Workspace,
} from "../lib/types";

const GITHUB_URL = "https://github.com/Fergana-Labs/stash";

function GithubIcon({ size = 16 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="currentColor" aria-hidden>
      <path d="M12 .5C5.65.5.5 5.65.5 12a11.5 11.5 0 0 0 7.86 10.92c.57.11.78-.25.78-.55v-1.94c-3.2.7-3.87-1.54-3.87-1.54-.52-1.33-1.28-1.69-1.28-1.69-1.04-.71.08-.7.08-.7 1.16.08 1.77 1.19 1.77 1.19 1.03 1.77 2.7 1.26 3.36.96.1-.75.4-1.26.73-1.55-2.55-.29-5.24-1.28-5.24-5.68 0-1.26.45-2.29 1.19-3.1-.12-.29-.52-1.47.11-3.07 0 0 .97-.31 3.18 1.18a11 11 0 0 1 5.79 0c2.21-1.49 3.18-1.18 3.18-1.18.63 1.6.23 2.78.12 3.07.74.81 1.19 1.84 1.19 3.1 0 4.41-2.69 5.38-5.26 5.67.41.35.77 1.05.77 2.12v3.14c0 .3.21.67.79.55A11.5 11.5 0 0 0 23.5 12C23.5 5.65 18.35.5 12 .5Z" />
    </svg>
  );
}

type StepVizLine = { r: "agent" | "human"; t: string; a: string; l: string; highlight?: boolean };

function StreamViz() {
  const lines: StepVizLine[] = [
    { r: "agent", t: "14:02", a: "tool_call", l: "read_file(auth.py)" },
    { r: "agent", t: "14:02", a: "edit", l: "session_refresh.py" },
    { r: "human", t: "14:03", a: "review", l: "pr/#482" },
    { r: "agent", t: "14:04", a: "test", l: "pytest auth/", highlight: true },
  ];
  return (
    <div className="flex flex-col gap-1.5 font-mono text-[11px]">
      {lines.map((x, i) => (
        <div
          key={i}
          className={"flex items-center gap-2 " + (x.highlight ? "text-foreground" : "text-dim")}
        >
          <span className="text-[10px] text-muted">{x.t}</span>
          <span
            className="h-[6px] w-[6px] shrink-0 rounded-full"
            style={{ background: x.r === "agent" ? "var(--color-agent)" : "var(--color-human)" }}
          />
          <span className="text-foreground">{x.a}</span>
          <span>{x.l}</span>
        </div>
      ))}
    </div>
  );
}

function CurateViz() {
  return (
    <div className="flex flex-col gap-1.5">
      <div className="flex items-center justify-between rounded-md border border-border bg-background px-2 py-1.5 text-[11.5px] text-foreground">
        auth-patterns
        <span className="rounded bg-brand/15 px-1.5 py-px font-mono text-[9.5px] uppercase tracking-[0.08em] text-brand">
          root
        </span>
      </div>
      <div className="relative ml-4 flex items-center rounded-md border border-border bg-background px-2 py-1.5 text-[11.5px] text-foreground before:absolute before:left-[-10px] before:top-1/2 before:h-px before:w-2 before:bg-border">
        session-refresh 401 race
      </div>
      <div className="relative ml-4 flex items-center rounded-md border border-border bg-background px-2 py-1.5 text-[11.5px] text-foreground before:absolute before:left-[-10px] before:top-1/2 before:h-px before:w-2 before:bg-border">
        rate-limits · 500/min
      </div>
      <div className="flex items-center justify-between rounded-md border border-border bg-background px-2 py-1.5 text-[11.5px] text-foreground">
        memory-leak-v2
        <span className="rounded bg-brand/15 px-1.5 py-px font-mono text-[9.5px] uppercase tracking-[0.08em] text-brand">
          new
        </span>
      </div>
    </div>
  );
}

function SearchViz() {
  const sources: [string, string][] = [
    ["history/rex:14:02", "62%"],
    ["notebooks/auth-patterns", "21%"],
    ["files/gateway.py", "11%"],
  ];
  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center gap-2 rounded-md border border-border bg-background px-2.5 py-1.5 text-[11.5px] text-foreground">
        <span className="font-mono text-[11px] text-brand">/stash</span>
        why was the rate-limit raised?
      </div>
      <div className="flex flex-col gap-1 font-mono text-[10.5px] text-dim">
        {sources.map(([p, pct]) => (
          <div key={p} className="flex justify-between">
            <span className="text-foreground">{p}</span>
            <span className="text-brand">{pct}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function LandingPage() {
  const steps = [
    {
      n: "01",
      pill: "Stream",
      title: "Every session flows into a shared store.",
      body: "Prompts, tool calls, and session summaries push to your workspace’s history as they happen. Nothing to remember to save.",
      viz: <StreamViz />,
    },
    {
      n: "02",
      pill: "Curate",
      title: "A curation agent turns noise into a wiki.",
      body: "On SessionEnd, stash:sleep reads recent history and organizes it into notebooks with [[backlinks]] and a page graph.",
      viz: <CurateViz />,
    },
    {
      n: "03",
      pill: "Search",
      title: "Every agent queries the whole team's work.",
      body: "stash search runs a cross-resource agentic loop over files, history, notebooks, tables, and chats. Answers with sources.",
      viz: <SearchViz />,
    },
  ];

  return (
    <div className="min-h-screen flex flex-col bg-background text-foreground">
      <header className="border-b border-border-subtle bg-background">
        <div className="mx-auto flex h-14 max-w-[1100px] items-center justify-between px-6">
          <span className="font-display text-[20px] font-black tracking-[-0.03em] text-foreground">
            stash
          </span>
          <nav className="flex items-center gap-1 text-sm text-dim">
            <Link href="/docs" className="rounded-md px-3 py-2 transition hover:bg-raised hover:text-foreground">
              Docs
            </Link>
            <a
              href={GITHUB_URL}
              className="inline-flex items-center gap-1.5 rounded-md px-3 py-2 transition hover:bg-raised hover:text-foreground"
              target="_blank"
              rel="noreferrer"
            >
              <GithubIcon />
              <span className="hidden sm:inline">GitHub</span>
            </a>
            <Link
              href="/login"
              className="ml-1 inline-flex h-9 items-center rounded-lg bg-brand px-4 text-sm font-medium text-white transition hover:bg-brand-hover"
            >
              Sign in
            </Link>
          </nav>
        </div>
      </header>

      <section className="mx-auto w-full max-w-[1100px] px-6 pt-20 pb-16 text-center">
        <h1 className="font-display text-[clamp(40px,6vw,68px)] font-black leading-[0.98] tracking-[-0.045em] text-foreground">
          <span className="text-brand">Agent memory</span>
          <br />
          for your repos.
        </h1>
        <p className="mx-auto mt-6 max-w-[560px] text-[17px] leading-[1.55] text-dim">
          Stash is the hive mind for your team&apos;s coding agents. Every
          session, decision, and search flows into one shared brain, so the
          next agent that touches your repo already knows what yours learned.
        </p>
        <div className="mt-8 flex flex-wrap justify-center gap-3">
          <Link
            href="/login"
            className="inline-flex h-10 items-center rounded-lg bg-brand px-5 text-sm font-medium text-white transition hover:bg-brand-hover"
          >
            Sign in
          </Link>
          <Link
            href="/docs"
            className="inline-flex h-10 items-center rounded-lg border border-border bg-background px-5 text-sm font-medium text-foreground transition hover:border-foreground/40"
          >
            Read the docs
          </Link>
          <a
            href={GITHUB_URL}
            target="_blank"
            rel="noreferrer"
            className="inline-flex h-10 items-center gap-2 rounded-lg border border-border bg-background px-5 text-sm font-medium text-foreground transition hover:border-foreground/40"
          >
            <GithubIcon />
            GitHub
          </a>
        </div>
      </section>

      <section className="border-t border-border-subtle bg-surface py-20">
        <div className="mx-auto w-full max-w-[1100px] px-6">
          <p className="flex items-center font-mono text-[11px] font-medium uppercase tracking-[0.14em] text-muted">
            <span className="mr-[10px] inline-block h-[6px] w-[6px] rounded-full bg-brand" />
            How it works
          </p>
          <h2 className="mt-3 font-display text-[clamp(28px,3.6vw,44px)] font-bold leading-[1.05] tracking-[-0.03em] text-foreground">
            Stream. Curate. Search.
            <br />
            <span className="font-medium text-dim">Nobody starts from zero.</span>
          </h2>
          <div className="mt-12 grid grid-cols-1 gap-4 lg:grid-cols-3">
            {steps.map((s) => (
              <div
                key={s.n}
                className="flex min-h-[340px] flex-col rounded-[14px] border border-border bg-background p-5 transition-colors hover:border-brand"
              >
                <div className="mb-4 flex items-center justify-between">
                  <span className="font-mono text-[11px] tracking-[0.14em] text-muted">
                    {s.n}
                  </span>
                  <span className="rounded bg-brand/15 px-2 py-0.5 font-mono text-[10px] font-medium uppercase tracking-[0.1em] text-brand">
                    {s.pill}
                  </span>
                </div>
                <div className="mb-5 min-h-[140px] shrink-0 rounded-[10px] border border-border-subtle bg-raised p-3.5">
                  {s.viz}
                </div>
                <h3 className="font-display text-[18px] font-bold tracking-[-0.015em] text-foreground">
                  {s.title}
                </h3>
                <p className="mt-2 text-[14px] leading-[1.6] text-dim">{s.body}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      <footer className="border-t border-border-subtle">
        <div className="mx-auto flex max-w-[1100px] flex-wrap items-center justify-between gap-3 px-6 py-5 font-mono text-[11px] uppercase tracking-[0.12em] text-muted">
          <span>MIT licensed · Self-hostable</span>
          <a href={GITHUB_URL} target="_blank" rel="noreferrer" className="hover:text-foreground">
            github.com/Fergana-Labs/stash
          </a>
        </div>
      </footer>
    </div>
  );
}

function LoggedInHome({ user, logout }: { user: NonNullable<ReturnType<typeof useAuth>["user"]>; logout: () => void }) {
  const router = useRouter();
  const [myWorkspaces, setMyWorkspaces] = useState<Workspace[]>([]);
  const [publicWorkspaces, setPublicWorkspaces] = useState<Workspace[]>([]);
  const [notebooks, setNotebooks] = useState<NotebookWithWorkspace[]>([]);
  const [loading, setLoading] = useState(true);

  // Create / join state
  const [showCreate, setShowCreate] = useState(false);
  const [newName, setNewName] = useState("");
  const [newDesc, setNewDesc] = useState("");
  const [isPublic, setIsPublic] = useState(false);
  const [joinCode, setJoinCode] = useState("");
  const [error, setError] = useState("");

  const myWsIds = useMemo(() => new Set(myWorkspaces.map((w) => w.id)), [myWorkspaces]);

  const loadData = useCallback(() => {
    setLoading(true);
    Promise.all([
      listMyWorkspaces().then((r) => r?.workspaces ?? []).catch(() => [] as Workspace[]),
      listPublicWorkspaces().then((r) => r?.workspaces ?? []).catch(() => [] as Workspace[]),
      listAllNotebooks().then((r) => r?.notebooks ?? []).catch(() => [] as NotebookWithWorkspace[]),
    ]).then(([mine, pub, nbs]) => {
      setMyWorkspaces(mine);
      setPublicWorkspaces(pub);
      setNotebooks(nbs);
      setLoading(false);
    });
  }, []);

  useEffect(() => { loadData(); }, [loadData]);

  const handleCreate = async () => {
    if (!newName.trim()) return;
    setError("");
    try {
      const ws = await createWorkspace(newName.trim(), newDesc.trim(), isPublic);
      setShowCreate(false);
      setNewName("");
      setNewDesc("");
      router.push(`/workspaces/${ws.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create workspace");
    }
  };

  const handleJoin = async () => {
    if (!joinCode.trim()) return;
    setError("");
    try {
      const ws = await joinWorkspace(joinCode.trim());
      router.push(`/workspaces/${ws.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to join workspace");
    }
  };

  const otherPublic = publicWorkspaces.filter((w) => !myWsIds.has(w.id));

  return (
    <AppShell user={user} onLogout={logout}>
      <div className="max-w-4xl mx-auto w-full px-4 py-8">
        <div className="flex items-center justify-between mb-6">
          <h1 className="text-2xl font-bold text-foreground font-display">Workspaces</h1>
          <button onClick={() => setShowCreate(true)} className="text-sm bg-brand hover:bg-brand-hover text-foreground px-3 py-1.5 rounded">
            Create Workspace
          </button>
        </div>

        {error && <p className="text-red-400 text-sm mb-4">{error}<button onClick={() => setError("")} className="ml-2 text-red-500">&times;</button></p>}

        {/* Create workspace form */}
        {showCreate && (
          <div className="bg-surface border border-border rounded-lg p-4 mb-6">
            <h3 className="text-foreground font-medium mb-3">New Workspace</h3>
            <input value={newName} onChange={(e) => setNewName(e.target.value)} placeholder="Name" className="w-full bg-raised border border-border rounded px-3 py-2 text-foreground text-sm mb-2" />
            <input value={newDesc} onChange={(e) => setNewDesc(e.target.value)} placeholder="Description (optional)" className="w-full bg-raised border border-border rounded px-3 py-2 text-foreground text-sm mb-2" />
            <label className="flex items-center gap-2 text-sm text-dim mb-3"><input type="checkbox" checked={isPublic} onChange={(e) => setIsPublic(e.target.checked)} /> Public</label>
            <div className="flex gap-2">
              <button onClick={handleCreate} className="bg-brand hover:bg-brand-hover text-foreground px-4 py-1.5 rounded text-sm">Create</button>
              <button onClick={() => setShowCreate(false)} className="bg-raised text-dim px-4 py-1.5 rounded text-sm">Cancel</button>
            </div>
          </div>
        )}

        {/* Join by invite code */}
        <div className="bg-surface border border-border rounded-lg p-4 mb-6">
          <h3 className="text-foreground font-medium mb-2">Join by Invite Code</h3>
          <div className="flex gap-2">
            <input value={joinCode} onChange={(e) => setJoinCode(e.target.value)} placeholder="Enter invite code" className="flex-1 bg-raised border border-border rounded px-3 py-2 text-foreground text-sm" />
            <button onClick={handleJoin} className="bg-success hover:bg-success/80 text-foreground px-4 py-1.5 rounded text-sm">Join</button>
          </div>
        </div>

        {loading ? (
          <p className="text-muted text-sm">Loading...</p>
        ) : (
          <>
            {/* My Workspaces */}
            {myWorkspaces.length > 0 && (
              <section className="mb-8">
                <h2 className="text-sm font-medium text-muted uppercase tracking-wider mb-3">My Workspaces</h2>
                <div className="grid gap-3 sm:grid-cols-2">
                  {myWorkspaces.map((ws) => (
                    <Link key={ws.id} href={`/workspaces/${ws.id}`} className="bg-surface border border-border rounded-lg p-4 hover:border-brand transition-colors">
                      <div className="text-foreground font-medium">{ws.name}</div>
                      {ws.description && <div className="text-dim text-sm mt-1">{ws.description}</div>}
                      <div className="text-[10px] text-muted mt-1">{ws.member_count ?? 0} members</div>
                    </Link>
                  ))}
                </div>
              </section>
            )}

            {/* Public Workspaces */}
            {otherPublic.length > 0 && (
              <section className="mb-8">
                <h2 className="text-sm font-medium text-muted uppercase tracking-wider mb-3">Public Workspaces</h2>
                <div className="grid gap-3 sm:grid-cols-2">
                  {otherPublic.map((ws) => (
                    <Link key={ws.id} href={`/workspaces/${ws.id}`} className="bg-surface border border-border rounded-lg p-4 hover:border-brand transition-colors">
                      <div className="text-foreground font-medium">{ws.name}</div>
                      {ws.description && <div className="text-dim text-sm mt-1">{ws.description}</div>}
                      <div className="text-[10px] text-muted mt-1">Public</div>
                    </Link>
                  ))}
                </div>
              </section>
            )}

            {/* Recent Notebooks */}
            {notebooks.length > 0 && (
              <section>
                <h2 className="text-sm font-medium text-muted uppercase tracking-wider mb-3">Recent Notebooks</h2>
                <div className="space-y-0.5">
                  {notebooks.slice(0, 10).map((nb) => (
                    <Link key={nb.id} href="/notebooks" className="flex items-center gap-3 px-3 py-2.5 rounded-lg hover:bg-raised transition-colors">
                      <div className="w-8 h-8 rounded-md bg-green-500/15 text-green-500 flex items-center justify-center text-xs font-bold flex-shrink-0">N</div>
                      <div className="min-w-0 flex-1">
                        <div className="text-sm text-foreground truncate">{nb.name}</div>
                        <div className="text-xs text-muted truncate">{nb.workspace_name || "Personal"}</div>
                      </div>
                      <span className="text-xs text-muted flex-shrink-0">{formatRelativeTime(nb.updated_at)}</span>
                    </Link>
                  ))}
                </div>
              </section>
            )}

            {myWorkspaces.length === 0 && notebooks.length === 0 && (
              <div className="text-center py-12">
                <p className="text-dim mb-4">Nothing here yet. Create a workspace to get started.</p>
              </div>
            )}
          </>
        )}
      </div>
    </AppShell>
  );
}

function formatRelativeTime(dateStr: string): string {
  const now = Date.now();
  const then = new Date(dateStr).getTime();
  const diffMs = now - then;
  const diffMin = Math.floor(diffMs / 60000);
  if (diffMin < 1) return "just now";
  if (diffMin < 60) return `${diffMin}m ago`;
  const diffHr = Math.floor(diffMin / 60);
  if (diffHr < 24) return `${diffHr}h ago`;
  const diffDay = Math.floor(diffHr / 24);
  if (diffDay < 30) return `${diffDay}d ago`;
  return new Date(dateStr).toLocaleDateString();
}

export default function Home() {
  const { user, loading, logout } = useAuth();

  if (loading) {
    return <div className="min-h-screen flex items-center justify-center text-muted">Loading...</div>;
  }

  return user ? <LoggedInHome user={user} logout={logout} /> : <LandingPage />;
}
