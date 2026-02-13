"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { createOrGetDM, searchUsers } from "../lib/api";
import { UserSearchResult } from "../lib/types";

interface NewDMDialogProps {
  open: boolean;
  onClose: () => void;
}

export default function NewDMDialog({ open, onClose }: NewDMDialogProps) {
  const router = useRouter();
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<UserSearchResult[]>([]);
  const [loading, setLoading] = useState(false);
  const [starting, setStarting] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const searchTimeoutRef = useRef<NodeJS.Timeout | null>(null);

  useEffect(() => {
    if (open) {
      setQuery("");
      setResults([]);
      setTimeout(() => inputRef.current?.focus(), 100);
    }
  }, [open]);

  const handleSearch = useCallback((value: string) => {
    setQuery(value);
    if (searchTimeoutRef.current) clearTimeout(searchTimeoutRef.current);
    if (!value.trim()) {
      setResults([]);
      setLoading(false);
      return;
    }
    setLoading(true);
    searchTimeoutRef.current = setTimeout(async () => {
      try {
        const users = await searchUsers(value.trim());
        setResults(users);
      } catch {
        setResults([]);
      } finally {
        setLoading(false);
      }
    }, 300);
  }, []);

  const handleSelect = useCallback(
    async (userId: string) => {
      setStarting(true);
      try {
        const dm = await createOrGetDM(userId);
        onClose();
        router.push(`/rooms/${dm.id}`);
      } catch {
        // Ignore
      } finally {
        setStarting(false);
      }
    },
    [onClose, router]
  );

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center pt-24">
      <div
        className="fixed inset-0 bg-black/60"
        onClick={onClose}
      />
      <div className="relative bg-gray-900 border border-gray-700 rounded-lg w-full max-w-md mx-4 shadow-xl">
        <div className="p-4 border-b border-gray-800">
          <h2 className="text-white font-medium mb-3">New Message</h2>
          <input
            ref={inputRef}
            type="text"
            value={query}
            onChange={(e) => handleSearch(e.target.value)}
            placeholder="Search users by name..."
            className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm text-white focus:outline-none focus:border-blue-500"
            disabled={starting}
          />
        </div>
        <div className="max-h-64 overflow-y-auto">
          {loading ? (
            <div className="px-4 py-3 text-sm text-gray-500">Searching...</div>
          ) : results.length === 0 && query.trim() ? (
            <div className="px-4 py-3 text-sm text-gray-500">No users found</div>
          ) : (
            results.map((user) => (
              <button
                key={user.id}
                onClick={() => handleSelect(user.id)}
                disabled={starting}
                className="w-full px-4 py-3 flex items-center gap-3 hover:bg-gray-800 transition-colors text-left disabled:opacity-50"
              >
                <div
                  className={`w-8 h-8 rounded-full flex items-center justify-center text-xs font-bold flex-shrink-0 ${
                    user.type === "agent"
                      ? "bg-purple-900 text-purple-300"
                      : "bg-blue-900 text-blue-300"
                  }`}
                >
                  {(user.display_name || user.name).charAt(0).toUpperCase()}
                </div>
                <div className="min-w-0 flex-1">
                  <div className="text-sm text-white truncate">
                    {user.display_name || user.name}
                  </div>
                  <div className="text-xs text-gray-500">
                    @{user.name}
                    {user.type === "agent" && (
                      <span className="ml-1.5 text-purple-400">agent</span>
                    )}
                  </div>
                </div>
              </button>
            ))
          )}
          {!query.trim() && !loading && (
            <div className="px-4 py-3 text-sm text-gray-500">
              Type a name to search for users
            </div>
          )}
        </div>
        <div className="p-3 border-t border-gray-800 flex justify-end">
          <button
            onClick={onClose}
            className="text-sm text-gray-400 hover:text-white px-3 py-1.5"
          >
            Cancel
          </button>
        </div>
      </div>
    </div>
  );
}
