"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import Header from "../../../components/Header";
import FileTreeComponent from "../../../components/workspace/FileTree";
import MarkdownEditor from "../../../components/workspace/MarkdownEditor";
import { useAuth } from "../../../hooks/useAuth";
import {
  createWorkspaceFile,
  createWorkspaceFolder,
  deleteWorkspaceFile,
  deleteWorkspaceFolder,
  getRoom,
  getWorkspaceFile,
  listWorkspaceFiles,
  renameWorkspaceFolder,
  updateWorkspaceFile,
  joinRoom as apiJoinRoom,
  getRoomMembers,
} from "../../../lib/api";
import { FileTree, Room, RoomMember, WorkspaceFile } from "../../../lib/types";

export default function WorkspacePage() {
  const params = useParams();
  const router = useRouter();
  const workspaceId = params.workspaceId as string;
  const { user, loading, logout } = useAuth();

  const [workspace, setWorkspace] = useState<Room | null>(null);
  const [tree, setTree] = useState<FileTree>({ folders: [], root_files: [] });
  const [selectedFileId, setSelectedFileId] = useState<string | null>(null);
  const [selectedFile, setSelectedFile] = useState<WorkspaceFile | null>(null);
  const [members, setMembers] = useState<RoomMember[]>([]);
  const [isMember, setIsMember] = useState(false);
  const [error, setError] = useState("");
  const [sidebarWidth] = useState(260);

  const loadWorkspace = useCallback(async () => {
    try {
      const room = await getRoom(workspaceId);
      setWorkspace(room);
    } catch {
      setError("Workspace not found");
    }
  }, [workspaceId]);

  const loadTree = useCallback(async () => {
    try {
      const t = await listWorkspaceFiles(workspaceId);
      setTree(t);
    } catch {
      // Not a member yet
    }
  }, [workspaceId]);

  const loadMembers = useCallback(async () => {
    try {
      const m = await getRoomMembers(workspaceId);
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
        const f = await getWorkspaceFile(workspaceId, fileId);
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
        const f = await createWorkspaceFile(workspaceId, name, folderId || undefined);
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
      await createWorkspaceFolder(workspaceId, name);
      await loadTree();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create folder");
    }
  }, [workspaceId, loadTree]);

  const handleDeleteFile = useCallback(
    async (fileId: string) => {
      if (!confirm("Delete this file?")) return;
      try {
        await deleteWorkspaceFile(workspaceId, fileId);
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
        await deleteWorkspaceFolder(workspaceId, folderId);
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
        const updated = await updateWorkspaceFile(workspaceId, fileId, { name });
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
        const updated = await updateWorkspaceFile(workspaceId, fileId, data);
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
        await renameWorkspaceFolder(workspaceId, folderId, name);
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
        const updated = await updateWorkspaceFile(workspaceId, selectedFileId, { content });
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

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center text-gray-500">
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
      <div className="bg-gray-900 border-b border-gray-800 px-4 py-2 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Link href="/rooms" className="text-gray-400 hover:text-white text-sm">
            &larr; Spaces
          </Link>
          <h1 className="text-white font-medium">{workspace?.name || "Loading..."}</h1>
          {workspace?.description && (
            <span className="text-gray-500 text-sm hidden sm:inline">
              {workspace.description}
            </span>
          )}
        </div>
        <div className="flex items-center gap-3">
          <span className="text-xs text-gray-500">
            {members.length} member{members.length !== 1 ? "s" : ""}
          </span>
          {workspace && (
            <span className="text-xs text-gray-600">
              Code: {workspace.invite_code}
            </span>
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
            <p className="text-gray-400 mb-4">You&apos;re not a member of this workspace.</p>
            <button
              onClick={handleJoin}
              className="bg-purple-600 hover:bg-purple-500 text-white px-6 py-2 rounded"
            >
              Join Workspace
            </button>
          </div>
        </div>
      ) : (
        <div className="flex-1 flex overflow-hidden">
          {/* File tree sidebar */}
          <div
            className="bg-gray-900 border-r border-gray-800 flex-shrink-0 overflow-hidden"
            style={{ width: sidebarWidth }}
          >
            <FileTreeComponent
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
              <div className="flex-1 flex items-center justify-center text-gray-500">
                <div className="text-center">
                  <p className="text-lg mb-2">Select a file to edit</p>
                  <p className="text-sm">or create a new one from the sidebar</p>
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
