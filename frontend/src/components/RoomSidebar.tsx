"use client";

import { useState } from "react";
import { Room, RoomMember } from "../lib/types";

interface RoomSidebarProps {
  room: Room;
  members: RoomMember[];
  currentUserId: string;
  isOwner: boolean;
  onLeave: () => void;
  onDeleteRoom: () => void;
  onKickMember: (userId: string) => void;
  onUpdateRoom: (data: { name?: string; description?: string }) => void;
}

export default function RoomSidebar({
  room,
  members,
  currentUserId,
  isOwner,
  onLeave,
  onDeleteRoom,
  onKickMember,
  onUpdateRoom,
}: RoomSidebarProps) {
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const [editing, setEditing] = useState(false);
  const [editName, setEditName] = useState(room.name);
  const [editDescription, setEditDescription] = useState(
    room.description || ""
  );

  const copyInvite = () => {
    const url = `${window.location.origin}/join/${room.invite_code}`;
    navigator.clipboard.writeText(url);
  };

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
            <span className="font-mono text-gray-400">{room.invite_code}</span>
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
