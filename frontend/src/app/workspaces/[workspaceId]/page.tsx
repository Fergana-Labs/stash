"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import AppShell from "../../../components/AppShell";
import WorkspaceSidebar from "../../../components/workspace/WorkspaceSidebar";
import { useAuth } from "../../../hooks/useAuth";
import {
  createChat,
  createNotebook,
  deleteChat,
  deleteNotebook,
  getWorkspace,
  listNotebooks,
  listChats,
  listHistories,
  createHistory,
  listDecks,
  createDeck,
  deleteDeck,
  getWebhook,
  setWebhook,
  updateWebhook,
  deleteWebhook,
  joinWorkspace as apiJoinRoom,
  getWorkspaceMembers,
  leaveWorkspace,
  deleteWorkspace,
  kickWorkspaceMember,
  updateWorkspace,
} from "../../../lib/api";
import { Chat, Deck, History, Notebook, Webhook, Workspace, WorkspaceMember } from "../../../lib/types";

export default function WorkspacePage() {
  const params = useParams();
  const router = useRouter();
  const workspaceId = params.workspaceId as string;
  const { user, loading, logout } = useAuth();

  const [workspace, setWorkspace] = useState<Workspace | null>(null);
  const [notebooks, setNotebooks] = useState<Notebook[]>([]);
  const [chats, setChats] = useState<Chat[]>([]);
  const [histories, setHistories] = useState<History[]>([]);
  const [decks, setDecks] = useState<Deck[]>([]);
  const [webhook, setWebhookState] = useState<Webhook | null>(null);
  const [members, setMembers] = useState<WorkspaceMember[]>([]);
  const [isMember, setIsMember] = useState(false);
  const [error, setError] = useState("");
  const [showManageSidebar, setShowManageSidebar] = useState(false);
  const [showWebhookForm, setShowWebhookForm] = useState(false);
  const [webhookUrl, setWebhookUrl] = useState("");
  const [webhookSecret, setWebhookSecret] = useState("");

  const buildWorkspaceChatHref = (chat: Chat) => {
    const params = new URLSearchParams({
      kind: "workspace",
      workspaceId,
      label: chat.name,
    });
    return `/chats/${chat.id}?${params.toString()}`;
  };

  const loadWorkspace = useCallback(async () => {
    try { setWorkspace(await getWorkspace(workspaceId)); } catch { setError("Workspace not found"); }
  }, [workspaceId]);

  const loadData = useCallback(async () => {
    try {
      const [nbRes, chatRes, m, histRes, deckRes, wh] = await Promise.all([
        listNotebooks(workspaceId).then(r => r?.notebooks ?? []).catch(() => [] as Notebook[]),
        listChats(workspaceId).then(r => r?.chats ?? []).catch(() => [] as Chat[]),
        getWorkspaceMembers(workspaceId).catch(() => [] as WorkspaceMember[]),
        listHistories(workspaceId).then(r => r?.stores ?? []).catch(() => [] as History[]),
        listDecks(workspaceId).then(r => r?.decks ?? []).catch(() => [] as Deck[]),
        getWebhook(workspaceId).catch(() => null),
      ]);
      setNotebooks(nbRes);
      setChats(chatRes);
      setMembers(m);
      setHistories(histRes);
      setDecks(deckRes);
      setWebhookState(wh);
      if (wh) { setWebhookUrl(wh.url); }
      if (user) setIsMember(m.some(mem => mem.user_id === user.id));
    } catch { setIsMember(false); }
  }, [workspaceId, user]);

  useEffect(() => { loadWorkspace(); }, [loadWorkspace]);
  useEffect(() => { if (user) loadData(); }, [user, loadData]);

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

  const handleCreateChat = async () => {
    const name = prompt("Chat name:");
    if (!name?.trim()) return;
    try {
      const chat = await createChat(workspaceId, name.trim());
      await loadData();
      router.push(buildWorkspaceChatHref(chat));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create chat");
    }
  };

  const handleDeleteChat = async (chatId: string) => {
    if (!confirm("Delete this chat and all its messages?")) return;
    try { await deleteChat(workspaceId, chatId); await loadData(); }
    catch (err) { setError(err instanceof Error ? err.message : "Failed to delete chat"); }
  };

  const handleDeleteNotebook = async (nbId: string) => {
    if (!confirm("Delete this notebook and all its pages?")) return;
    try { await deleteNotebook(workspaceId, nbId); await loadData(); }
    catch (err) { setError(err instanceof Error ? err.message : "Failed to delete"); }
  };

  const handleCreateHistory = async () => {
    const name = prompt("History store name:");
    if (!name?.trim()) return;
    try { await createHistory(workspaceId, name.trim()); await loadData(); }
    catch (err) { setError(err instanceof Error ? err.message : "Failed to create history store"); }
  };

  const handleCreateDeck = async () => {
    const name = prompt("Deck name:");
    if (!name?.trim()) return;
    try { await createDeck(workspaceId, name.trim()); await loadData(); }
    catch (err) { setError(err instanceof Error ? err.message : "Failed to create deck"); }
  };

  const handleDeleteDeck = async (deckId: string) => {
    if (!confirm("Delete this deck?")) return;
    try { await deleteDeck(workspaceId, deckId); await loadData(); }
    catch (err) { setError(err instanceof Error ? err.message : "Failed to delete deck"); }
  };

  const handleSaveWebhook = async () => {
    if (!webhookUrl.trim()) return;
    try {
      if (webhook) {
        await updateWebhook(workspaceId, { url: webhookUrl.trim() });
      } else {
        await setWebhook(workspaceId, webhookUrl.trim(), webhookSecret || undefined);
      }
      await loadData();
      setShowWebhookForm(false);
      setWebhookSecret("");
    } catch (err) { setError(err instanceof Error ? err.message : "Failed to save webhook"); }
  };

  const handleDeleteWebhook = async () => {
    if (!confirm("Delete your webhook for this workspace?")) return;
    try { await deleteWebhook(workspaceId); setWebhookState(null); setWebhookUrl(""); setShowWebhookForm(false); }
    catch (err) { setError(err instanceof Error ? err.message : "Failed to delete webhook"); }
  };

  const handleToggleWebhook = async () => {
    if (!webhook) return;
    try { await updateWebhook(workspaceId, { is_active: !webhook.is_active }); await loadData(); }
    catch (err) { setError(err instanceof Error ? err.message : "Failed to update webhook"); }
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
            <Link href="/rooms" className="text-dim hover:text-foreground text-sm">&larr;</Link>
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
            <div className="flex-1 overflow-y-auto px-6 py-6 max-w-3xl">
              {/* Chats */}
              <section className="mb-8">
                <div className="flex items-center justify-between mb-3">
                  <h2 className="text-sm font-medium text-muted uppercase tracking-wider">Chats</h2>
                  <button onClick={handleCreateChat} className="text-xs text-brand hover:text-brand-hover">+ New</button>
                </div>
                {chats.length === 0 ? (
                  <p className="text-muted text-sm">No chats in this workspace yet.</p>
                ) : (
                  <div className="space-y-1">
                    {chats.map(chat => (
                      <div key={chat.id} className="flex items-center justify-between px-3 py-2 rounded-lg hover:bg-raised transition-colors">
                        <Link href={buildWorkspaceChatHref(chat)} className="flex items-center gap-3 flex-1 min-w-0">
                          <div className="w-7 h-7 rounded-md bg-brand/15 text-brand flex items-center justify-center text-xs font-bold">#</div>
                          <div className="text-sm text-foreground">{chat.name}</div>
                        </Link>
                        {isOwner && (
                          <button onClick={() => handleDeleteChat(chat.id)} className="text-xs text-red-400 hover:text-red-300 px-2 py-1 opacity-0 group-hover:opacity-100">Delete</button>
                        )}
                      </div>
                    ))}
                  </div>
                )}
              </section>

              {/* Notebooks */}
              <section className="mb-8">
                <div className="flex items-center justify-between mb-3">
                  <h2 className="text-sm font-medium text-muted uppercase tracking-wider">Notebooks</h2>
                  <button onClick={handleCreateNotebook} className="text-xs text-brand hover:text-brand-hover">+ New</button>
                </div>
                {notebooks.length === 0 ? (
                  <p className="text-muted text-sm">No notebooks yet.</p>
                ) : (
                  <div className="space-y-1">
                    {notebooks.map(nb => (
                      <div key={nb.id} className="flex items-center justify-between px-3 py-2 rounded-lg hover:bg-raised transition-colors">
                        <Link href="/notebooks" className="flex items-center gap-3 flex-1 min-w-0">
                          <div className="w-7 h-7 rounded-md bg-green-500/15 text-green-500 flex items-center justify-center text-xs font-bold">N</div>
                          <div>
                            <div className="text-sm text-foreground">{nb.name}</div>
                            {nb.description && <div className="text-xs text-muted">{nb.description}</div>}
                          </div>
                        </Link>
                        <button onClick={() => handleDeleteNotebook(nb.id)} className="text-xs text-red-400 hover:text-red-300 px-2 py-1">Delete</button>
                      </div>
                    ))}
                  </div>
                )}
              </section>

              {/* History Stores */}
              <section className="mb-8">
                <div className="flex items-center justify-between mb-3">
                  <h2 className="text-sm font-medium text-muted uppercase tracking-wider">History</h2>
                  <button onClick={handleCreateHistory} className="text-xs text-brand hover:text-brand-hover">+ New</button>
                </div>
                {histories.length === 0 ? (
                  <p className="text-muted text-sm">No history stores yet. Create one for agents to stream activity.</p>
                ) : (
                  <div className="space-y-1">
                    {histories.map(h => (
                      <Link key={h.id} href="/memory" className="flex items-center gap-3 px-3 py-2 rounded-lg hover:bg-raised transition-colors">
                        <div className="w-7 h-7 rounded-md bg-violet-500/15 text-violet-500 flex items-center justify-center text-xs font-bold">H</div>
                        <div className="flex-1 min-w-0">
                          <div className="text-sm text-foreground">{h.name}</div>
                          {h.description && <div className="text-xs text-muted truncate">{h.description}</div>}
                        </div>
                        {h.event_count != null && (
                          <span className="text-xs text-muted">{h.event_count} events</span>
                        )}
                      </Link>
                    ))}
                  </div>
                )}
              </section>

              {/* Decks */}
              <section className="mb-8">
                <div className="flex items-center justify-between mb-3">
                  <h2 className="text-sm font-medium text-muted uppercase tracking-wider">Decks</h2>
                  <button onClick={handleCreateDeck} className="text-xs text-brand hover:text-brand-hover">+ New</button>
                </div>
                {decks.length === 0 ? (
                  <p className="text-muted text-sm">No decks yet. Create one for HTML pages, slides, or dashboards.</p>
                ) : (
                  <div className="space-y-1">
                    {decks.map(d => (
                      <div key={d.id} className="flex items-center justify-between px-3 py-2 rounded-lg hover:bg-raised transition-colors">
                        <Link href={`/decks/${d.id}/edit?workspaceId=${workspaceId}`} className="flex items-center gap-3 flex-1 min-w-0">
                          <div className="w-7 h-7 rounded-md bg-blue-500/15 text-blue-500 flex items-center justify-center text-xs font-bold">D</div>
                          <div>
                            <div className="text-sm text-foreground">{d.name}</div>
                            <div className="text-xs text-muted">{d.deck_type}</div>
                          </div>
                        </Link>
                        <button onClick={() => handleDeleteDeck(d.id)} className="text-xs text-red-400 hover:text-red-300 px-2 py-1">Delete</button>
                      </div>
                    ))}
                  </div>
                )}
              </section>

              {/* Webhooks */}
              <section className="mb-8">
                <div className="flex items-center justify-between mb-3">
                  <h2 className="text-sm font-medium text-muted uppercase tracking-wider">Webhook</h2>
                  {!webhook && !showWebhookForm && (
                    <button onClick={() => setShowWebhookForm(true)} className="text-xs text-brand hover:text-brand-hover">+ Configure</button>
                  )}
                </div>
                {webhook && !showWebhookForm ? (
                  <div className="bg-raised border border-border rounded-lg px-4 py-3">
                    <div className="flex items-center justify-between mb-2">
                      <div className="flex items-center gap-2">
                        <div className={`w-2 h-2 rounded-full ${webhook.is_active ? "bg-green-500" : "bg-gray-400"}`} />
                        <span className="text-sm text-foreground">{webhook.is_active ? "Active" : "Paused"}</span>
                      </div>
                      <div className="flex items-center gap-2">
                        <button onClick={handleToggleWebhook} className="text-xs text-dim hover:text-foreground">
                          {webhook.is_active ? "Pause" : "Resume"}
                        </button>
                        <button onClick={() => setShowWebhookForm(true)} className="text-xs text-brand hover:text-brand-hover">Edit</button>
                        <button onClick={handleDeleteWebhook} className="text-xs text-red-400 hover:text-red-300">Delete</button>
                      </div>
                    </div>
                    <div className="text-xs text-muted font-mono truncate">{webhook.url}</div>
                    {webhook.has_secret && <div className="text-xs text-muted mt-1">HMAC-SHA256 signing enabled</div>}
                    {webhook.event_filter.length > 0 && (
                      <div className="text-xs text-muted mt-1">Events: {webhook.event_filter.join(", ")}</div>
                    )}
                  </div>
                ) : showWebhookForm ? (
                  <div className="bg-raised border border-border rounded-lg px-4 py-3 space-y-3">
                    <div>
                      <label className="block text-xs text-dim mb-1">Webhook URL</label>
                      <input
                        type="url"
                        value={webhookUrl}
                        onChange={e => setWebhookUrl(e.target.value)}
                        placeholder="https://example.com/webhook"
                        className="w-full bg-surface border border-border rounded px-3 py-2 text-sm text-foreground focus:outline-none focus:border-brand"
                      />
                    </div>
                    {!webhook && (
                      <div>
                        <label className="block text-xs text-dim mb-1">Secret (optional, for HMAC-SHA256 signing)</label>
                        <input
                          type="text"
                          value={webhookSecret}
                          onChange={e => setWebhookSecret(e.target.value)}
                          placeholder="your-webhook-secret"
                          className="w-full bg-surface border border-border rounded px-3 py-2 text-sm text-foreground focus:outline-none focus:border-brand"
                        />
                      </div>
                    )}
                    <div className="text-xs text-muted">
                      Receives <code className="text-foreground">chat.message</code> and <code className="text-foreground">memory.event</code> payloads via POST.
                    </div>
                    <div className="flex gap-2">
                      <button onClick={handleSaveWebhook} className="bg-brand hover:bg-brand-hover text-foreground px-3 py-1.5 rounded text-sm">
                        {webhook ? "Update" : "Create"}
                      </button>
                      <button onClick={() => { setShowWebhookForm(false); if (webhook) setWebhookUrl(webhook.url); }}
                        className="text-sm text-dim hover:text-foreground px-3 py-1.5">Cancel</button>
                    </div>
                  </div>
                ) : (
                  <p className="text-muted text-sm">No webhook configured. Set one up to receive event notifications.</p>
                )}
              </section>
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
              />
            )}
          </div>
        )}
      </div>
    </AppShell>
  );
}
