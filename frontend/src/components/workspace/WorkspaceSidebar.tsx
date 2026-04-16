"use client";

import { useCallback, useRef, useState } from "react";

import { Workspace, WorkspaceMember } from "../../lib/types";

interface UserResult { id: string; name: string; display_name: string }

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:3456";

function AddMemberInput({ onAdd, existingMemberIds }: { onAdd: (username: string) => Promise<void>; existingMemberIds: string[] }) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<UserResult[]>([]);
  const [searching, setSearching] = useState(false);
  const [status, setStatus] = useState<{ msg: string; ok: boolean } | null>(null);
  const [adding, setAdding] = useState(false);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const search = useCallback(async (q: string) => {
    if (q.length < 1) { setResults([]); return; }
    setSearching(true);
    try {
      const token = localStorage.getItem("stash_token") || "";
      const res = await fetch(`${API_BASE}/api/v1/users/search?q=${encodeURIComponent(q)}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) {
        const data: UserResult[] = await res.json();
        setResults(data.filter(u => !existingMemberIds.includes(u.id)));
      }
    } catch { /* ignore */ }
    setSearching(false);
  }, [existingMemberIds]);

  const handleInput = (val: string) => {
    setQuery(val);
    setStatus(null);
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => search(val), 200);
  };

  const handleSelect = async (user: UserResult) => {
    setAdding(true);
    setStatus(null);
    try {
      await onAdd(user.name);
      setQuery("");
      setResults([]);
      setStatus({ msg: `Added ${user.display_name || user.name}`, ok: true });
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to add";
      setStatus({ msg, ok: false });
    }
    setAdding(false);
  };

  return (
    <div className="relative">
      <input
        type="text"
        value={query}
        onChange={(e) => handleInput(e.target.value)}
        placeholder="Search users to add..."
        className="w-full bg-raised border border-border rounded px-2 py-1 text-xs text-foreground focus:outline-none focus:border-brand"
        disabled={adding}
      />
      {results.length > 0 && (
        <div className="absolute left-0 right-0 top-full mt-1 bg-surface border border-border rounded-lg shadow-xl z-50 py-1 max-h-[150px] overflow-y-auto">
          {results.map((u) => (
            <button
              key={u.id}
              onClick={() => handleSelect(u)}
              className="w-full text-left px-2 py-1.5 text-xs hover:bg-raised transition-colors flex items-center gap-2"
            >
              <div className="w-5 h-5 rounded-full bg-human-muted text-human flex items-center justify-center text-[9px] font-bold flex-shrink-0">
                {(u.display_name || u.name).charAt(0).toUpperCase()}
              </div>
              <div className="min-w-0">
                <div className="text-foreground truncate">{u.display_name || u.name}</div>
                <div className="text-muted text-[10px]">@{u.name}</div>
              </div>
            </button>
          ))}
        </div>
      )}
      {searching && <p className="text-[10px] text-muted mt-1">Searching...</p>}
      {status && (
        <p className={`text-[10px] mt-1 ${status.ok ? "text-green-400" : "text-red-400"}`}>
          {status.msg}
        </p>
      )}
    </div>
  );
}

interface WorkspaceSidebarProps {
  workspace: Workspace;
  members: WorkspaceMember[];
  currentUserId: string;
  isOwner: boolean;
  onLeave: () => void;
  onDelete: () => void;
  onKickMember: (userId: string) => void;
  onUpdateWorkspace: (data: { name?: string; description?: string }) => void;
  onAddMember: (username: string) => Promise<void>;
  onAddToAccessList?: (userName: string, listType: "allow" | "block") => Promise<void>;
  onRemoveFromAccessList?: (userName: string, listType: "allow" | "block") => Promise<void>;
  onGetAccessList?: (listType: "allow" | "block") => Promise<AccessListEntry[]>;
}

interface AccessListEntry {
  user_name: string;
}

export default function WorkspaceSidebar({
  workspace,
  members,
  currentUserId,
  isOwner,
  onLeave,
  onDelete,
  onKickMember,
  onUpdateWorkspace,
  onAddMember,
  onAddToAccessList,
  onRemoveFromAccessList,
  onGetAccessList,
}: WorkspaceSidebarProps) {
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const [editing, setEditing] = useState(false);
  const [editName, setEditName] = useState(workspace.name);
  const [editDescription, setEditDescription] = useState(workspace.description || "");

  const [showAccessList, setShowAccessList] = useState(false);
  const [activeListTab, setActiveListTab] = useState<"allow" | "block">("allow");
  const [accessEntries, setAccessEntries] = useState<AccessListEntry[]>([]);
  const [accessLoading, setAccessLoading] = useState(false);
  const [newAccessName, setNewAccessName] = useState("");

  const copyInvite = () => {
    const url = `${window.location.origin}/join/${workspace.invite_code}`;
    navigator.clipboard.writeText(url);
  };

  const loadAccessList = useCallback(
    async (listType: "allow" | "block") => {
      if (!onGetAccessList) return;
      setAccessLoading(true);
      try {
        const entries = await onGetAccessList(listType);
        setAccessEntries(entries);
      } catch {
        setAccessEntries([]);
      } finally {
        setAccessLoading(false);
      }
    },
    [onGetAccessList]
  );

  const handleToggleAccessList = () => {
    const next = !showAccessList;
    setShowAccessList(next);
    if (next) {
      loadAccessList(activeListTab);
    }
  };

  const handleTabSwitch = (tab: "allow" | "block") => {
    setActiveListTab(tab);
    loadAccessList(tab);
  };

  const handleAddEntry = async () => {
    if (!newAccessName.trim() || !onAddToAccessList) return;
    try {
      await onAddToAccessList(newAccessName.trim(), activeListTab);
      setNewAccessName("");
      loadAccessList(activeListTab);
    } catch {
      // Ignore
    }
  };

  const handleRemoveEntry = async (userName: string) => {
    if (!onRemoveFromAccessList) return;
    try {
      await onRemoveFromAccessList(userName, activeListTab);
      loadAccessList(activeListTab);
    } catch {
      // Ignore
    }
  };

  return (
    <div className="w-64 bg-surface border-l border-border flex flex-col flex-shrink-0">
      <div className="p-4 border-b border-border">
        {editing ? (
          <div className="space-y-2">
            <input
              type="text"
              value={editName}
              onChange={(e) => setEditName(e.target.value)}
              className="w-full bg-raised border border-border rounded px-2 py-1 text-sm text-foreground"
              placeholder="Workspace name"
            />
            <textarea
              value={editDescription}
              onChange={(e) => setEditDescription(e.target.value)}
              className="w-full bg-raised border border-border rounded px-2 py-1 text-sm text-foreground resize-none"
              rows={2}
              placeholder="Description"
            />
            <div className="flex gap-2">
              <button
                onClick={() => {
                  onUpdateWorkspace({
                    name: editName !== workspace.name ? editName : undefined,
                    description:
                      editDescription !== (workspace.description || "")
                        ? editDescription
                        : undefined,
                  });
                  setEditing(false);
                }}
                className="text-xs bg-brand hover:bg-brand-hover text-foreground px-3 py-1 rounded"
              >
                Save
              </button>
              <button
                onClick={() => {
                  setEditName(workspace.name);
                  setEditDescription(workspace.description || "");
                  setEditing(false);
                }}
                className="text-xs text-dim hover:text-foreground px-3 py-1"
              >
                Cancel
              </button>
            </div>
          </div>
        ) : (
          <>
            <div className="flex items-start justify-between">
              <h2 className="font-medium text-foreground truncate">{workspace.name}</h2>
              {isOwner && (
                <button
                  onClick={() => {
                    setEditName(workspace.name);
                    setEditDescription(workspace.description || "");
                    setEditing(true);
                  }}
                  className="text-xs text-muted hover:text-dim ml-2 flex-shrink-0"
                >
                  Edit
                </button>
              )}
            </div>
            {workspace.description && (
              <p className="text-dim text-xs mt-1 line-clamp-3">
                {workspace.description}
              </p>
            )}
          </>
        )}
        <div className="mt-3 flex flex-col gap-2">
          <button
            onClick={copyInvite}
            className="w-full text-xs bg-raised hover:bg-raised text-dim px-3 py-1.5 rounded border border-border"
          >
            Copy Invite Link
          </button>
          <div className="text-xs text-muted text-center">
            Code:{" "}
            <span className="font-mono text-dim">{workspace.invite_code}</span>
          </div>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto p-4">
        <h3 className="text-xs uppercase tracking-wider text-muted mb-2">
          Members ({members.length})
        </h3>
        <div className="space-y-2">
          {members.map((m) => (
            <div key={m.user_id} className="flex items-center gap-2 group">
              <div className="w-6 h-6 rounded-full flex items-center justify-center text-[10px] font-bold bg-human-muted text-human">
                {(m.display_name || m.name).charAt(0).toUpperCase()}
              </div>
              <div className="min-w-0 flex-1">
                <div className="text-sm text-dim truncate">
                  {m.display_name || m.name}
                </div>
                <div className="text-[10px] text-muted">
                  {m.role}
                </div>
              </div>
              {isOwner && m.user_id !== currentUserId && (
                <button
                  onClick={() => onKickMember(m.user_id)}
                  className="hidden group-hover:block text-[10px] text-red-400 hover:text-red-300 px-1"
                  title={`Remove ${m.display_name || m.name}`}
                >
                  Remove
                </button>
              )}
            </div>
          ))}
        </div>

        {/* Add member */}
        {isOwner && (
          <div className="mt-3">
            <AddMemberInput onAdd={onAddMember} existingMemberIds={members.map(m => m.user_id)} />
          </div>
        )}

        {isOwner && onGetAccessList && (
          <div className="mt-4">
            <button
              onClick={handleToggleAccessList}
              className="text-xs uppercase tracking-wider text-muted hover:text-dim flex items-center gap-1 mb-2"
            >
              <span className={`transition-transform ${showAccessList ? "rotate-90" : ""}`}>
                &#9654;
              </span>
              Access Lists
            </button>

            {showAccessList && (
              <div className="space-y-2">
                <div className="flex border border-border rounded overflow-hidden">
                  <button
                    onClick={() => handleTabSwitch("allow")}
                    className={`flex-1 text-xs py-1 ${
                      activeListTab === "allow"
                        ? "bg-brand text-foreground"
                        : "bg-raised text-dim hover:text-foreground"
                    }`}
                  >
                    Allow
                  </button>
                  <button
                    onClick={() => handleTabSwitch("block")}
                    className={`flex-1 text-xs py-1 ${
                      activeListTab === "block"
                        ? "bg-red-600 text-foreground"
                        : "bg-raised text-dim hover:text-foreground"
                    }`}
                  >
                    Block
                  </button>
                </div>

                <div className="flex gap-1">
                  <input
                    type="text"
                    value={newAccessName}
                    onChange={(e) => setNewAccessName(e.target.value)}
                    onKeyDown={(e) => e.key === "Enter" && handleAddEntry()}
                    placeholder="Username..."
                    className="flex-1 bg-raised border border-border rounded px-2 py-1 text-xs text-foreground focus:outline-none focus:border-brand"
                  />
                  <button
                    onClick={handleAddEntry}
                    className="text-xs bg-raised hover:bg-raised text-foreground px-2 py-1 rounded"
                  >
                    Add
                  </button>
                </div>

                {accessLoading ? (
                  <div className="text-xs text-muted">Loading...</div>
                ) : accessEntries.length === 0 ? (
                  <div className="text-xs text-muted">No entries.</div>
                ) : (
                  <div className="space-y-1">
                    {accessEntries.map((entry) => (
                      <div
                        key={entry.user_name}
                        className="flex items-center justify-between text-xs bg-raised rounded px-2 py-1"
                      >
                        <span className="text-dim truncate">
                          {entry.user_name}
                        </span>
                        <button
                          onClick={() => handleRemoveEntry(entry.user_name)}
                          className="text-red-400 hover:text-red-300 ml-2 flex-shrink-0"
                        >
                          &times;
                        </button>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>
        )}
      </div>

      <div className="p-4 border-t border-border space-y-2">
        {isOwner && (
          <>
            {showDeleteConfirm ? (
              <div className="space-y-2">
                <p className="text-xs text-red-400 text-center">
                  Delete this workspace permanently?
                </p>
                <div className="flex gap-2">
                  <button
                    onClick={onDelete}
                    className="flex-1 text-xs bg-red-600 hover:bg-red-500 text-foreground px-3 py-1.5 rounded"
                  >
                    Confirm
                  </button>
                  <button
                    onClick={() => setShowDeleteConfirm(false)}
                    className="flex-1 text-xs text-dim hover:text-foreground px-3 py-1.5 rounded border border-border"
                  >
                    Cancel
                  </button>
                </div>
              </div>
            ) : (
              <button
                onClick={() => setShowDeleteConfirm(true)}
                className="w-full text-xs text-red-400 hover:text-red-300 hover:bg-raised px-3 py-1.5 rounded border border-border"
              >
                Delete Workspace
              </button>
            )}
          </>
        )}
        <button
          onClick={onLeave}
          className="w-full text-xs text-red-400 hover:text-red-300 hover:bg-raised px-3 py-1.5 rounded"
        >
          Leave Workspace
        </button>
      </div>
    </div>
  );
}
