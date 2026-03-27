"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import AppShell from "../../components/AppShell";
import MarkdownEditor from "../../components/workspace/MarkdownEditor";
import { useAuth } from "../../hooks/useAuth";
import {
  listAllNotebooks,
  getNotebook,
  getPersonalNotebook,
  updateNotebook,
  updatePersonalNotebook,
  createPersonalNotebook,
  createNotebook,
} from "../../lib/api";
import { Notebook, NotebookWithWorkspace } from "../../lib/types";

export default function NotebooksPage() {
  const router = useRouter();
  const { user, loading, logout } = useAuth();
  const [notebooks, setNotebooks] = useState<NotebookWithWorkspace[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [selectedFile, setSelectedFile] = useState<Notebook | null>(null);
  const [error, setError] = useState("");

  const loadNotebooks = useCallback(async () => {
    try {
      const res = await listAllNotebooks();
      setNotebooks(res?.notebooks ?? []);
    } catch {
      // ignore
    }
  }, []);

  useEffect(() => {
    if (user) loadNotebooks();
  }, [user, loadNotebooks]);

  // Group notebooks by workspace
  const grouped = useMemo(() => {
    const groups: Record<string, { name: string; notebooks: NotebookWithWorkspace[] }> = {};
    for (const nb of notebooks) {
      const key = nb.workspace_id || "personal";
      if (!groups[key]) {
        groups[key] = { name: nb.workspace_name || "Personal", notebooks: [] };
      }
      groups[key].notebooks.push(nb);
    }
    return groups;
  }, [notebooks]);

  const handleSelect = useCallback(async (nb: NotebookWithWorkspace) => {
    setSelectedId(nb.id);
    try {
      let file: Notebook;
      if (nb.workspace_id) {
        file = await getNotebook(nb.workspace_id, nb.id);
      } else {
        file = await getPersonalNotebook(nb.id);
      }
      setSelectedFile(file);
    } catch {
      setError("Failed to load notebook");
    }
  }, []);

  const handleCreate = async () => {
    const name = prompt("Notebook name:");
    if (!name) return;
    try {
      const nb = await createPersonalNotebook(name);
      await loadNotebooks();
      setSelectedId(nb.id);
      setSelectedFile(nb);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create notebook");
    }
  };

  const handleSave = useCallback(async (content: string) => {
    if (!selectedFile) return;
    try {
      if (selectedFile.workspace_id) {
        await updateNotebook(selectedFile.workspace_id, selectedFile.id, { content });
      } else {
        await updatePersonalNotebook(selectedFile.id, { content });
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save");
    }
  }, [selectedFile]);

  if (loading) {
    return <div className="min-h-screen flex items-center justify-center text-muted">Loading...</div>;
  }
  if (!user) { router.push("/login"); return null; }

  return (
    <AppShell user={user} onLogout={logout}>
      <div className="flex h-full overflow-hidden">
        {/* Notebook list sidebar */}
        <div className="w-[240px] flex-shrink-0 bg-surface border-r border-border overflow-y-auto">
          <div className="px-3 py-3 flex items-center justify-between border-b border-border">
            <span className="text-xs font-medium text-muted uppercase tracking-wider">Notebooks</span>
            <button onClick={handleCreate} className="text-xs text-brand hover:text-brand-hover">+ New</button>
          </div>
          {Object.entries(grouped).map(([key, group]) => (
            <div key={key} className="px-2 py-2">
              <div className="text-[10px] font-medium text-muted uppercase tracking-wider px-2 mb-1">
                {group.name}
              </div>
              {group.notebooks.map((nb) => (
                <button
                  key={nb.id}
                  onClick={() => handleSelect(nb)}
                  className={`w-full text-left px-2 py-1.5 rounded text-sm truncate transition-colors ${
                    selectedId === nb.id
                      ? "bg-brand/10 text-brand font-medium"
                      : "text-dim hover:text-foreground hover:bg-raised"
                  }`}
                >
                  {nb.name}
                </button>
              ))}
            </div>
          ))}
          {notebooks.length === 0 && (
            <div className="px-4 py-8 text-center text-muted text-sm">
              No notebooks yet
            </div>
          )}
        </div>

        {/* Editor area */}
        <div className="flex-1 flex flex-col overflow-hidden">
          {error && (
            <div className="bg-red-900/30 border-b border-red-800 text-red-400 text-sm px-4 py-2">
              {error}
              <button onClick={() => setError("")} className="ml-2 text-red-500 hover:text-red-300">&times;</button>
            </div>
          )}
          {selectedFile ? (
            <MarkdownEditor
              key={selectedFile.id}
              workspaceId={selectedFile.workspace_id}
              file={selectedFile}
              onSave={handleSave}
            />
          ) : (
            <div className="flex-1 flex items-center justify-center text-muted">
              <div className="text-center">
                <p className="text-lg mb-2">Select a notebook to edit</p>
                <p className="text-sm">or create a new one from the sidebar</p>
              </div>
            </div>
          )}
        </div>
      </div>
    </AppShell>
  );
}
