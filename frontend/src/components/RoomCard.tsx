"use client";

import Link from "next/link";
import { Room } from "../lib/types";

interface RoomCardProps {
  room: Room;
  isMember?: boolean;
}

export default function RoomCard({ room, isMember }: RoomCardProps) {
  return (
    <Link
      href={`/rooms/${room.id}`}
      className="block bg-gray-800 border border-gray-700 rounded-lg p-4 hover:border-gray-600 transition-colors"
    >
      <div className="flex items-start justify-between">
        <div className="min-w-0 flex-1">
          <h3 className="text-white font-medium truncate">{room.name}</h3>
          {room.description && (
            <p className="text-gray-400 text-sm mt-1 line-clamp-2">
              {room.description}
            </p>
          )}
        </div>
        {isMember && (
          <span className="text-xs bg-green-900 text-green-300 px-2 py-0.5 rounded ml-2 flex-shrink-0">
            Joined
          </span>
        )}
      </div>
      <div className="flex items-center gap-3 mt-3 text-xs text-gray-500">
        <span>{room.member_count ?? 0} members</span>
        <span>Code: {room.invite_code}</span>
        {!room.is_public && <span className="text-yellow-500">Private</span>}
      </div>
    </Link>
  );
}
