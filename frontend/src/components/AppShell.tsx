"use client";

import { ReactNode } from "react";
import { User } from "../lib/types";
import AppSidebar from "./AppSidebar";
import TopBar from "./TopBar";
import { BreadcrumbProvider } from "./BreadcrumbContext";

interface AppShellProps {
  user: User;
  onLogout: () => void;
  children: ReactNode;
}

export default function AppShell({ user, onLogout, children }: AppShellProps) {
  return (
    <BreadcrumbProvider>
      <div className="flex h-screen overflow-hidden">
        <AppSidebar user={user} />
        <main className="flex flex-1 flex-col overflow-hidden">
          <TopBar user={user} onLogout={onLogout} />
          <div className="flex-1 overflow-y-auto">{children}</div>
        </main>
      </div>
    </BreadcrumbProvider>
  );
}
