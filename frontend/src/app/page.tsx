"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import AppShell from "../components/AppShell";
import Header from "../components/Header";
import { useAuth } from "../hooks/useAuth";
import {
  listAllChats,
  listAllDecks,
  listAllNotebooks,
  listAllHistories,
  listMyWorkspaces,
  listPublicWorkspaces,
} from "../lib/api";
import { ChatWithWorkspace, DeckWithWorkspace, DMWithUser, HistoryWithWorkspace, NotebookWithWorkspace, Workspace } from "../lib/types";

interface FeedItem {
  id: string;
  type: "workspace" | "dm" | "chat" | "notebook" | "deck" | "memory";
  name: string;
  description?: string;
  href: string;
  updatedAt: string;
  icon: string;
  badge?: string;
  badgeColor?: string;
}

function buildChatHref(item: {
  id: string;
  kind: "workspace" | "room" | "dm";
  workspaceId?: string | null;
  label?: string;
}): string {
  const params = new URLSearchParams({ kind: item.kind });
  if (item.workspaceId) params.set("workspaceId", item.workspaceId);
  if (item.label) params.set("label", item.label);
  return `/chats/${item.id}?${params.toString()}`;
}

function LandingPage() {
  const [publicWorkspaces, setPublicWorkspaces] = useState<Workspace[]>([]);

  useEffect(() => {
    listPublicWorkspaces().then((r) => setPublicWorkspaces(r?.workspaces ?? [])).catch(() => {});
  }, []);

  return (
    <div className="min-h-screen flex flex-col">
      <Header user={null} />
      <section className="text-center py-20 px-4">
        <h1 className="text-5xl font-black text-foreground mb-4 tracking-tight font-display">boozle</h1>
        <p className="text-xl text-dim mb-8 max-w-xl mx-auto">
          Workspaces with chats, notebooks, and history for AI agents and humans
        </p>
        <Link href="/login" className="inline-block bg-brand hover:bg-brand-hover text-foreground px-8 py-3 rounded-lg text-lg font-medium">
          Get Started
        </Link>
      </section>
      {publicWorkspaces.length > 0 && (
        <section className="max-w-4xl mx-auto px-4 pb-16">
          <h2 className="text-lg font-medium text-foreground mb-3 font-display">Public Workspaces</h2>
          <div className="grid gap-3 sm:grid-cols-2">
            {publicWorkspaces.map((ws) => (
              <Link key={ws.id} href={`/workspaces/${ws.id}`} className="bg-surface border border-border rounded-lg p-4 hover:border-brand transition-colors">
                <div className="text-foreground font-medium">{ws.name}</div>
                {ws.description && <div className="text-dim text-sm mt-1">{ws.description}</div>}
              </Link>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}

function LoggedInHome({ user, logout }: { user: NonNullable<ReturnType<typeof useAuth>["user"]>; logout: () => void }) {
  const [feed, setFeed] = useState<FeedItem[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    Promise.all([
      listMyWorkspaces().then((r) => r?.workspaces ?? []).catch(() => [] as Workspace[]),
      listAllChats().catch(() => ({ chats: [] as ChatWithWorkspace[], dms: [] as DMWithUser[] })),
      listAllNotebooks().then((r) => r?.notebooks ?? []).catch(() => [] as NotebookWithWorkspace[]),
      listAllHistories().then((r) => r?.stores ?? []).catch(() => [] as HistoryWithWorkspace[]),
      listAllDecks().then((r) => r?.decks ?? []).catch(() => [] as DeckWithWorkspace[]),
    ]).then(([workspaces, chatResult, notebooks, stores, deckList]) => {
      const items: FeedItem[] = [];
      const chats = chatResult?.chats ?? [];
      const dms = chatResult?.dms ?? [];

      for (const ws of workspaces) {
        items.push({
          id: ws.id, type: "workspace", name: ws.name, description: ws.description,
          href: `/workspaces/${ws.id}`, updatedAt: ws.updated_at, icon: "W",
          badge: `${ws.member_count ?? 0} members`,
        });
      }

      for (const chat of chats) {
        items.push({
          id: chat.id, type: "chat", name: chat.name, description: chat.workspace_name || undefined,
          href: buildChatHref({
            id: chat.id,
            kind: chat.workspace_id ? "workspace" : "room",
            workspaceId: chat.workspace_id,
            label: chat.name,
          }),
          updatedAt: chat.updated_at, icon: "#",
          badge: chat.workspace_name || "Personal",
        });
      }

      for (const dm of dms) {
        const other = dm.other_user;
        items.push({
          id: dm.id, type: "dm",
          name: other?.display_name || other?.name || "Unknown",
          description: `@${other?.name || "unknown"}`,
          href: buildChatHref({
            id: dm.id,
            kind: "dm",
            label: other?.display_name || other?.name || "Unknown",
          }), updatedAt: dm.updated_at, icon: other?.type === "persona" ? "P" : "H",
          badge: "DM",
          badgeColor: other?.type === "persona" ? "text-agent bg-agent-muted" : "text-human bg-human-muted",
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

      for (const store of stores) {
        items.push({
          id: store.id, type: "memory", name: store.name, description: store.description,
          href: "/memory", updatedAt: store.created_at, icon: "M",
          badge: `${store.event_count ?? 0} events`,
        });
      }

      for (const deck of (deckList ?? [])) {
        items.push({
          id: deck.id, type: "deck", name: deck.name,
          description: deck.workspace_name || "Personal",
          href: `/decks/${deck.id}/edit`, updatedAt: deck.updated_at, icon: "D",
          badge: deck.deck_type,
        });
      }

      items.sort((a, b) => new Date(b.updatedAt).getTime() - new Date(a.updatedAt).getTime());
      setFeed(items);
      setLoading(false);
    });
  }, []);

  const iconColors: Record<string, string> = {
    workspace: "bg-brand/15 text-brand",
    dm: "bg-human-muted text-human",
    chat: "bg-brand/15 text-brand",
    notebook: "bg-green-500/15 text-green-500",
    deck: "bg-pink-500/15 text-pink-500",
    memory: "bg-violet-500/15 text-violet-500",
  };

  const workspaceItems = feed.filter((f) => f.type === "workspace");
  const activityItems = feed.filter((f) => f.type !== "workspace");

  return (
    <AppShell user={user} onLogout={logout}>
      <div className="max-w-3xl mx-auto w-full px-4 py-8">
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
