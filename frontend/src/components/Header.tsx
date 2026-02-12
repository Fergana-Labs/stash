"use client";

import Link from "next/link";
import { User } from "../lib/types";

interface HeaderProps {
  user: User | null;
  onLogout?: () => void;
}

export default function Header({ user, onLogout }: HeaderProps) {
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
            <div className="flex items-center gap-3">
              <span className="text-sm text-gray-400">
                {user.display_name || user.name}
                <span className="ml-1 text-xs px-1.5 py-0.5 rounded bg-gray-800 text-gray-500">
                  {user.type}
                </span>
              </span>
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
