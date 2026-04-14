"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { ReactNode, useCallback, useEffect, useState } from "react";
import AppShell from "../../../components/AppShell";
import SetupCard from "../../../components/SetupCard";
import WorkspaceSidebar from "../../../components/workspace/WorkspaceSidebar";
import { useAuth } from "../../../hooks/useAuth";
import {
  createNotebook,
  deleteNotebook,
  getWorkspace,
  listNotebooks,
  listFiles,
  listTables,
  createTable,
  deleteTable,
  joinWorkspace as apiJoinRoom,
  getWorkspaceMembers,
  leaveWorkspace,
  deleteWorkspace,
  kickWorkspaceMember,
  updateWorkspace,
  getActivityTimeline,
  getKnowledgeDensity,
  getEmbeddingProjection,
  getPageGraph,
} from "../../../lib/api";
import {
  ActivityTimeline,
  EmbeddingProjection,
  KnowledgeDensity,
  Notebook,
  FileInfo,
  PageGraph,
  Table,
  Workspace,
  WorkspaceMember,
} from "../../../lib/types";
import DashboardSection from "../../../components/viz/DashboardSection";
import AgentActivityTimeline from "../../../components/viz/AgentActivityTimeline";
import KnowledgeDensityMap from "../../../components/viz/KnowledgeDensityMap";
import EmbeddingSpaceExplorer from "../../../components/viz/EmbeddingSpaceExplorer";
import PageGraphView from "../../../components/workspace/PageGraphView";

interface WorkspaceSectionProps {
  title: string;
  description: string;
  actionLabel?: string;
  onAction?: () => void;
  children: ReactNode;
}

function WorkspaceSection({ title, description, actionLabel, onAction, children }: WorkspaceSectionProps) {
  return (
    <section className="bg-surface border border-border rounded-xl px-5 py-4">
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <h2 className="text-sm font-semibold text-foreground uppercase tracking-wider">{title}</h2>
          <p className="text-sm text-dim mt-1">{description}</p>
        </div>
        {actionLabel && onAction && (
          <button
            onClick={onAction}
            className="text-xs text-brand hover:text-brand-hover px-2 py-1 rounded-md hover:bg-brand/5 transition-colors flex-shrink-0"
          >
            {actionLabel}
          </button>
        )}
      </div>
      <div className="mt-4 pt-4 border-t border-border-subtle">
        {children}
      </div>
    </section>
  );
}

export default function WorkspacePage() {
  const params = useParams();
  const router = useRouter();
  const workspaceId = params.workspaceId as string;
  const { user, loading, logout } = useAuth();

  const [workspace, setWorkspace] = useState<Workspace | null>(null);
  const [notebooks, setNotebooks] = useState<Notebook[]>([]);
  const [tables, setTables] = useState<Table[]>([]);
  const [recentFiles, setRecentFiles] = useState<FileInfo[]>([]);
  const [members, setMembers] = useState<WorkspaceMember[]>([]);
  const [isMember, setIsMember] = useState(false);
  const [error, setError] = useState("");
  const [dataLoaded, setDataLoaded] = useState(false);
  const [showManageSidebar, setShowManageSidebar] = useState(false);

  // Visualization state
  const [timeline, setTimeline] = useState<ActivityTimeline | null>(null);
  const [density, setDensity] = useState<KnowledgeDensity | null>(null);
  const [projection, setProjection] = useState<EmbeddingProjection | null>(null);
  const [vizLoading, setVizLoading] = useState(true);

  // Page graph state
  const [showGraph, setShowGraph] = useState(false);
  const [pageGraph, setPageGraph] = useState<PageGraph | null>(null);
  const [graphNotebookId, setGraphNotebookId] = useState<string | null>(null);

  const loadWorkspace = useCallback(async () => {
    try { setWorkspace(await getWorkspace(workspaceId)); } catch { setError("Workspace not found"); }
  }, [workspaceId]);

  const loadData = useCallback(async () => {
    try {
      const [nbRes, m, tblRes, filesRes] = await Promise.all([
        listNotebooks(workspaceId).then(r => r?.notebooks ?? []).catch(() => [] as Notebook[]),
        getWorkspaceMembers(workspaceId).catch(() => [] as WorkspaceMember[]),
        listTables(workspaceId).then(r => r?.tables ?? []).catch(() => [] as Table[]),
        listFiles(workspaceId).catch(() => [] as FileInfo[]),
      ]);
      setNotebooks(nbRes);
      setMembers(m);
      setTables(tblRes);
      setRecentFiles(filesRes.slice(0, 5));
      if (user) setIsMember(m.some(mem => mem.user_id === user.id));
      setDataLoaded(true);
    } catch { setIsMember(false); setDataLoaded(true); }
  }, [workspaceId, user]);

  useEffect(() => { loadWorkspace(); }, [loadWorkspace]);
  useEffect(() => { if (user) loadData(); }, [user, loadData]);
  useEffect(() => {
    if (!user) return;
    setVizLoading(true);
    Promise.all([
      getActivityTimeline().catch(() => null),
      getKnowledgeDensity().catch(() => null),
      getEmbeddingProjection().catch(() => null),
    ]).then(([t, d, p]) => {
      setTimeline(t);
      setDensity(d);
      setProjection(p);
    }).finally(() => setVizLoading(false));
  }, [user]);

  const handleJoin = async () => {
    if (!workspace) return;
    try { await apiJoinRoom(workspace.invite_code); await loadData(); }
    catch (err) { setError(err instanceof Error ? err.message : "Failed to join"); }
  };

  const handleCreateNotebook = async () => {
    const name = prompt("Notebook name:");
    if (!name) return;
    try { await createNotebook(workspaceId, name); await loadData(); }
    catch (err) { setError(err instanceof Error ? err.message : "Failed to create notebook"); }
  };

  const handleDeleteNotebook = async (nbId: string) => {
    if (!confirm("Delete this notebook and all its pages?")) return;
    try { await deleteNotebook(workspaceId, nbId); await loadData(); }
    catch (err) { setError(err instanceof Error ? err.message : "Failed to delete"); }
  };


  const handleCreateTable = async () => {
    const name = prompt("Table name:");
    if (!name?.trim()) return;
    try { await createTable(workspaceId, name.trim()); await loadData(); }
    catch (err) { setError(err instanceof Error ? err.message : "Failed to create table"); }
  };

  const handleDeleteTable = async (tableId: string) => {
    if (!confirm("Delete this table and all its data?")) return;
    try { await deleteTable(workspaceId, tableId); await loadData(); }
    catch (err) { setError(err instanceof Error ? err.message : "Failed to delete table"); }
  };

  const isOwner = members.some(m => m.user_id === user?.id && m.role === "owner");

  if (loading) return <div className="min-h-screen flex items-center justify-center text-muted">Loading...</div>;
  if (!user) { router.push("/login"); return null; }

  return (
    <AppShell user={user} onLogout={logout}>
      <div className="flex flex-col h-full">
        {/* Workspace header */}
        <div className="bg-surface border-b border-border px-4 py-2 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <h1 className="text-foreground font-medium">{workspace?.name || "Loading..."}</h1>
            {workspace?.description && <span className="text-muted text-sm hidden sm:inline">{workspace.description}</span>}
          </div>
          <div className="flex items-center gap-3">
            <span className="text-xs text-muted">{members.length} member{members.length !== 1 ? "s" : ""}</span>
            {isMember && (
              <button onClick={() => setShowManageSidebar(!showManageSidebar)}
                className={`text-xs px-3 py-1 rounded border ${showManageSidebar ? "bg-brand border-brand text-foreground" : "bg-raised border-border text-dim hover:text-foreground"}`}>
                Settings
              </button>
            )}
          </div>
        </div>

        {error && (
          <div className="bg-red-900/30 border-b border-red-800 text-red-400 text-sm px-4 py-2">
            {error}<button onClick={() => setError("")} className="ml-2 text-red-500 hover:text-red-300">&times;</button>
          </div>
        )}

        {!isMember ? (
          <div className="flex-1 flex items-center justify-center">
            <div className="text-center">
              <p className="text-dim mb-4">You&apos;re not a member of this workspace.</p>
              <button onClick={handleJoin} className="bg-brand hover:bg-brand-hover text-foreground px-6 py-2 rounded">Join Workspace</button>
            </div>
          </div>
        ) : (
          <div className="flex-1 flex overflow-hidden">
            <div className="flex-1 overflow-y-auto">
              <div className="max-w-4xl mx-auto w-full px-6 py-8 space-y-5">
              {dataLoaded && notebooks.length === 0 && (
                <SetupCard workspaceId={workspaceId} />
              )}

              {/* Visualizations */}
              {(vizLoading || timeline?.buckets.length || density?.clusters.length || projection?.points.length) ? (
                <div className="space-y-4">
                  <DashboardSection title="Agent Activity" loading={vizLoading} empty={!timeline?.buckets.length} emptyMessage="No agent activity yet.">
                    {timeline && <AgentActivityTimeline data={timeline} />}
                  </DashboardSection>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <DashboardSection title="Key Topics" loading={vizLoading} empty={!density?.clusters.length} emptyMessage="No content yet.">
                      {density && <KnowledgeDensityMap data={density} onTopicClick={(topic) => router.push(`/search?q=${encodeURIComponent(topic)}`)} />}
                    </DashboardSection>
                    <DashboardSection title="Embedding Space" loading={vizLoading} empty={!projection?.points.length} emptyMessage="No embeddings yet.">
                      {projection && <EmbeddingSpaceExplorer data={projection} />}
                    </DashboardSection>
                  </div>
                </div>
              ) : null}

              {/* Page Graph */}
              {notebooks.length > 0 && (
                <div className="bg-surface border border-border rounded-xl px-5 py-4">
                  <div className="flex items-center justify-between">
                    <h2 className="text-sm font-semibold text-foreground uppercase tracking-wider">Page Graph</h2>
                    <div className="flex items-center gap-2">
                      <select
                        className="text-xs bg-raised border border-border rounded px-2 py-1 text-foreground"
                        value={graphNotebookId || ""}
                        onChange={(e) => {
                          setGraphNotebookId(e.target.value || null);
                          setPageGraph(null);
                          setShowGraph(false);
                        }}
                      >
                        <option value="">Select notebook</option>
                        {notebooks.map((nb) => (
                          <option key={nb.id} value={nb.id}>{nb.name}</option>
                        ))}
                      </select>
                      <button
                        onClick={async () => {
                          if (!graphNotebookId) return;
                          try {
                            const g = await getPageGraph(workspaceId, graphNotebookId);
                            setPageGraph(g);
                            setShowGraph(true);
                          } catch { /* ignore */ }
                        }}
                        disabled={!graphNotebookId}
                        className="text-xs text-brand hover:text-brand-hover px-2 py-1 rounded hover:bg-brand/5 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
                      >
                        View
                      </button>
                    </div>
                  </div>
                  {showGraph && pageGraph && (
                    <div className="mt-4 pt-4 border-t border-border-subtle">
                      <PageGraphView
                        graph={pageGraph}
                        onClose={() => setShowGraph(false)}
                        onSelectPage={() => router.push("/notebooks")}
                        inline
                      />
                    </div>
                  )}
                </div>
              )}

              <WorkspaceSection
                title="Wiki"
                description="Notebooks and tables — wiki pages with backlinks, and structured data."
              >
                {/* Notebooks */}
                <div className="flex items-center justify-between mb-2">
                  <span className="text-[10px] font-medium text-muted uppercase tracking-wider">Notebooks</span>
                  <button onClick={handleCreateNotebook} className="text-xs text-brand hover:text-brand-hover">+ New</button>
                </div>
                {notebooks.length === 0 ? (
                  <p className="text-sm text-muted mb-4">No notebooks yet.</p>
                ) : (
                  <div className="space-y-1 mb-4">
                    {notebooks.map(nb => (
                      <div key={nb.id} className="flex items-center justify-between px-3 py-2 rounded-lg hover:bg-raised transition-colors">
                        <Link href="/notebooks" className="flex items-center gap-3 flex-1 min-w-0">
                          <div className="w-7 h-7 rounded-md bg-green-500/15 text-green-500 flex items-center justify-center text-xs font-bold">N</div>
                          <div>
                            <div className="text-sm text-foreground">{nb.name}</div>
                            {nb.description && <div className="text-xs text-muted">{nb.description}</div>}
                          </div>
                        </Link>
                        <button onClick={() => handleDeleteNotebook(nb.id)} className="text-xs text-red-400 hover:text-red-300 px-2 py-1 opacity-0 group-hover:opacity-100">Delete</button>
                      </div>
                    ))}
                  </div>
                )}

                {/* Tables */}
                <div className="flex items-center justify-between mb-2 pt-3 border-t border-border-subtle">
                  <span className="text-[10px] font-medium text-muted uppercase tracking-wider">Tables</span>
                  <button onClick={handleCreateTable} className="text-xs text-brand hover:text-brand-hover">+ New</button>
                </div>
                {tables.length === 0 ? (
                  <p className="text-sm text-muted">No tables yet.</p>
                ) : (
                  <div className="space-y-1">
                    {tables.map(t => (
                      <div key={t.id} className="group flex items-center justify-between px-3 py-2 rounded-lg hover:bg-raised transition-colors">
                        <Link href={`/tables/${t.id}?workspaceId=${workspaceId}`} className="flex items-center gap-3 flex-1 min-w-0">
                          <div className="w-7 h-7 rounded-md bg-cyan-500/15 text-cyan-500 flex items-center justify-center text-xs font-bold">T</div>
                          <div>
                            <div className="text-sm text-foreground">{t.name}</div>
                            <div className="text-xs text-muted">{t.columns.length} cols, {t.row_count ?? 0} rows</div>
                          </div>
                        </Link>
                        {isOwner && (
                          <button onClick={() => handleDeleteTable(t.id)} className="text-xs text-red-400 hover:text-red-300 px-2 py-1 opacity-0 group-hover:opacity-100">Delete</button>
                        )}
                      </div>
                    ))}
                  </div>
                )}
              </WorkspaceSection>

              <WorkspaceSection
                title="History"
                description="Agent sessions — every tool call, edit, and message."
              >
                <Link href={`/memory?ws=${workspaceId}`} className="flex items-center gap-3 px-3 py-2 rounded-lg hover:bg-raised transition-colors">
                  <div className="w-7 h-7 rounded-md bg-violet-500/15 text-violet-500 flex items-center justify-center text-xs font-bold">H</div>
                  <div className="text-sm text-foreground">View agent sessions</div>
                </Link>
              </WorkspaceSection>

              <WorkspaceSection
                title="Files"
                description="Uploaded images, documents, and attachments."
                actionLabel="View all"
                onAction={() => router.push(`/files?ws=${workspaceId}`)}
              >
                {recentFiles.length === 0 ? (
                  <p className="text-sm text-muted">No files uploaded yet.</p>
                ) : (
                  <div className="space-y-1">
                    {recentFiles.map(f => (
                      <a key={f.id} href={f.url} target="_blank" rel="noopener noreferrer" className="flex items-center gap-3 px-3 py-2 rounded-lg hover:bg-raised transition-colors">
                        <div className="w-7 h-7 rounded-md bg-amber-500/15 text-amber-500 flex items-center justify-center text-[10px] font-bold">
                          {f.content_type.startsWith("image/") ? "IMG" : "FILE"}
                        </div>
                        <div className="flex-1 min-w-0">
                          <div className="text-sm text-foreground truncate">{f.name}</div>
                          <div className="text-xs text-muted">{(f.size_bytes / 1024).toFixed(1)} KB</div>
                        </div>
                      </a>
                    ))}
                    {recentFiles.length >= 5 && (
                      <Link href={`/files?ws=${workspaceId}`} className="block px-3 py-1.5 text-xs text-brand hover:text-brand-hover">
                        View all files...
                      </Link>
                    )}
                  </div>
                )}
              </WorkspaceSection>

              </div>
            </div>

            {/* Settings sidebar */}
            {showManageSidebar && workspace && user && (
              <WorkspaceSidebar
                workspace={workspace}
                members={members}
                currentUserId={user.id}
                isOwner={isOwner}
                onLeave={async () => { await leaveWorkspace(workspaceId); router.push("/rooms"); }}
                onDelete={async () => { await deleteWorkspace(workspaceId); router.push("/rooms"); }}
                onKickMember={async (uid) => { await kickWorkspaceMember(workspaceId, uid); await loadData(); }}
                onUpdateWorkspace={async (data) => { setWorkspace(await updateWorkspace(workspaceId, data)); }}
                onAddMember={async (username) => {
                  const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL || "http://localhost:3456"}/api/v1/workspaces/${workspaceId}/members`, {
                    method: "POST",
                    headers: { "Content-Type": "application/json", "Authorization": `Bearer ${localStorage.getItem("octopus_token") || ""}` },
                    body: JSON.stringify({ username }),
                  });
                  if (!res.ok) {
                    const data = await res.json().catch(() => ({}));
                    throw new Error(data.detail || "Failed to add member");
                  }
                  await loadData();
                }}
              />
            )}
          </div>
        )}
      </div>
    </AppShell>
  );
}
