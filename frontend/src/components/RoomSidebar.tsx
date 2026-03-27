"use client";

import { useCallback, useState } from "react";
import { Chat, WorkspaceMember } from "../lib/types";

interface RoomSidebarProps {
  room: Chat;
  members: WorkspaceMember[];
  currentUserId: string;
  isOwner: boolean;
  isDM?: boolean;
  dmOtherUser?: WorkspaceMember;
  onLeave: () => void;
  onDeleteRoom: () => void;
  onKickMember: (userId: string) => void;
  onUpdateRoom: (data: { name?: string; description?: string }) => void;
  onAddToAccessList?: (userName: string, listType: "allow" | "block") => Promise<void>;
  onRemoveFromAccessList?: (userName: string, listType: "allow" | "block") => Promise<void>;
  onGetAccessList?: (listType: "allow" | "block") => Promise<any[]>;
}

export default function RoomSidebar({
  room,
  members,
  currentUserId,
  isOwner,
  isDM,
  dmOtherUser,
  onLeave,
  onDeleteRoom,
  onKickMember,
  onUpdateRoom,
  onAddToAccessList,
  onRemoveFromAccessList,
  onGetAccessList,
}: RoomSidebarProps) {
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const [editing, setEditing] = useState(false);
  const [editName, setEditName] = useState(room.name);
  const [editDescription, setEditDescription] = useState(
    room.description || ""
  );

  // Access list state
  const [showAccessList, setShowAccessList] = useState(false);
  const [activeListTab, setActiveListTab] = useState<"allow" | "block">("allow");
  const [accessEntries, setAccessEntries] = useState<any[]>([]);
  const [accessLoading, setAccessLoading] = useState(false);
  const [newAccessName, setNewAccessName] = useState("");

  const copyInvite = () => {
    const url = `${window.location.origin}/join/${""}`;
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

  if (isDM) {
    const other = dmOtherUser;
    const displayName = other?.display_name || other?.name || "Unknown";
    return (
      <div className="w-64 bg-surface border-l border-border flex flex-col">
        <div className="p-4 border-b border-border">
          <div className="flex flex-col items-center text-center">
            <div
              className={`w-14 h-14 rounded-full flex items-center justify-center text-lg font-bold mb-3 ${
                other?.type === "agent"
                  ? "bg-agent-muted text-agent"
                  : "bg-human-muted text-human"
              }`}
            >
              {displayName.charAt(0).toUpperCase()}
            </div>
            <h2 className="font-medium text-foreground">{displayName}</h2>
            {other && (
              <div className="text-xs text-muted mt-1">
                @{other.name} &middot; {other.type}
              </div>
            )}
          </div>
        </div>
        <div className="flex-1" />
      </div>
    );
  }

  return (
    <div className="w-64 bg-surface border-l border-border flex flex-col">
      <div className="p-4 border-b border-border">
        {editing ? (
          <div className="space-y-2">
            <input
              type="text"
              value={editName}
              onChange={(e) => setEditName(e.target.value)}
              className="w-full bg-raised border border-border rounded px-2 py-1 text-sm text-foreground"
              placeholder="Room name"
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
                  onUpdateRoom({
                    name: editName !== room.name ? editName : undefined,
                    description:
                      editDescription !== (room.description || "")
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
                  setEditName(room.name);
                  setEditDescription(room.description || "");
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
              <h2 className="font-medium text-foreground truncate">{room.name}</h2>
              {isOwner && (
                <button
                  onClick={() => {
                    setEditName(room.name);
                    setEditDescription(room.description || "");
                    setEditing(true);
                  }}
                  className="text-xs text-muted hover:text-foreground ml-2 flex-shrink-0"
                >
                  Edit
                </button>
              )}
            </div>
            {room.description && (
              <p className="text-dim text-xs mt-1 line-clamp-3">
                {room.description}
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
            <span className="font-mono text-dim">{""}</span>
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
              <div
                className={`w-6 h-6 rounded-full flex items-center justify-center text-[10px] font-bold ${
                  m.type === "agent"
                    ? "bg-agent-muted text-agent"
                    : "bg-human-muted text-human"
                }`}
              >
                {(m.display_name || m.name).charAt(0).toUpperCase()}
              </div>
              <div className="min-w-0 flex-1">
                <div className="text-sm text-dim truncate">
                  {m.display_name || m.name}
                </div>
                <div className="text-[10px] text-muted">
                  {m.role} · {m.type}
                </div>
              </div>
              {isOwner && m.user_id !== currentUserId && (
                <button
                  onClick={() => onKickMember(m.user_id)}
                  className="hidden group-hover:block text-[10px] text-red-400 hover:text-red-300 px-1"
                  title={`Kick ${m.display_name || m.name}`}
                >
                  Kick
                </button>
              )}
            </div>
          ))}
        </div>

        {isOwner && onGetAccessList && (
          <div className="mt-4">
            <button
              onClick={handleToggleAccessList}
              className="text-xs uppercase tracking-wider text-muted hover:text-foreground flex items-center gap-1 mb-2"
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
                  Delete this room permanently?
                </p>
                <div className="flex gap-2">
                  <button
                    onClick={onDeleteRoom}
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
                Delete Room
              </button>
            )}
          </>
        )}
        <button
          onClick={onLeave}
          className="w-full text-xs text-red-400 hover:text-red-300 hover:bg-raised px-3 py-1.5 rounded"
        >
          Leave Room
        </button>
      </div>
    </div>
  );
}
