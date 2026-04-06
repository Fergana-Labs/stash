"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import AppShell from "../../components/AppShell";
import { useAuth } from "../../hooks/useAuth";
import {
  createPersona,
  deletePersona,
  listPersonasWithContext,
  rotatePersonaKey,
  updatePersona,
  getSleepConfig,
  updateSleepConfig,
  triggerSleep,
  getPersonaSleepConfig,
  updatePersonaSleepConfig,
  triggerPersonaSleep,
  listMyWorkspaces,
} from "../../lib/api";
import { PersonaWithContext, SleepConfig, Workspace } from "../../lib/types";

const ALL_SOURCES = ["history", "notebooks", "documents", "tables"] as const;

function SleepAgentConfig() {
  const [config, setConfig] = useState<SleepConfig | null>(null);
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const [saving, setSaving] = useState(false);
  const [triggerResult, setTriggerResult] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    getSleepConfig().then(setConfig).catch(() => {});
    listMyWorkspaces().then((r) => setWorkspaces(r?.workspaces ?? [])).catch(() => {});
  }, []);

  const handleSave = async () => {
    if (!config) return;
    setSaving(true);
    setError("");
    try {
      const updated = await updateSleepConfig({
        enabled: config.enabled,
        interval_minutes: config.interval_minutes,
        curation_sources: config.curation_sources,
        workspace_ids: config.workspace_ids,
        curation_model: config.curation_model,
      });
      setConfig(updated);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save");
    }
    setSaving(false);
  };

  const handleTrigger = async () => {
    setTriggerResult("");
    try {
      const res = await triggerSleep();
      setTriggerResult(`Status: ${res.status || "done"}, items: ${res.total_items_curated || res.episodes_processed || 0}`);
    } catch (err) {
      setTriggerResult(err instanceof Error ? err.message : "Failed");
    }
  };

  const toggleSource = (src: string) => {
    if (!config) return;
    const sources = new Set(config.curation_sources);
    if (sources.has(src)) sources.delete(src);
    else sources.add(src);
    setConfig({ ...config, curation_sources: Array.from(sources) });
  };

  const toggleWorkspace = (wsId: string) => {
    if (!config) return;
    const ids = new Set(config.workspace_ids);
    if (ids.has(wsId)) ids.delete(wsId);
    else ids.add(wsId);
    setConfig({ ...config, workspace_ids: Array.from(ids) });
  };

  if (!config) return <div className="flex items-center justify-center h-full text-muted">Loading config...</div>;

  return (
    <div className="max-w-2xl mx-auto w-full px-4 py-8">
      <h1 className="text-2xl font-bold text-foreground font-display mb-6">Sleep Agent</h1>

      {error && <p className="text-red-400 text-sm mb-4">{error}</p>}

      <div className="space-y-6">
        {/* Enable/disable */}
        <div className="bg-surface border border-border rounded-lg p-4">
          <label className="flex items-center gap-3 cursor-pointer">
            <input
              type="checkbox"
              checked={config.enabled}
              onChange={(e) => setConfig({ ...config, enabled: e.target.checked })}
              className="accent-brand w-4 h-4"
            />
            <div>
              <div className="text-sm text-foreground font-medium">Enabled</div>
              <div className="text-xs text-muted">Run curation automatically on schedule</div>
            </div>
          </label>
        </div>

        {/* Interval */}
        <div className="bg-surface border border-border rounded-lg p-4">
          <label className="text-sm text-foreground font-medium block mb-2">Curation interval</label>
          <div className="flex items-center gap-2">
            <input
              type="number"
              value={config.interval_minutes}
              onChange={(e) => setConfig({ ...config, interval_minutes: parseInt(e.target.value) || 60 })}
              min={5}
              max={1440}
              className="w-24 bg-raised border border-border rounded px-3 py-1.5 text-sm text-foreground"
            />
            <span className="text-sm text-muted">minutes</span>
          </div>
        </div>

        {/* Curation sources */}
        <div className="bg-surface border border-border rounded-lg p-4">
          <div className="text-sm text-foreground font-medium mb-2">Curation sources</div>
          <div className="text-xs text-muted mb-3">What the sleep agent reads and curates into pattern cards</div>
          <div className="flex flex-wrap gap-2">
            {ALL_SOURCES.map((src) => (
              <button
                key={src}
                onClick={() => toggleSource(src)}
                className={`text-xs px-3 py-1.5 rounded transition-colors ${
                  config.curation_sources.includes(src)
                    ? "bg-brand/15 text-brand font-medium"
                    : "bg-raised text-muted hover:text-foreground"
                }`}
              >
                {src}
              </button>
            ))}
          </div>
        </div>

        {/* Workspace scope */}
        <div className="bg-surface border border-border rounded-lg p-4">
          <div className="text-sm text-foreground font-medium mb-2">Workspace scope</div>
          <div className="text-xs text-muted mb-3">Which workspaces to curate (in addition to personal resources)</div>
          {workspaces.length === 0 ? (
            <p className="text-xs text-muted">Not a member of any workspaces</p>
          ) : (
            <div className="space-y-1.5">
              {workspaces.map((ws) => (
                <label key={ws.id} className="flex items-center gap-2 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={config.workspace_ids.includes(ws.id)}
                    onChange={() => toggleWorkspace(ws.id)}
                    className="accent-brand"
                  />
                  <span className="text-sm text-foreground">{ws.name}</span>
                </label>
              ))}
            </div>
          )}
        </div>

        {/* Model */}
        <div className="bg-surface border border-border rounded-lg p-4">
          <label className="text-sm text-foreground font-medium block mb-2">Curation model</label>
          <input
            value={config.curation_model}
            onChange={(e) => setConfig({ ...config, curation_model: e.target.value })}
            className="w-full bg-raised border border-border rounded px-3 py-1.5 text-sm text-foreground font-mono"
          />
        </div>

        {/* Actions */}
        <div className="flex items-center gap-3">
          <button
            onClick={handleSave}
            disabled={saving}
            className="bg-brand hover:bg-brand-hover text-foreground px-4 py-2 rounded text-sm disabled:opacity-50"
          >
            {saving ? "Saving..." : "Save Configuration"}
          </button>
          <button
            onClick={handleTrigger}
            className="bg-raised hover:bg-border text-foreground px-4 py-2 rounded text-sm"
          >
            Run Now
          </button>
          {triggerResult && <span className="text-xs text-brand">{triggerResult}</span>}
        </div>
      </div>
    </div>
  );
}

function InlineSleepConfig({ personaId, personaWorkspaces }: { personaId: string; personaWorkspaces: { workspace_id: string; workspace_name: string }[] }) {
  const [config, setConfig] = useState<SleepConfig | null>(null);
  const [saving, setSaving] = useState(false);
  const [triggerResult, setTriggerResult] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    getPersonaSleepConfig(personaId).then(setConfig).catch(() => {});
  }, [personaId]);

  const handleSave = async () => {
    if (!config) return;
    setSaving(true);
    setError("");
    try {
      const updated = await updatePersonaSleepConfig(personaId, {
        enabled: config.enabled,
        interval_minutes: config.interval_minutes,
        curation_sources: config.curation_sources,
        workspace_ids: config.workspace_ids,
        curation_model: config.curation_model,
      });
      setConfig(updated);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save");
    }
    setSaving(false);
  };

  const handleTrigger = async () => {
    setTriggerResult("Running...");
    try {
      const res = await triggerPersonaSleep(personaId);
      setTriggerResult(`${res.status || "done"}, ${res.total_items_curated || res.episodes_processed || 0} items`);
    } catch (err) {
      setTriggerResult(err instanceof Error ? err.message : "Failed");
    }
  };

  const toggleSource = (src: string) => {
    if (!config) return;
    const sources = new Set(config.curation_sources);
    if (sources.has(src)) sources.delete(src); else sources.add(src);
    setConfig({ ...config, curation_sources: Array.from(sources) });
  };

  const toggleWorkspace = (wsId: string) => {
    if (!config) return;
    const ids = new Set(config.workspace_ids);
    if (ids.has(wsId)) ids.delete(wsId); else ids.add(wsId);
    setConfig({ ...config, workspace_ids: Array.from(ids) });
  };

  if (!config) return <div className="text-xs text-muted py-2">Loading config...</div>;

  return (
    <div className="space-y-3 pt-2">
      {error && <p className="text-red-400 text-xs">{error}</p>}

      <div className="flex items-center gap-4 flex-wrap">
        <label className="flex items-center gap-1.5 text-xs cursor-pointer">
          <input type="checkbox" checked={config.enabled} onChange={(e) => setConfig({ ...config, enabled: e.target.checked })} className="accent-brand" />
          Enabled
        </label>
        <div className="flex items-center gap-1.5 text-xs">
          <span className="text-muted">Every</span>
          <input type="number" value={config.interval_minutes} onChange={(e) => setConfig({ ...config, interval_minutes: parseInt(e.target.value) || 60 })} min={5} max={1440} className="w-14 bg-raised border border-border rounded px-1.5 py-0.5 text-xs text-foreground" />
          <span className="text-muted">min</span>
        </div>
      </div>

      <div className="flex items-center gap-1.5 flex-wrap">
        <span className="text-xs text-muted">Sources:</span>
        {(["history", "notebooks", "documents", "tables"] as const).map((src) => (
          <button key={src} onClick={() => toggleSource(src)} className={`text-[11px] px-2 py-0.5 rounded ${config.curation_sources.includes(src) ? "bg-brand/15 text-brand" : "bg-raised text-muted"}`}>
            {src}
          </button>
        ))}
      </div>

      {personaWorkspaces.length > 0 && (
        <div className="flex items-center gap-1.5 flex-wrap">
          <span className="text-xs text-muted">Workspaces:</span>
          {personaWorkspaces.map((ws) => (
            <label key={ws.workspace_id} className="flex items-center gap-1 text-xs cursor-pointer">
              <input type="checkbox" checked={config.workspace_ids.includes(ws.workspace_id)} onChange={() => toggleWorkspace(ws.workspace_id)} className="accent-brand" />
              {ws.workspace_name}
            </label>
          ))}
        </div>
      )}

      <div className="flex items-center gap-1.5">
        <span className="text-xs text-muted">Model:</span>
        <input value={config.curation_model} onChange={(e) => setConfig({ ...config, curation_model: e.target.value })} className="flex-1 bg-raised border border-border rounded px-2 py-0.5 text-xs text-foreground font-mono max-w-[280px]" />
      </div>

      <div className="flex items-center gap-2">
        <button onClick={handleSave} disabled={saving} className="text-xs bg-brand hover:bg-brand-hover text-foreground px-2.5 py-1 rounded disabled:opacity-50">
          {saving ? "Saving..." : "Save"}
        </button>
        <button onClick={handleTrigger} className="text-xs bg-raised hover:bg-border text-foreground px-2.5 py-1 rounded">
          Run Now
        </button>
        {triggerResult && <span className="text-xs text-brand">{triggerResult}</span>}
      </div>
    </div>
  );
}

export default function PersonasPage() {
  const router = useRouter();
  const { user, loading, logout } = useAuth();
  const [personas, setPersonas] = useState<PersonaWithContext[]>([]);
  const [showCreate, setShowCreate] = useState(false);
  const [newName, setNewName] = useState("");
  const [newDisplayName, setNewDisplayName] = useState("");
  const [newDescription, setNewDescription] = useState("");
  const [error, setError] = useState("");
  const [newApiKey, setNewApiKey] = useState<string | null>(null);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editDisplayName, setEditDisplayName] = useState("");
  const [editDescription, setEditDescription] = useState("");
  const [sleepExpandedId, setSleepExpandedId] = useState<string | null>(null);

  const loadPersonas = useCallback(async () => {
    try {
      const res = await listPersonasWithContext();
      setPersonas(res?.personas ?? []);
    } catch { /* ignore */ }
  }, []);

  useEffect(() => {
    if (user && user.type === "human") loadPersonas();
  }, [user, loadPersonas]);

  const handleCreate = async () => {
    if (!newName.trim()) return;
    setError("");
    try {
      const persona = await createPersona(newName.trim(), newDisplayName.trim() || undefined, newDescription.trim() || undefined);
      setNewApiKey(persona.api_key);
      setShowCreate(false);
      setNewName("");
      setNewDisplayName("");
      setNewDescription("");
      await loadPersonas();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create persona");
    }
  };

  const handleRotateKey = async (personaId: string) => {
    if (!confirm("Rotate this persona's API key? The old key will stop working immediately.")) return;
    try {
      const result = await rotatePersonaKey(personaId);
      setNewApiKey(result.api_key);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to rotate key");
    }
  };

  const handleDelete = async (personaId: string) => {
    if (!confirm("Delete this persona? This cannot be undone.")) return;
    try {
      await deletePersona(personaId);
      await loadPersonas();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to delete persona");
    }
  };

  const startEdit = (persona: PersonaWithContext) => {
    setEditingId(persona.id);
    setEditDisplayName(persona.display_name || "");
    setEditDescription(persona.description || "");
  };

  const handleSaveEdit = async () => {
    if (!editingId) return;
    try {
      await updatePersona(editingId, { display_name: editDisplayName || undefined, description: editDescription || undefined });
      setEditingId(null);
      await loadPersonas();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to update persona");
    }
  };

  if (loading) {
    return <div className="min-h-screen flex items-center justify-center text-muted">Loading...</div>;
  }
  if (!user) { router.push("/login"); return null; }

  if (user.type !== "human") {
    return (
      <AppShell user={user} onLogout={logout}>
        <SleepAgentConfig />
      </AppShell>
    );
  }

  return (
    <AppShell user={user} onLogout={logout}>
      <div className="max-w-3xl mx-auto w-full px-4 py-8">
        <div className="flex items-center justify-between mb-6">
          <h1 className="text-2xl font-bold text-foreground font-display">Personas</h1>
          <button onClick={() => { setShowCreate(true); setNewApiKey(null); }} className="text-sm bg-brand hover:bg-brand-hover text-foreground px-3 py-1.5 rounded">
            Create Persona
          </button>
        </div>

        {error && <p className="text-red-400 text-sm mb-4">{error}</p>}

        {newApiKey && (
          <div className="bg-green-900/20 border border-green-800 rounded-lg p-4 mb-6">
            <div className="text-green-400 text-sm font-medium mb-1">API Key (copy now — shown only once)</div>
            <code className="text-green-300 text-xs font-mono bg-green-900/30 px-2 py-1 rounded block break-all select-all">{newApiKey}</code>
            <button onClick={() => setNewApiKey(null)} className="text-xs text-green-500 hover:text-green-400 mt-2">Dismiss</button>
          </div>
        )}

        {showCreate && (
          <div className="bg-surface border border-border rounded-lg p-4 mb-6">
            <h3 className="text-foreground font-medium mb-3">New Persona</h3>
            <input value={newName} onChange={(e) => setNewName(e.target.value)} placeholder="Username (a-z, 0-9, -, _)" className="w-full bg-raised border border-border rounded px-3 py-2 text-foreground text-sm mb-2 font-mono" />
            <input value={newDisplayName} onChange={(e) => setNewDisplayName(e.target.value)} placeholder="Display name (optional)" className="w-full bg-raised border border-border rounded px-3 py-2 text-foreground text-sm mb-2" />
            <input value={newDescription} onChange={(e) => setNewDescription(e.target.value)} placeholder="Description (optional)" className="w-full bg-raised border border-border rounded px-3 py-2 text-foreground text-sm mb-2" />
            <div className="flex gap-2">
              <button onClick={handleCreate} className="bg-brand hover:bg-brand-hover text-foreground px-4 py-1.5 rounded text-sm">Create</button>
              <button onClick={() => setShowCreate(false)} className="bg-raised text-dim px-4 py-1.5 rounded text-sm">Cancel</button>
            </div>
          </div>
        )}

        {personas.length === 0 && !showCreate ? (
          <p className="text-muted text-sm">No personas yet. Create one to get started.</p>
        ) : (
          <div className="space-y-3">
            {personas.map((persona) => (
              <div key={persona.id} className="bg-surface border border-border rounded-lg p-4">
                {editingId === persona.id ? (
                  <div className="space-y-2">
                    <input value={editDisplayName} onChange={(e) => setEditDisplayName(e.target.value)} placeholder="Display name" className="w-full bg-raised border border-border rounded px-3 py-1.5 text-foreground text-sm" />
                    <input value={editDescription} onChange={(e) => setEditDescription(e.target.value)} placeholder="Description" className="w-full bg-raised border border-border rounded px-3 py-1.5 text-foreground text-sm" />
                    <div className="flex gap-2">
                      <button onClick={handleSaveEdit} className="text-xs bg-brand hover:bg-brand-hover text-foreground px-3 py-1 rounded">Save</button>
                      <button onClick={() => setEditingId(null)} className="text-xs text-dim hover:text-foreground px-3 py-1">Cancel</button>
                    </div>
                  </div>
                ) : (
                  <>
                    <div className="flex items-start justify-between mb-3">
                      <div>
                        <div className="flex items-center gap-2">
                          <span className="text-foreground font-medium">{persona.display_name || persona.name}</span>
                          <span className="text-[10px] uppercase font-mono px-1.5 py-0.5 rounded bg-agent-muted text-agent">persona</span>
                        </div>
                        <div className="text-xs text-muted font-mono mt-0.5">@{persona.name}</div>
                        {persona.description && <div className="text-sm text-dim mt-1">{persona.description}</div>}
                      </div>
                      <div className="flex gap-1 flex-shrink-0">
                        <button onClick={() => startEdit(persona)} className="text-xs text-dim hover:text-foreground px-2 py-1">Edit</button>
                        <button onClick={() => handleRotateKey(persona.id)} className="text-xs text-brand hover:text-brand-hover px-2 py-1">Rotate Key</button>
                        <button onClick={() => handleDelete(persona.id)} className="text-xs text-red-400 hover:text-red-300 px-2 py-1">Delete</button>
                      </div>
                    </div>

                    {/* Workspace memberships */}
                    {persona.workspaces && persona.workspaces.length > 0 ? (
                      <div className="border-t border-border pt-2 mt-2">
                        <div className="text-[10px] text-muted uppercase tracking-wider mb-1">Workspaces</div>
                        <div className="flex flex-wrap gap-1.5">
                          {persona.workspaces.map((ws) => (
                            <a
                              key={ws.workspace_id}
                              href={`/workspaces/${ws.workspace_id}`}
                              className="text-xs bg-raised text-dim px-2 py-1 rounded hover:text-foreground transition-colors"
                            >
                              {ws.workspace_name} <span className="text-muted">({ws.role})</span>
                            </a>
                          ))}
                        </div>
                      </div>
                    ) : (
                      <div className="border-t border-border pt-2 mt-2">
                        <div className="text-xs text-muted">Not a member of any workspaces yet</div>
                      </div>
                    )}

                    {/* Sleep Agent */}
                    <div className="border-t border-border pt-2 mt-2">
                      <button
                        onClick={() => setSleepExpandedId(sleepExpandedId === persona.id ? null : persona.id)}
                        className="text-[10px] text-muted uppercase tracking-wider hover:text-foreground transition-colors"
                      >
                        {sleepExpandedId === persona.id ? "▾" : "▸"} Sleep Agent
                      </button>
                      {sleepExpandedId === persona.id && (
                        <InlineSleepConfig
                          personaId={persona.id}
                          personaWorkspaces={persona.workspaces || []}
                        />
                      )}
                    </div>

                    <div className="text-xs text-muted mt-2">
                      Last seen: {new Date(persona.last_seen).toLocaleString()}
                    </div>
                  </>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </AppShell>
  );
}
