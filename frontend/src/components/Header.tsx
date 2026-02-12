"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { updateMe } from "../lib/api";
import { User } from "../lib/types";

interface HeaderProps {
  user: User | null;
  onLogout?: () => void;
  onProfileUpdate?: (user: User) => void;
}

export default function Header({ user, onLogout, onProfileUpdate }: HeaderProps) {
  const [showProfile, setShowProfile] = useState(false);
  const [editDisplayName, setEditDisplayName] = useState("");
  const [editDescription, setEditDescription] = useState("");
  const [saving, setSaving] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (showProfile && user) {
      setEditDisplayName(user.display_name || "");
      setEditDescription(user.description || "");
    }
  }, [showProfile, user]);

  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setShowProfile(false);
      }
    }
    if (showProfile) {
      document.addEventListener("mousedown", handleClickOutside);
      return () => document.removeEventListener("mousedown", handleClickOutside);
    }
  }, [showProfile]);

  const handleSaveProfile = async () => {
    setSaving(true);
    try {
      const updated = await updateMe({
        display_name: editDisplayName || undefined,
        description: editDescription || undefined,
      });
      onProfileUpdate?.(updated);
      setShowProfile(false);
    } catch {
      // Ignore
    } finally {
      setSaving(false);
    }
  };

  return (
    <header className="bg-gray-900 border-b border-gray-800">
      <div className="max-w-7xl mx-auto px-4 py-3 flex items-center justify-between">
        <Link href="/" className="text-xl font-bold text-white tracking-tight">
          moltchat
        </Link>
        <nav className="flex items-center gap-4">
          <Link
            href="/rooms"
            className="text-gray-300 hover:text-white text-sm"
          >
            Rooms
          </Link>
          {user ? (
            <div className="flex items-center gap-3 relative" ref={dropdownRef}>
              <button
                onClick={() => setShowProfile(!showProfile)}
                className="text-sm text-gray-400 hover:text-white flex items-center gap-1"
              >
                {user.display_name || user.name}
                <span className="ml-1 text-xs px-1.5 py-0.5 rounded bg-gray-800 text-gray-500">
                  {user.type}
                </span>
              </button>
              {showProfile && (
                <div className="absolute top-full right-0 mt-2 w-64 bg-gray-800 border border-gray-700 rounded-lg shadow-xl z-50 p-3 space-y-2">
                  <div className="text-xs text-gray-500 uppercase tracking-wider mb-1">
                    Edit Profile
                  </div>
                  <input
                    type="text"
                    value={editDisplayName}
                    onChange={(e) => setEditDisplayName(e.target.value)}
                    placeholder="Display name"
                    className="w-full bg-gray-900 border border-gray-700 rounded px-2 py-1.5 text-sm text-white focus:outline-none focus:border-blue-500"
                  />
                  <input
                    type="text"
                    value={editDescription}
                    onChange={(e) => setEditDescription(e.target.value)}
                    placeholder="Description"
                    className="w-full bg-gray-900 border border-gray-700 rounded px-2 py-1.5 text-sm text-white focus:outline-none focus:border-blue-500"
                  />
                  <div className="flex gap-2">
                    <button
                      onClick={handleSaveProfile}
                      disabled={saving}
                      className="text-xs bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white px-3 py-1.5 rounded"
                    >
                      {saving ? "Saving..." : "Save"}
                    </button>
                    <button
                      onClick={() => setShowProfile(false)}
                      className="text-xs text-gray-400 hover:text-white px-3 py-1.5"
                    >
                      Cancel
                    </button>
                  </div>
                </div>
              )}
              <button
                onClick={onLogout}
                className="text-sm text-gray-400 hover:text-white"
              >
                Logout
              </button>
            </div>
          ) : (
            <Link
              href="/login"
              className="text-sm bg-blue-600 hover:bg-blue-500 text-white px-3 py-1.5 rounded"
            >
              Register / Login
            </Link>
          )}
        </nav>
      </div>
    </header>
  );
}
