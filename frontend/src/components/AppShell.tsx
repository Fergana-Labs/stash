"use client";

import { ReactNode } from "react";
import { User } from "../lib/types";
import AppSidebar from "./AppSidebar";
import CollectTray from "./share/CollectTray";
import TopBar from "./TopBar";

interface AppShellProps {
  user: User;
  onLogout: () => void;
  onAddToStash?: () => void;
  addToStashDisabled?: boolean;
  children: ReactNode;
}

export default function AppShell({
  user,
  onLogout,
  onAddToStash,
  addToStashDisabled,
  children,
}: AppShellProps) {
  return (
    <div className="flex h-screen overflow-hidden">
      <AppSidebar
        user={user}
        onLogout={onLogout}
        onAddToStash={onAddToStash}
        addToStashDisabled={addToStashDisabled}
      />
      <main className="flex flex-1 flex-col overflow-hidden">
        <TopBar />
        <div className="flex-1 overflow-y-auto">{children}</div>
      </main>
      <CollectTray />
    </div>
  );
}
