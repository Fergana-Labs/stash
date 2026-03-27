"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import Header from "../../../components/Header";
import NotebookTreeComponent from "../../../components/workspace/FileTree";
import MarkdownEditor from "../../../components/workspace/MarkdownEditor";
import WorkspaceSidebar from "../../../components/workspace/WorkspaceSidebar";
import { useAuth } from "../../../hooks/useAuth";
import {
  createNotebook,
  createNotebookFolder,
  deleteNotebook,
  deleteNotebookFolder,
  getWorkspace,
  getNotebook,
  listNotebooks,
  renameNotebookFolder,
  updateNotebook,
  joinWorkspace as apiJoinRoom,
  getWorkspaceMembers,
  leaveWorkspace,
  deleteWorkspace,
  kickWorkspaceMember,
  updateWorkspace,
  
  
  
} from "../../../lib/api";
import { NotebookTree, Workspace, WorkspaceMember, Notebook } from "../../../lib/types";

export default function WorkspacePage() {
  const params = useParams();
  const router = useRouter();
  const workspaceId = params.workspaceId as string;
  const { user, loading, logout } = useAuth();

  const [workspace, setWorkspace] = useState<Workspace | null>(null);
  const [tree, setTree] = useState<NotebookTree>({ folders: [], root_files: [] });
  const [selectedFileId, setSelectedFileId] = useState<string | null>(null);
  const [selectedFile, setSelectedFile] = useState<Notebook | null>(null);
  const [members, setMembers] = useState<WorkspaceMember[]>([]);
  const [isMember, setIsMember] = useState(false);
  const [error, setError] = useState("");
  const [sidebarWidth] = useState(260);
  const [showManageSidebar, setShowManageSidebar] = useState(false);

  const loadWorkspace = useCallback(async () => {
    try {
      const room = await getWorkspace(workspaceId);
      setWorkspace(room);
    } catch {
      setError("Workspace not found");
    }
  }, [workspaceId]);

  const loadTree = useCallback(async () => {
    try {
      const t = await listNotebooks(workspaceId);
      setTree(t);
    } catch {
      // Not a member yet
    }
  }, [workspaceId]);

  const loadMembers = useCallback(async () => {
    try {
      const m = await getWorkspaceMembers(workspaceId);
      setMembers(m);
      if (user) {
        setIsMember(m.some((member) => member.user_id === user.id));
      }
    } catch {
      setIsMember(false);
    }
  }, [workspaceId, user]);

  useEffect(() => {
    loadWorkspace();
  }, [loadWorkspace]);

  useEffect(() => {
    if (user) {
      loadTree();
      loadMembers();
    }
  }, [user, loadTree, loadMembers]);

  const handleSelectFile = useCallback(
    async (fileId: string) => {
      setSelectedFileId(fileId);
      try {
        const f = await getNotebook(workspaceId, fileId);
        setSelectedFile(f);
      } catch {
        setError("Failed to load file");
      }
    },
    [workspaceId]
  );

  const handleCreateFile = useCallback(
    async (folderId: string | null) => {
      const name = prompt("File name:");
      if (!name) return;
      try {
        const f = await createNotebook(workspaceId, name, folderId || undefined);
        await loadTree();
        setSelectedFileId(f.id);
        setSelectedFile(f);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to create file");
      }
    },
    [workspaceId, loadTree]
  );

  const handleCreateFolder = useCallback(async () => {
    const name = prompt("Folder name:");
    if (!name) return;
    try {
      await createNotebookFolder(workspaceId, name);
      await loadTree();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create folder");
    }
  }, [workspaceId, loadTree]);

  const handleDeleteFile = useCallback(
    async (fileId: string) => {
      if (!confirm("Delete this file?")) return;
      try {
        await deleteNotebook(workspaceId, fileId);
        if (selectedFileId === fileId) {
          setSelectedFileId(null);
          setSelectedFile(null);
        }
        await loadTree();
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to delete file");
      }
    },
    [workspaceId, selectedFileId, loadTree]
  );

  const handleDeleteFolder = useCallback(
    async (folderId: string) => {
      if (!confirm("Delete this folder and all its files?")) return;
      try {
        await deleteNotebookFolder(workspaceId, folderId);
        setSelectedFileId(null);
        setSelectedFile(null);
        await loadTree();
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to delete folder");
      }
    },
    [workspaceId, loadTree]
  );

  const handleRenameFile = useCallback(
    async (fileId: string, currentName: string) => {
      const name = prompt("New name:", currentName);
      if (!name || name === currentName) return;
      try {
        const updated = await updateNotebook(workspaceId, fileId, { name });
        if (selectedFileId === fileId) {
          setSelectedFile(updated);
        }
        await loadTree();
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to rename file");
      }
    },
    [workspaceId, selectedFileId, loadTree]
  );

  const handleMoveFile = useCallback(
    async (fileId: string, folderId: string | null) => {
      try {
        const data = folderId ? { folder_id: folderId } : { move_to_root: true };
        const updated = await updateNotebook(workspaceId, fileId, data);
        if (selectedFileId === fileId) {
          setSelectedFile(updated);
        }
        await loadTree();
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to move file");
      }
    },
    [workspaceId, selectedFileId, loadTree]
  );

  const handleRenameFolder = useCallback(
    async (folderId: string, currentName: string) => {
      const name = prompt("New name:", currentName);
      if (!name || name === currentName) return;
      try {
        await renameNotebookFolder(workspaceId, folderId, name);
        await loadTree();
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to rename folder");
      }
    },
    [workspaceId, loadTree]
  );

  const handleSaveFile = useCallback(
    async (content: string) => {
      if (!selectedFileId) return;
      try {
        const updated = await updateNotebook(workspaceId, selectedFileId, { content });
        setSelectedFile(updated);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to save file");
      }
    },
    [workspaceId, selectedFileId]
  );

  const handleJoin = async () => {
    if (!workspace) return;
    try {
      await apiJoinRoom(workspace.invite_code);
      await loadMembers();
      await loadTree();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to join workspace");
    }
  };

  const handleLeave = async () => {
    if (!confirm("Leave this workspace?")) return;
    try {
      await leaveWorkspace(workspaceId);
      router.push("/rooms");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to leave workspace");
    }
  };

  const handleDeleteWorkspace = async () => {
    try {
      await deleteWorkspace(workspaceId);
      router.push("/rooms");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to delete workspace");
    }
  };

  const handleKickMember = async (userId: string) => {
    try {
      await kickWorkspaceMember(workspaceId, userId);
      await loadMembers();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to kick member");
    }
  };

  const handleUpdateWorkspace = async (data: { name?: string; description?: string }) => {
    try {
      const updated = await updateWorkspace(workspaceId, data);
      setWorkspace(updated);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to update workspace");
    }
  };

  const handleAddToAccessList = async (userName: string, listType: "allow" | "block") => {
    // TODO: migrate to permissions API // await addToAccessList(workspaceId, userName, listType);
  };

  const handleRemoveFromAccessList = async (userName: string, listType: "allow" | "block") => {
    // TODO: migrate to permissions API
  };

  const handleGetAccessList = async (listType: "allow" | "block"): Promise<any[]> => {
    // TODO: migrate to permissions API
    return [];
  };

  const isOwner = members.some(
    (m) => m.user_id === user?.id && m.role === "owner"
  );

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center text-muted">
        Loading...
      </div>
    );
  }

  if (!user) {
    router.push("/login");
    return null;
  }

  return (
    <div className="h-screen flex flex-col">
      <Header user={user} onLogout={logout} />

      {/* Workspace header bar */}
      <div className="bg-surface border-b border-border px-4 py-2 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Link href="/rooms" className="text-dim hover:text-foreground text-sm">
            &larr; Workspaces
          </Link>
          <h1 className="text-foreground font-medium">{workspace?.name || "Loading..."}</h1>
          {workspace?.description && (
            <span className="text-muted text-sm hidden sm:inline">
              {workspace.description}
            </span>
          )}
        </div>
        <div className="flex items-center gap-3">
          <span className="text-xs text-muted">
            {members.length} member{members.length !== 1 ? "s" : ""}
          </span>
          {isMember && (
            <button
              onClick={() => setShowManageSidebar(!showManageSidebar)}
              className={`text-xs px-3 py-1 rounded border ${
                showManageSidebar
                  ? "bg-brand border-brand text-foreground"
                  : "bg-raised border-border text-dim hover:text-foreground hover:border-brand"
              }`}
            >
              Settings
            </button>
          )}
        </div>
      </div>

      {error && (
        <div className="bg-red-900/30 border-b border-red-800 text-red-400 text-sm px-4 py-2">
          {error}
          <button onClick={() => setError("")} className="ml-2 text-red-500 hover:text-red-300">&times;</button>
        </div>
      )}

      {!isMember ? (
        <div className="flex-1 flex items-center justify-center">
          <div className="text-center">
            <p className="text-dim mb-4">You&apos;re not a member of this workspace.</p>
            <button
              onClick={handleJoin}
              className="bg-brand hover:bg-brand-hover text-foreground px-6 py-2 rounded"
            >
              Join Workspace
            </button>
          </div>
        </div>
      ) : (
        <div className="flex-1 flex overflow-hidden">
          {/* File tree sidebar */}
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

          {/* Editor area */}
          <div className="flex-1 flex flex-col overflow-hidden">
            {selectedFile ? (
              <MarkdownEditor
                key={selectedFile.id}
                workspaceId={workspaceId}
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

          {/* Management sidebar */}
          {showManageSidebar && workspace && user && (
            <WorkspaceSidebar
              workspace={workspace}
              members={members}
              currentUserId={user.id}
              isOwner={isOwner}
              onLeave={handleLeave}
              onDelete={handleDeleteWorkspace}
              onKickMember={handleKickMember}
              onUpdateWorkspace={handleUpdateWorkspace}
              onAddToAccessList={isOwner ? handleAddToAccessList : undefined}
              onRemoveFromAccessList={isOwner ? handleRemoveFromAccessList : undefined}
              onGetAccessList={isOwner ? handleGetAccessList : undefined}
            />
          )}
        </div>
      )}
    </div>
  );
}
