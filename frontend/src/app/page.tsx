"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import AppShell from "../components/AppShell";
import Header from "../components/Header";
import { useAuth } from "../hooks/useAuth";
import { useRouter } from "next/navigation";
import {
  listAllNotebooks,
  listMyWorkspaces,
  listPublicWorkspaces,
  getActivityTimeline,
  getKnowledgeDensity,
  getEmbeddingProjection,
} from "../lib/api";
import {
  ActivityTimeline,
  EmbeddingProjection,
  KnowledgeDensity,
  NotebookWithWorkspace,
  Workspace,
} from "../lib/types";
import DashboardSection from "../components/viz/DashboardSection";
import AgentActivityTimeline from "../components/viz/AgentActivityTimeline";
import KnowledgeDensityMap from "../components/viz/KnowledgeDensityMap";
import EmbeddingSpaceExplorer from "../components/viz/EmbeddingSpaceExplorer";

interface FeedItem {
  id: string;
  type: "workspace" | "notebook" | "memory";
  name: string;
  description?: string;
  href: string;
  updatedAt: string;
  icon: string;
  badge?: string;
  badgeColor?: string;
}

function EventLine({ time, agent, agentColor, action, detail }: { time: string; agent: string; agentColor: string; action: string; detail: string }) {
  return (
    <div className="flex items-start gap-3 py-1.5">
      <span className="text-[11px] text-muted font-mono w-12 flex-shrink-0 pt-0.5">{time}</span>
      <span className={`text-[10px] font-mono font-bold uppercase px-1.5 py-0.5 rounded flex-shrink-0 ${agentColor}`}>
        {agent}
      </span>
      <div className="min-w-0">
        <span className="text-xs text-muted">{action}</span>
        <span className="text-xs text-foreground ml-1">{detail}</span>
      </div>
    </div>
  );
}

function ChatBubble({ name, type, text }: { name: string; type: "human" | "agent"; text: string }) {
  const colors = type === "agent"
    ? "bg-violet-500/10 border-violet-500/20"
    : "bg-blue-500/10 border-blue-500/20";
  const badge = type === "agent"
    ? "bg-violet-500/15 text-violet-400"
    : "bg-blue-500/15 text-blue-400";
  return (
    <div className={`rounded-lg border px-3 py-2 ${colors}`}>
      <div className="flex items-center gap-2 mb-1">
        <span className={`text-[10px] font-mono font-medium uppercase px-1.5 py-0.5 rounded ${badge}`}>{name}</span>
      </div>
      <p className="text-sm text-foreground leading-relaxed">{text}</p>
    </div>
  );
}

function LandingPage() {
  const [publicWorkspaces, setPublicWorkspaces] = useState<Workspace[]>([]);

  useEffect(() => {
    listPublicWorkspaces().then((r) => setPublicWorkspaces(r?.workspaces ?? [])).catch(() => {});
  }, []);

  return (
    <div className="min-h-screen flex flex-col">
      <Header user={null} />

      {/* Hero — compact */}
      <section className="text-center pt-16 pb-10 px-4">
        <h1 className="text-5xl font-black text-foreground mb-3 tracking-tight font-display">octopus</h1>
        <p className="text-lg text-dim mb-6 max-w-lg mx-auto">
          A shared memory for your AI agent team. Every session, every edit, every finding — searchable and curated automatically.
        </p>
        <div className="flex items-center justify-center gap-3">
          <Link href="/login" className="bg-brand hover:bg-brand-hover text-foreground px-6 py-2.5 rounded-lg text-sm font-medium transition-colors">
            Get Started
          </Link>
          <Link href="/docs" className="text-dim hover:text-foreground px-4 py-2.5 rounded-lg text-sm border border-border hover:border-foreground/20 transition-colors">
            Docs
          </Link>
        </div>
      </section>

      {/* Product loop — three panels */}
      <section className="max-w-5xl mx-auto px-4 pb-16 w-full">
        <div className="grid gap-4 lg:grid-cols-3">

          {/* CONSUME */}
          <div className="bg-surface border border-border rounded-lg overflow-hidden">
            <div className="px-4 py-3 border-b border-border flex items-center gap-2">
              <span className="text-[10px] font-mono font-medium text-muted uppercase tracking-wider">Consume</span>
              <span className="text-[10px] text-muted">— data flows in</span>
            </div>
            <div className="px-4 py-3">
              <EventLine
                time="14:32"
                agent="rex"
                agentColor="bg-violet-500/15 text-violet-400"
                action="tool_call"
                detail="Read src/auth.ts"
              />
              <EventLine
                time="14:32"
                agent="rex"
                agentColor="bg-violet-500/15 text-violet-400"
                action="edit"
                detail="Added JWT refresh logic"
              />
              <EventLine
                time="14:33"
                agent="scout"
                agentColor="bg-violet-500/15 text-violet-400"
                action="web_search"
                detail="OAuth 2.1 best practices 2026"
              />
              <EventLine
                time="14:35"
                agent="scout"
                agentColor="bg-violet-500/15 text-violet-400"
                action="memory"
                detail="Saved 3 research summaries"
              />
              <div className="mt-3 pt-3 border-t border-border">
                <p className="text-xs text-muted">
                  Every tool call, edit, and session auto-streams from connected agents.
                </p>
              </div>
            </div>
          </div>

          {/* CURATE */}
          <div className="bg-surface border border-border rounded-lg overflow-hidden">
            <div className="px-4 py-3 border-b border-border flex items-center gap-2">
              <span className="text-[10px] font-mono font-medium text-muted uppercase tracking-wider">Curate</span>
              <span className="text-[10px] text-muted">— auto-organized</span>
            </div>
            <div className="px-4 py-3">
              <div className="mb-3">
                <div className="flex items-center gap-2 mb-1">
                  <span className="w-5 h-5 rounded bg-green-500/15 text-green-500 flex items-center justify-center text-[10px] font-bold">N</span>
                  <span className="text-sm font-medium text-foreground">Authentication Patterns</span>
                </div>
                <div className="flex gap-1.5 mb-2">
                  <span className="text-[10px] bg-raised text-muted px-1.5 py-0.5 rounded">security</span>
                  <span className="text-[10px] bg-raised text-muted px-1.5 py-0.5 rounded">auth</span>
                </div>
                <div className="text-xs text-dim leading-relaxed">
                  JWT refresh tokens should use rotation with reuse detection.
                  See <span className="text-brand">[[OAuth 2.1 Research]]</span> for
                  the latest spec changes. Rex implemented this
                  in <span className="font-mono text-foreground">src/auth.ts</span>...
                </div>
              </div>
              <div className="flex items-center gap-2 py-1.5 px-2 rounded bg-raised/50">
                <span className="w-4 h-4 rounded bg-green-500/15 text-green-500 flex items-center justify-center text-[9px] font-bold">N</span>
                <span className="text-xs text-dim">OAuth 2.1 Research</span>
                <span className="text-[9px] text-muted ml-auto">2 backlinks</span>
              </div>
              <div className="flex items-center gap-2 py-1.5 px-2 rounded">
                <span className="w-4 h-4 rounded bg-green-500/15 text-green-500 flex items-center justify-center text-[9px] font-bold">N</span>
                <span className="text-xs text-dim">Session Management</span>
                <span className="text-[9px] text-muted ml-auto">1 backlink</span>
              </div>
              <div className="mt-3 pt-3 border-t border-border">
                <p className="text-xs text-muted">
                  Use the curate tool to organize raw data into a wiki with categories and [[backlinks]].
                </p>
              </div>
            </div>
          </div>

          {/* COLLABORATE */}
          <div className="bg-surface border border-border rounded-lg overflow-hidden">
            <div className="px-4 py-3 border-b border-border flex items-center gap-2">
              <span className="text-[10px] font-mono font-medium text-muted uppercase tracking-wider">Collaborate</span>
              <span className="text-[10px] text-muted">— work together</span>
            </div>
            <div className="px-4 py-3 space-y-2">
              <ChatBubble
                name="sam"
                type="human"
                text="What did we learn about token rotation from the auth research?"
              />
              <ChatBubble
                name="rex"
                type="agent"
                text="JWT refresh tokens should rotate on every use with reuse detection. I implemented this in src/auth.ts yesterday — see the wiki page for details."
              />
              <ChatBubble
                name="sam"
                type="human"
                text="Ship it. Scout, write up a security report page."
              />
              <div className="mt-3 pt-3 border-t border-border">
                <p className="text-xs text-muted">
                  Agents and humans in the same channels, referencing shared knowledge.
                </p>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Public workspaces */}
      {publicWorkspaces.length > 0 && (
        <section className="max-w-5xl mx-auto px-4 pb-16 w-full">
          <h2 className="text-lg font-medium text-foreground mb-3 font-display">Public Workspaces</h2>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {publicWorkspaces.map((ws) => (
              <Link key={ws.id} href={`/workspaces/${ws.id}`} className="bg-surface border border-border rounded-lg p-4 hover:border-brand transition-colors">
                <div className="text-foreground font-medium">{ws.name}</div>
                {ws.description && <div className="text-dim text-sm mt-1">{ws.description}</div>}
              </Link>
            ))}
          </div>
        </section>
      )}

      {/* Self-host footer */}
      <section className="max-w-5xl mx-auto px-4 pb-16 w-full">
        <div className="bg-surface border border-border rounded-lg px-6 py-5 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
          <div>
            <h3 className="text-sm font-medium text-foreground mb-1">Self-host Octopus</h3>
            <p className="text-xs text-muted">
              <span className="font-mono">git clone</span> → <span className="font-mono">docker compose up</span> → done. PostgreSQL + pgvector, no other dependencies required.
            </p>
          </div>
          <Link href="/docs/quickstart" className="text-xs text-brand hover:text-brand-hover flex-shrink-0">
            Setup guide →
          </Link>
        </div>
      </section>

      {/* Bottom */}
      <footer className="border-t border-border py-6 text-center">
        <p className="text-xs text-muted">MIT License · <a href="https://github.com/Fergana-Labs/octopus" className="hover:text-foreground">GitHub</a></p>
      </footer>
    </div>
  );
}

function LoggedInHome({ user, logout }: { user: NonNullable<ReturnType<typeof useAuth>["user"]>; logout: () => void }) {
  const router = useRouter();
  const [feed, setFeed] = useState<FeedItem[]>([]);
  const [loading, setLoading] = useState(true);

  // Visualization state
  const [timeline, setTimeline] = useState<ActivityTimeline | null>(null);
  const [density, setDensity] = useState<KnowledgeDensity | null>(null);
  const [projection, setProjection] = useState<EmbeddingProjection | null>(null);
  const [vizLoading, setVizLoading] = useState(true);

  useEffect(() => {
    setVizLoading(true);
    Promise.all([
      getActivityTimeline().catch(() => null),
      getKnowledgeDensity().catch(() => null),
      getEmbeddingProjection().catch(() => null),
    ]).then(([tl, kd, ep]) => {
      setTimeline(tl);
      setDensity(kd);
      setProjection(ep);
      setVizLoading(false);
    });
  }, []);

  useEffect(() => {
    setLoading(true);
    Promise.all([
      listMyWorkspaces().then((r) => r?.workspaces ?? []).catch(() => [] as Workspace[]),
      listAllNotebooks().then((r) => r?.notebooks ?? []).catch(() => [] as NotebookWithWorkspace[]),
    ]).then(([workspaces, notebooks]) => {
      const items: FeedItem[] = [];

      for (const ws of workspaces) {
        items.push({
          id: ws.id, type: "workspace", name: ws.name, description: ws.description,
          href: `/workspaces/${ws.id}`, updatedAt: ws.updated_at, icon: "W",
          badge: `${ws.member_count ?? 0} members`,
        });
      }

      for (const nb of notebooks) {
        items.push({
          id: nb.id, type: "notebook", name: nb.name,
          description: nb.workspace_name || "Personal",
          href: "/notebooks", updatedAt: nb.updated_at, icon: "N",
          badge: nb.workspace_name || "Personal",
        });
      }

      items.sort((a, b) => new Date(b.updatedAt).getTime() - new Date(a.updatedAt).getTime());
      setFeed(items);
      setLoading(false);
    });
  }, []);

  const iconColors: Record<string, string> = {
    workspace: "bg-brand/15 text-brand",
    notebook: "bg-green-500/15 text-green-500",
    memory: "bg-violet-500/15 text-violet-500",
  };

  const workspaceItems = feed.filter((f) => f.type === "workspace");
  const activityItems = feed.filter((f) => f.type !== "workspace");


  const hasVizData = timeline?.buckets.length || density?.clusters.length || projection?.points.length;

  return (
    <AppShell user={user} onLogout={logout}>
      <div className="max-w-6xl mx-auto w-full px-4 py-8">
        {/* Dashboard Visualizations */}
        {(vizLoading || hasVizData) ? (
          <div className="mb-8 space-y-4">
            <DashboardSection
              title="Agent Activity"
              loading={vizLoading}
              empty={!timeline?.buckets.length}
              emptyMessage="No agent activity yet. Connect an agent to start tracking."
            >
              {timeline && <AgentActivityTimeline data={timeline} />}
            </DashboardSection>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <DashboardSection
                title="Knowledge Density"
                loading={vizLoading}
                empty={!density?.clusters.length}
                emptyMessage="No knowledge base content yet. Create a notebook or push data to a table."
              >
                {density && (
                  <KnowledgeDensityMap
                    data={density}
                    onTopicClick={(topic) => router.push(`/search?q=${encodeURIComponent(topic)}`)}
                  />
                )}
              </DashboardSection>

              <DashboardSection
                title="Embedding Space"
                loading={vizLoading}
                empty={!projection?.points.length}
                emptyMessage="No embeddings yet. Embeddings are generated when you add content to notebooks, tables, or history."
              >
                {projection && <EmbeddingSpaceExplorer data={projection} />}
              </DashboardSection>
            </div>
          </div>
        ) : null}

        {/* Workspace cards + activity feed */}
        {loading ? (
          <p className="text-muted text-sm">Loading...</p>
        ) : feed.length === 0 ? (
          <div className="text-center py-12">
            <p className="text-dim mb-4">Nothing here yet. Get started by creating something.</p>
            <div className="flex gap-3 justify-center">
              <Link href="/rooms" className="text-sm bg-brand hover:bg-brand-hover text-foreground px-4 py-2 rounded">Create Workspace</Link>
              <Link href="/notebooks" className="text-sm bg-raised text-dim px-4 py-2 rounded border border-border">New Notebook</Link>
            </div>
          </div>
        ) : (
          <>
            {/* Workspaces */}
            {workspaceItems.length > 0 && (
              <section className="mb-8">
                <div className="flex items-center justify-between mb-3">
                  <h2 className="text-sm font-medium text-muted uppercase tracking-wider">Workspaces</h2>
                  <Link href="/rooms" className="text-xs text-brand hover:text-brand-hover">Manage</Link>
                </div>
                <div className="grid grid-cols-2 gap-2">
                  {workspaceItems.map((item) => (
                    <Link key={item.id} href={item.href} className="bg-surface border border-border rounded-lg p-3 hover:bg-raised transition-colors">
                      <div className="text-sm text-foreground font-medium truncate">{item.name}</div>
                      {item.description && <div className="text-xs text-muted truncate mt-0.5">{item.description}</div>}
                      <div className="text-[10px] text-muted mt-1">{item.badge}</div>
                    </Link>
                  ))}
                </div>
              </section>
            )}

            {/* Recent Activity */}
            <section>
              <h2 className="text-sm font-medium text-muted uppercase tracking-wider mb-3">Recent Activity</h2>
              <div className="space-y-0.5">
                {activityItems.map((item) => (
                  <Link key={`${item.type}-${item.id}`} href={item.href} className="flex items-center gap-3 px-3 py-2.5 rounded-lg hover:bg-raised transition-colors">
                    <div className={`w-8 h-8 rounded-md flex items-center justify-center text-xs font-bold flex-shrink-0 ${item.badgeColor || iconColors[item.type] || "bg-raised text-muted"}`}>
                      {item.icon}
                    </div>
                    <div className="min-w-0 flex-1">
                      <div className="text-sm text-foreground truncate">{item.name}</div>
                      {item.description && <div className="text-xs text-muted truncate">{item.description}</div>}
                    </div>
                    <div className="flex items-center gap-2 flex-shrink-0">
                      {item.badge && <span className="text-[10px] text-muted bg-raised px-1.5 py-0.5 rounded">{item.badge}</span>}
                      <span className="text-xs text-muted">{formatRelativeTime(item.updatedAt)}</span>
                    </div>
                  </Link>
                ))}
                {activityItems.length === 0 && (
                  <p className="text-muted text-sm py-4">No recent activity yet.</p>
                )}
              </div>
            </section>
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
