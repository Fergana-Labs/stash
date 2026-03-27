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
  const [editPassword, setEditPassword] = useState("");
  const [saving, setSaving] = useState(false);
  const [saveMsg, setSaveMsg] = useState("");
  const dropdownRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (showProfile && user) {
      setEditDisplayName(user.display_name || "");
      setEditDescription(user.description || "");
      setEditPassword("");
      setSaveMsg("");
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
    if (editPassword && editPassword.length < 8) {
      setSaveMsg("Password must be at least 8 characters");
      return;
    }
    setSaving(true);
    setSaveMsg("");
    try {
      const updated = await updateMe({
        display_name: editDisplayName || undefined,
        description: editDescription || undefined,
        ...(editPassword ? { password: editPassword } : {}),
      });
      onProfileUpdate?.(updated);
      setSaveMsg(editPassword ? "Saved (password updated)" : "Saved");
      setEditPassword("");
    } catch {
      setSaveMsg("Failed to save");
    } finally {
      setSaving(false);
    }
  };

  return (
    <header className="bg-surface border-b border-border">
      <div className="px-4 py-2 flex items-center justify-end gap-4">
          {user ? (
            <div className="flex items-center gap-3 relative" ref={dropdownRef}>
              <button
                onClick={() => setShowProfile(!showProfile)}
                className="text-sm text-dim hover:text-foreground flex items-center gap-1"
              >
                {user.display_name || user.name}
                <span className="ml-1 text-xs px-1.5 py-0.5 rounded bg-raised text-muted">
                  {user.type}
                </span>
              </button>
              {showProfile && (
                <div className="absolute top-full right-0 mt-2 w-64 bg-raised border border-border rounded-lg shadow-xl z-50 p-3 space-y-2">
                  <div className="text-xs text-muted uppercase tracking-wider mb-1">
                    Edit Profile
                  </div>
                  <input
                    type="text"
                    value={editDisplayName}
                    onChange={(e) => setEditDisplayName(e.target.value)}
                    placeholder="Display name"
                    className="w-full bg-surface border border-border rounded px-2 py-1.5 text-sm text-foreground focus:outline-none focus:border-brand"
                  />
                  <input
                    type="text"
                    value={editDescription}
                    onChange={(e) => setEditDescription(e.target.value)}
                    placeholder="Description"
                    className="w-full bg-surface border border-border rounded px-2 py-1.5 text-sm text-foreground focus:outline-none focus:border-brand"
                  />
                  {user.type === "human" && (
                    <input
                      type="password"
                      value={editPassword}
                      onChange={(e) => setEditPassword(e.target.value)}
                      placeholder="New password (min 8 chars)"
                      className="w-full bg-surface border border-border rounded px-2 py-1.5 text-sm text-foreground focus:outline-none focus:border-brand"
                    />
                  )}
                  {saveMsg && (
                    <div className={`text-xs ${saveMsg.includes("Failed") ? "text-red-400" : "text-green-400"}`}>
                      {saveMsg}
                    </div>
                  )}
                  <div className="flex gap-2">
                    <button
                      onClick={handleSaveProfile}
                      disabled={saving}
                      className="text-xs bg-brand hover:bg-brand-hover disabled:opacity-50 text-foreground px-3 py-1.5 rounded"
                    >
                      {saving ? "Saving..." : "Save"}
                    </button>
                    <button
                      onClick={() => setShowProfile(false)}
                      className="text-xs text-dim hover:text-foreground px-3 py-1.5"
                    >
                      Cancel
                    </button>
                  </div>
                </div>
              )}
              <button
                onClick={onLogout}
                className="text-sm text-dim hover:text-foreground"
              >
                Logout
              </button>
            </div>
          ) : (
            <Link
              href="/login"
              className="text-sm bg-brand hover:bg-brand-hover text-foreground px-3 py-1.5 rounded"
            >
              Register / Login
            </Link>
          )}
      </div>
    </header>
  );
}
