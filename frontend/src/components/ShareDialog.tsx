"use client";

import { useCallback, useEffect, useState } from "react";
import { addShare, getPermissions, removeShare, searchUsers, setVisibility } from "../lib/api";
import { ObjectPermission, Share, UserSearchResult } from "../lib/types";

interface ShareDialogProps {
  open: boolean;
  onClose: () => void;
  objectType: string;
  objectId: string;
  workspaceId: string;
}

export default function ShareDialog({ open, onClose, objectType, objectId, workspaceId }: ShareDialogProps) {
  const [perms, setPerms] = useState<ObjectPermission | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [searchResults, setSearchResults] = useState<UserSearchResult[]>([]);
  const [selectedPermission, setSelectedPermission] = useState<"read" | "write" | "admin">("read");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const loadPermissions = useCallback(async () => {
    try {
      const p = await getPermissions(workspaceId, objectType, objectId);
      setPerms(p);
    } catch { /* ignore */ }
  }, [workspaceId, objectType, objectId]);

  useEffect(() => {
    if (open) { loadPermissions(); setSearchQuery(""); setSearchResults([]); setError(""); }
  }, [open, loadPermissions]);

  useEffect(() => {
    if (!searchQuery.trim()) { setSearchResults([]); return; }
    const timer = setTimeout(async () => {
      try {
        const results = await searchUsers(searchQuery.trim());
        setSearchResults(results);
      } catch { /* ignore */ }
    }, 300);
    return () => clearTimeout(timer);
  }, [searchQuery]);

  const handleSetVisibility = async (vis: "inherit" | "private" | "public") => {
    setError("");
    try {
      await setVisibility(workspaceId, objectType, objectId, vis);
      await loadPermissions();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to set visibility");
    }
  };

  const handleAddShare = async (userId: string) => {
    setError("");
    setLoading(true);
    try {
      await addShare(workspaceId, objectType, objectId, userId, selectedPermission);
      setSearchQuery("");
      setSearchResults([]);
      await loadPermissions();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to add share");
    }
    setLoading(false);
  };

  const handleRemoveShare = async (userId: string) => {
    setError("");
    try {
      await removeShare(workspaceId, objectType, objectId, userId);
      await loadPermissions();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to remove share");
    }
  };

  if (!open) return null;

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50" onClick={onClose}>
      <div className="bg-surface border border-border rounded-lg shadow-xl w-full max-w-md p-4" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-foreground font-medium">Share {objectType}</h3>
          <button onClick={onClose} className="text-muted hover:text-foreground">&times;</button>
        </div>

        {error && <p className="text-red-400 text-sm mb-3">{error}</p>}

        {/* Visibility */}
        <div className="mb-4">
          <div className="text-xs text-muted uppercase tracking-wider mb-2">Visibility</div>
          <div className="flex gap-1">
            {(["inherit", "private", "public"] as const).map((vis) => (
              <button
                key={vis}
                onClick={() => handleSetVisibility(vis)}
                className={`text-xs px-3 py-1.5 rounded border transition-colors ${
                  perms?.visibility === vis
                    ? "bg-brand border-brand text-foreground"
                    : "bg-raised border-border text-dim hover:text-foreground"
                }`}
              >
                {vis === "inherit" ? "Workspace members" : vis === "private" ? "Private" : "Public"}
              </button>
            ))}
          </div>
        </div>

        {/* Current shares */}
        {perms && perms.shares.length > 0 && (
          <div className="mb-4">
            <div className="text-xs text-muted uppercase tracking-wider mb-2">Shared with</div>
            <div className="space-y-1">
              {perms.shares.map((share: Share) => (
                <div key={share.user_id} className="flex items-center justify-between px-2 py-1.5 rounded bg-raised">
                  <div className="flex items-center gap-2">
                    <span className="text-sm text-foreground">{share.user_name}</span>
                    <span className="text-[10px] text-muted bg-surface px-1.5 py-0.5 rounded">{share.permission}</span>
                  </div>
                  <button
                    onClick={() => handleRemoveShare(share.user_id)}
                    className="text-xs text-red-400 hover:text-red-300"
                  >
                    Remove
                  </button>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Add share */}
        <div>
          <div className="text-xs text-muted uppercase tracking-wider mb-2">Add person</div>
          <div className="flex gap-2 mb-2">
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search by username..."
              className="flex-1 bg-raised border border-border rounded px-3 py-1.5 text-sm text-foreground focus:outline-none focus:border-brand"
            />
            <select
              value={selectedPermission}
              onChange={(e) => setSelectedPermission(e.target.value as "read" | "write" | "admin")}
              className="bg-raised border border-border rounded px-2 py-1.5 text-sm text-foreground"
            >
              <option value="read">Read</option>
              <option value="write">Write</option>
              <option value="admin">Admin</option>
            </select>
          </div>
          {searchResults.length > 0 && (
            <div className="space-y-0.5 max-h-32 overflow-y-auto">
              {searchResults.map((u) => (
                <button
                  key={u.id}
                  onClick={() => handleAddShare(u.id)}
                  disabled={loading}
                  className="w-full text-left flex items-center gap-2 px-2 py-1.5 rounded hover:bg-raised transition-colors text-sm"
                >
                  <span className={`w-6 h-6 rounded-full flex items-center justify-center text-[10px] font-bold ${
                    u.type === "agent" ? "bg-agent-muted text-agent" : "bg-human-muted text-human"
                  }`}>
                    {(u.display_name || u.name).charAt(0).toUpperCase()}
                  </span>
                  <span className="text-foreground">{u.display_name || u.name}</span>
                  <span className="text-muted text-xs">@{u.name}</span>
                </button>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
