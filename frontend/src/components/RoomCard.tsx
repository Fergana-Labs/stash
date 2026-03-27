"use client";

import Link from "next/link";
import { Workspace } from "../lib/types";

interface WorkspaceCardProps {
  workspace: Workspace;
  isMember?: boolean;
}

export default function WorkspaceCard({ workspace, isMember }: WorkspaceCardProps) {
  return (
    <Link
      href={`/workspaces/${workspace.id}`}
      className="block bg-gray-800 border border-gray-700 rounded-lg p-4 hover:border-gray-600 transition-colors"
    >
      <div className="flex items-start justify-between">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <span className="text-base" title="Workspace">{"\u{1F4C1}"}</span>
            <h3 className="text-white font-medium truncate">{workspace.name}</h3>
          </div>
          {workspace.description && (
            <p className="text-gray-400 text-sm mt-1 line-clamp-2">
              {workspace.description}
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
        <span>{workspace.member_count ?? 0} members</span>
        <span>Code: {workspace.invite_code}</span>
        {!workspace.is_public && <span className="text-yellow-500">Private</span>}
      </div>
    </Link>
  );
}
