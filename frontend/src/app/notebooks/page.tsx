"use client";

import { useCallback, useEffect, useState } from "react";
import AppShell from "../../components/AppShell";
import NotebookTreeComponent from "../../components/workspace/FileTree";
import MarkdownEditor from "../../components/workspace/MarkdownEditor";
import { useAuth } from "../../hooks/useAuth";
import {
  createPersonalNotebook,
  createPersonalNotebookFolder,
  deletePersonalNotebook,
  deletePersonalNotebookFolder,
  getPersonalNotebook,
  listPersonalNotebooks,
  renamePersonalNotebookFolder,
  updatePersonalNotebook,
} from "../../lib/api";
import { Notebook, NotebookTree } from "../../lib/types";
import { useRouter } from "next/navigation";

export default function PersonalNotebooksPage() {
  const router = useRouter();
  const { user, loading, logout } = useAuth();
  const [tree, setTree] = useState<NotebookTree>({ folders: [], root_files: [] });
  const [selectedFileId, setSelectedFileId] = useState<string | null>(null);
  const [selectedFile, setSelectedFile] = useState<Notebook | null>(null);
  const [error, setError] = useState("");
  const [sidebarWidth] = useState(260);

  const loadTree = useCallback(async () => {
    try {
      const t = await listPersonalNotebooks();
      setTree(t);
    } catch {
      // ignore
    }
  }, []);

  useEffect(() => {
    if (user) loadTree();
  }, [user, loadTree]);

  const handleSelectFile = useCallback(async (fileId: string) => {
    setSelectedFileId(fileId);
    try {
      const f = await getPersonalNotebook(fileId);
      setSelectedFile(f);
    } catch {
      setError("Failed to load file");
    }
  }, []);

  const handleCreateFile = useCallback(
    async (folderId: string | null) => {
      const name = prompt("File name:");
      if (!name) return;
      try {
        const f = await createPersonalNotebook(name, folderId || undefined);
        await loadTree();
        setSelectedFileId(f.id);
        setSelectedFile(f);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to create file");
      }
    },
    [loadTree]
  );

  const handleCreateFolder = useCallback(async () => {
    const name = prompt("Folder name:");
    if (!name) return;
    try {
      await createPersonalNotebookFolder(name);
      await loadTree();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create folder");
    }
  }, [loadTree]);

  const handleDeleteFile = useCallback(
    async (fileId: string) => {
      if (!confirm("Delete this file?")) return;
      try {
        await deletePersonalNotebook(fileId);
        if (selectedFileId === fileId) {
          setSelectedFileId(null);
          setSelectedFile(null);
        }
        await loadTree();
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to delete file");
      }
    },
    [selectedFileId, loadTree]
  );

  const handleDeleteFolder = useCallback(
    async (folderId: string) => {
      if (!confirm("Delete this folder and all its files?")) return;
      try {
        await deletePersonalNotebookFolder(folderId);
        setSelectedFileId(null);
        setSelectedFile(null);
        await loadTree();
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to delete folder");
      }
    },
    [loadTree]
  );

  const handleRenameFile = useCallback(
    async (fileId: string, currentName: string) => {
      const name = prompt("New name:", currentName);
      if (!name || name === currentName) return;
      try {
        const updated = await updatePersonalNotebook(fileId, { name });
        if (selectedFileId === fileId) setSelectedFile(updated);
        await loadTree();
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to rename file");
      }
    },
    [selectedFileId, loadTree]
  );

  const handleMoveFile = useCallback(
    async (fileId: string, folderId: string | null) => {
      try {
        const data = folderId ? { folder_id: folderId } : { move_to_root: true };
        const updated = await updatePersonalNotebook(fileId, data);
        if (selectedFileId === fileId) setSelectedFile(updated);
        await loadTree();
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to move file");
      }
    },
    [selectedFileId, loadTree]
  );

  const handleRenameFolder = useCallback(
    async (folderId: string, currentName: string) => {
      const name = prompt("New name:", currentName);
      if (!name || name === currentName) return;
      try {
        await renamePersonalNotebookFolder(folderId, name);
        await loadTree();
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to rename folder");
      }
    },
    [loadTree]
  );

  const handleSaveFile = useCallback(
    async (content: string) => {
      if (!selectedFileId) return;
      try {
        const updated = await updatePersonalNotebook(selectedFileId, { content });
        setSelectedFile(updated);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to save file");
      }
    },
    [selectedFileId]
  );

  if (loading) {
    return <div className="min-h-screen flex items-center justify-center text-muted">Loading...</div>;
  }
  if (!user) { router.push("/login"); return null; }

  return (
    <AppShell user={user} onLogout={logout}>
      <div className="flex flex-col h-full">
      {error && (
        <div className="bg-red-900/30 border-b border-red-800 text-red-400 text-sm px-4 py-2">
          {error}
          <button onClick={() => setError("")} className="ml-2 text-red-500 hover:text-red-300">&times;</button>
        </div>
      )}
      <div className="flex-1 flex overflow-hidden">
        <div
          className="bg-surface border-r border-border flex-shrink-0 overflow-hidden"
          style={{ width: sidebarWidth }}
        >
          <NotebookTreeComponent
            tree={tree}
            selectedFileId={selectedFileId}
            onSelectFile={handleSelectFile}
            onCreateFile={handleCreateFile}
            onCreateFolder={handleCreateFolder}
            onDeleteFile={handleDeleteFile}
            onDeleteFolder={handleDeleteFolder}
            onRenameFile={handleRenameFile}
            onRenameFolder={handleRenameFolder}
            onMoveFile={handleMoveFile}
          />
        </div>
        <div className="flex-1 flex flex-col overflow-hidden">
          {selectedFile ? (
            <MarkdownEditor
              key={selectedFile.id}
              workspaceId={null}
              file={selectedFile}
              onSave={handleSaveFile}
            />
          ) : (
            <div className="flex-1 flex items-center justify-center text-muted">
              <div className="text-center">
                <p className="text-lg mb-2">Select a file to edit</p>
                <p className="text-sm">or create a new one from the sidebar</p>
              </div>
            </div>
          )}
        </div>
      </div>
      </div>
    </AppShell>
  );
}
