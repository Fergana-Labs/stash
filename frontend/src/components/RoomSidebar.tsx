"use client";

import { Room, RoomMember } from "../lib/types";

interface RoomSidebarProps {
  room: Room;
  members: RoomMember[];
  onLeave: () => void;
}

export default function RoomSidebar({
  room,
  members,
  onLeave,
}: RoomSidebarProps) {
  const copyInvite = () => {
    const url = `${window.location.origin}/join/${room.invite_code}`;
    navigator.clipboard.writeText(url);
  };

  return (
    <div className="w-64 bg-gray-900 border-l border-gray-800 flex flex-col">
      <div className="p-4 border-b border-gray-800">
        <h2 className="font-medium text-white truncate">{room.name}</h2>
        {room.description && (
          <p className="text-gray-400 text-xs mt-1 line-clamp-3">
            {room.description}
          </p>
        )}
        <div className="mt-3 flex flex-col gap-2">
          <button
            onClick={copyInvite}
            className="w-full text-xs bg-gray-800 hover:bg-gray-700 text-gray-300 px-3 py-1.5 rounded border border-gray-700"
          >
            Copy Invite Link
          </button>
          <div className="text-xs text-gray-500 text-center">
            Code: <span className="font-mono text-gray-400">{room.invite_code}</span>
          </div>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto p-4">
        <h3 className="text-xs uppercase tracking-wider text-gray-500 mb-2">
          Members ({members.length})
        </h3>
        <div className="space-y-2">
          {members.map((m) => (
            <div key={m.user_id} className="flex items-center gap-2">
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
            </div>
          ))}
        </div>
      </div>

      <div className="p-4 border-t border-gray-800">
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
