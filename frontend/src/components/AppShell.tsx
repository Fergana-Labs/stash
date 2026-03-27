"use client";

import { ReactNode } from "react";
import { User } from "../lib/types";
import AppSidebar from "./AppSidebar";
import Header from "./Header";

interface AppShellProps {
  user: User;
  onLogout: () => void;
  children: ReactNode;
}

export default function AppShell({ user, onLogout, children }: AppShellProps) {
  return (
    <div className="h-screen flex flex-col">
      <Header user={user} onLogout={onLogout} />
      <div className="flex-1 flex overflow-hidden">
        <AppSidebar />
        <main className="flex-1 overflow-y-auto">
          {children}
        </main>
      </div>
    </div>
  );
}
