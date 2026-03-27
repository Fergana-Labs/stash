"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import AppShell from "../../components/AppShell";
import { useAuth } from "../../hooks/useAuth";
import {
  createAgent,
  deleteAgent,
  listAgents,
  rotateAgentKey,
  updateAgent,
} from "../../lib/api";
import { AgentProfile } from "../../lib/types";

export default function AgentsPage() {
  const router = useRouter();
  const { user, loading, logout } = useAuth();
  const [agents, setAgents] = useState<AgentProfile[]>([]);
  const [showCreate, setShowCreate] = useState(false);
  const [newName, setNewName] = useState("");
  const [newDisplayName, setNewDisplayName] = useState("");
  const [newDescription, setNewDescription] = useState("");
  const [error, setError] = useState("");
  const [newApiKey, setNewApiKey] = useState<string | null>(null);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editDisplayName, setEditDisplayName] = useState("");
  const [editDescription, setEditDescription] = useState("");

  const loadAgents = useCallback(async () => {
    try {
      const list = await listAgents();
      setAgents(list ?? []);
    } catch {
      // ignore — might not be human
    }
  }, []);

  useEffect(() => {
    if (user && user.type === "human") loadAgents();
  }, [user, loadAgents]);

  const handleCreate = async () => {
    if (!newName.trim()) return;
    setError("");
    try {
      const agent = await createAgent(
        newName.trim(),
        newDisplayName.trim() || undefined,
        newDescription.trim() || undefined,
      );
      setNewApiKey(agent.api_key);
      setShowCreate(false);
      setNewName("");
      setNewDisplayName("");
      setNewDescription("");
      await loadAgents();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create agent");
    }
  };

  const handleRotateKey = async (agentId: string) => {
    if (!confirm("Rotate this agent's API key? The old key will stop working immediately.")) return;
    try {
      const result = await rotateAgentKey(agentId);
      setNewApiKey(result.api_key);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to rotate key");
    }
  };

  const handleDelete = async (agentId: string) => {
    if (!confirm("Delete this agent? This cannot be undone.")) return;
    try {
      await deleteAgent(agentId);
      await loadAgents();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to delete agent");
    }
  };

  const startEdit = (agent: AgentProfile) => {
    setEditingId(agent.id);
    setEditDisplayName(agent.display_name || "");
    setEditDescription(agent.description || "");
  };

  const handleSaveEdit = async () => {
    if (!editingId) return;
    try {
      await updateAgent(editingId, {
        display_name: editDisplayName || undefined,
        description: editDescription || undefined,
      });
      setEditingId(null);
      await loadAgents();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to update agent");
    }
  };

  if (loading) {
    return <div className="min-h-screen flex items-center justify-center text-muted">Loading...</div>;
  }
  if (!user) { router.push("/login"); return null; }

  if (user.type !== "human") {
    return (
      <AppShell user={user} onLogout={logout}>
        <div className="flex items-center justify-center h-full text-muted">
          Only human users can manage agents.
        </div>
      </AppShell>
    );
  }

  return (
    <AppShell user={user} onLogout={logout}>
      <div className="max-w-3xl mx-auto w-full px-4 py-8">
        <div className="flex items-center justify-between mb-6">
          <h1 className="text-2xl font-bold text-foreground font-display">Agents</h1>
          <button
            onClick={() => { setShowCreate(true); setNewApiKey(null); }}
            className="text-sm bg-brand hover:bg-brand-hover text-foreground px-3 py-1.5 rounded"
          >
            Create Agent
          </button>
        </div>

        {error && <p className="text-red-400 text-sm mb-4">{error}</p>}

        {newApiKey && (
          <div className="bg-green-900/20 border border-green-800 rounded-lg p-4 mb-6">
            <div className="text-green-400 text-sm font-medium mb-1">API Key (copy now — shown only once)</div>
            <code className="text-green-300 text-xs font-mono bg-green-900/30 px-2 py-1 rounded block break-all select-all">
              {newApiKey}
            </code>
            <button
              onClick={() => setNewApiKey(null)}
              className="text-xs text-green-500 hover:text-green-400 mt-2"
            >
              Dismiss
            </button>
          </div>
        )}

        {showCreate && (
          <div className="bg-surface border border-border rounded-lg p-4 mb-6">
            <h3 className="text-foreground font-medium mb-3">New Agent</h3>
            <input
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              placeholder="Username (a-z, 0-9, -, _)"
              className="w-full bg-raised border border-border rounded px-3 py-2 text-foreground text-sm mb-2 font-mono"
            />
            <input
              value={newDisplayName}
              onChange={(e) => setNewDisplayName(e.target.value)}
              placeholder="Display name (optional)"
              className="w-full bg-raised border border-border rounded px-3 py-2 text-foreground text-sm mb-2"
            />
            <input
              value={newDescription}
              onChange={(e) => setNewDescription(e.target.value)}
              placeholder="Description (optional)"
              className="w-full bg-raised border border-border rounded px-3 py-2 text-foreground text-sm mb-2"
            />
            <div className="flex gap-2">
              <button onClick={handleCreate} className="bg-brand hover:bg-brand-hover text-foreground px-4 py-1.5 rounded text-sm">Create</button>
              <button onClick={() => setShowCreate(false)} className="bg-raised text-dim px-4 py-1.5 rounded text-sm">Cancel</button>
            </div>
          </div>
        )}

        {agents.length === 0 && !showCreate ? (
          <p className="text-muted text-sm">No agents yet. Create one to get started.</p>
        ) : (
          <div className="space-y-2">
            {agents.map((agent) => (
              <div key={agent.id} className="bg-surface border border-border rounded-lg p-4">
                {editingId === agent.id ? (
                  <div className="space-y-2">
                    <input
                      value={editDisplayName}
                      onChange={(e) => setEditDisplayName(e.target.value)}
                      placeholder="Display name"
                      className="w-full bg-raised border border-border rounded px-3 py-1.5 text-foreground text-sm"
                    />
                    <input
                      value={editDescription}
                      onChange={(e) => setEditDescription(e.target.value)}
                      placeholder="Description"
                      className="w-full bg-raised border border-border rounded px-3 py-1.5 text-foreground text-sm"
                    />
                    <div className="flex gap-2">
                      <button onClick={handleSaveEdit} className="text-xs bg-brand hover:bg-brand-hover text-foreground px-3 py-1 rounded">Save</button>
                      <button onClick={() => setEditingId(null)} className="text-xs text-dim hover:text-foreground px-3 py-1">Cancel</button>
                    </div>
                  </div>
                ) : (
                  <div className="flex items-start justify-between">
                    <div>
                      <div className="flex items-center gap-2">
                        <span className="text-foreground font-medium">{agent.display_name || agent.name}</span>
                        <span className="text-[10px] uppercase font-mono px-1.5 py-0.5 rounded bg-agent-muted text-agent">
                          agent
                        </span>
                      </div>
                      <div className="text-xs text-muted font-mono mt-0.5">@{agent.name}</div>
                      {agent.description && (
                        <div className="text-sm text-dim mt-1">{agent.description}</div>
                      )}
                      <div className="text-xs text-muted mt-2">
                        Last seen: {new Date(agent.last_seen).toLocaleString()}
                      </div>
                    </div>
                    <div className="flex gap-1 flex-shrink-0">
                      <button
                        onClick={() => startEdit(agent)}
                        className="text-xs text-dim hover:text-foreground px-2 py-1"
                      >
                        Edit
                      </button>
                      <button
                        onClick={() => handleRotateKey(agent.id)}
                        className="text-xs text-brand hover:text-brand-hover px-2 py-1"
                      >
                        Rotate Key
                      </button>
                      <button
                        onClick={() => handleDelete(agent.id)}
                        className="text-xs text-red-400 hover:text-red-300 px-2 py-1"
                      >
                        Delete
                      </button>
                    </div>
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </AppShell>
  );
}
