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
      <div className="w-64 bg-gray-900 border-l border-gray-800 flex flex-col">
        <div className="p-4 border-b border-gray-800">
          <div className="flex flex-col items-center text-center">
            <div
              className={`w-14 h-14 rounded-full flex items-center justify-center text-lg font-bold mb-3 ${
                other?.type === "agent"
                  ? "bg-purple-900 text-purple-300"
                  : "bg-blue-900 text-blue-300"
              }`}
            >
              {displayName.charAt(0).toUpperCase()}
            </div>
            <h2 className="font-medium text-white">{displayName}</h2>
            {other && (
              <div className="text-xs text-gray-500 mt-1">
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
    <div className="w-64 bg-gray-900 border-l border-gray-800 flex flex-col">
      <div className="p-4 border-b border-gray-800">
        {editing ? (
          <div className="space-y-2">
            <input
              type="text"
              value={editName}
              onChange={(e) => setEditName(e.target.value)}
              className="w-full bg-gray-800 border border-gray-700 rounded px-2 py-1 text-sm text-white"
              placeholder="Room name"
            />
            <textarea
              value={editDescription}
              onChange={(e) => setEditDescription(e.target.value)}
              className="w-full bg-gray-800 border border-gray-700 rounded px-2 py-1 text-sm text-white resize-none"
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
                className="text-xs bg-blue-600 hover:bg-blue-500 text-white px-3 py-1 rounded"
              >
                Save
              </button>
              <button
                onClick={() => {
                  setEditName(room.name);
                  setEditDescription(room.description || "");
                  setEditing(false);
                }}
                className="text-xs text-gray-400 hover:text-white px-3 py-1"
              >
                Cancel
              </button>
            </div>
          </div>
        ) : (
          <>
            <div className="flex items-start justify-between">
              <h2 className="font-medium text-white truncate">{room.name}</h2>
              {isOwner && (
                <button
                  onClick={() => {
                    setEditName(room.name);
                    setEditDescription(room.description || "");
                    setEditing(true);
                  }}
                  className="text-xs text-gray-500 hover:text-gray-300 ml-2 flex-shrink-0"
                >
                  Edit
                </button>
              )}
            </div>
            {room.description && (
              <p className="text-gray-400 text-xs mt-1 line-clamp-3">
                {room.description}
              </p>
            )}
          </>
        )}
        <div className="mt-3 flex flex-col gap-2">
          <button
            onClick={copyInvite}
            className="w-full text-xs bg-gray-800 hover:bg-gray-700 text-gray-300 px-3 py-1.5 rounded border border-gray-700"
          >
            Copy Invite Link
          </button>
          <div className="text-xs text-gray-500 text-center">
            Code:{" "}
            <span className="font-mono text-gray-400">{""}</span>
          </div>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto p-4">
        <h3 className="text-xs uppercase tracking-wider text-gray-500 mb-2">
          Members ({members.length})
        </h3>
        <div className="space-y-2">
          {members.map((m) => (
            <div key={m.user_id} className="flex items-center gap-2 group">
              <div
                className={`w-6 h-6 rounded-full flex items-center justify-center text-[10px] font-bold ${
                  m.type === "agent"
                    ? "bg-purple-900 text-purple-300"
                    : "bg-blue-900 text-blue-300"
                }`}
              >
                {(m.display_name || m.name).charAt(0).toUpperCase()}
              </div>
              <div className="min-w-0 flex-1">
                <div className="text-sm text-gray-300 truncate">
                  {m.display_name || m.name}
                </div>
                <div className="text-[10px] text-gray-600">
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
              className="text-xs uppercase tracking-wider text-gray-500 hover:text-gray-300 flex items-center gap-1 mb-2"
            >
              <span className={`transition-transform ${showAccessList ? "rotate-90" : ""}`}>
                &#9654;
              </span>
              Access Lists
            </button>

            {showAccessList && (
              <div className="space-y-2">
                <div className="flex border border-gray-700 rounded overflow-hidden">
                  <button
                    onClick={() => handleTabSwitch("allow")}
                    className={`flex-1 text-xs py-1 ${
                      activeListTab === "allow"
                        ? "bg-blue-600 text-white"
                        : "bg-gray-800 text-gray-400 hover:text-white"
                    }`}
                  >
                    Allow
                  </button>
                  <button
                    onClick={() => handleTabSwitch("block")}
                    className={`flex-1 text-xs py-1 ${
                      activeListTab === "block"
                        ? "bg-red-600 text-white"
                        : "bg-gray-800 text-gray-400 hover:text-white"
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
                    className="flex-1 bg-gray-800 border border-gray-700 rounded px-2 py-1 text-xs text-white focus:outline-none focus:border-blue-500"
                  />
                  <button
                    onClick={handleAddEntry}
                    className="text-xs bg-gray-700 hover:bg-gray-600 text-white px-2 py-1 rounded"
                  >
                    Add
                  </button>
                </div>

                {accessLoading ? (
                  <div className="text-xs text-gray-500">Loading...</div>
                ) : accessEntries.length === 0 ? (
                  <div className="text-xs text-gray-600">No entries.</div>
                ) : (
                  <div className="space-y-1">
                    {accessEntries.map((entry) => (
                      <div
                        key={entry.user_name}
                        className="flex items-center justify-between text-xs bg-gray-800 rounded px-2 py-1"
                      >
                        <span className="text-gray-300 truncate">
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

      <div className="p-4 border-t border-gray-800 space-y-2">
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
                    className="flex-1 text-xs bg-red-600 hover:bg-red-500 text-white px-3 py-1.5 rounded"
                  >
                    Confirm
                  </button>
                  <button
                    onClick={() => setShowDeleteConfirm(false)}
                    className="flex-1 text-xs text-gray-400 hover:text-white px-3 py-1.5 rounded border border-gray-700"
                  >
                    Cancel
                  </button>
                </div>
              </div>
            ) : (
              <button
                onClick={() => setShowDeleteConfirm(true)}
                className="w-full text-xs text-red-400 hover:text-red-300 hover:bg-gray-800 px-3 py-1.5 rounded border border-gray-800"
              >
                Delete Room
              </button>
            )}
          </>
        )}
        <button
          onClick={onLeave}
          className="w-full text-xs text-red-400 hover:text-red-300 hover:bg-gray-800 px-3 py-1.5 rounded"
        >
          Leave Room
        </button>
      </div>
    </div>
  );
}
