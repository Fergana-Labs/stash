"use client";

import { ReactNode } from "react";

interface DashboardSectionProps {
  title: string;
  loading?: boolean;
  empty?: boolean;
  emptyMessage?: string;
  children: ReactNode;
}

export default function DashboardSection({
  title,
  loading,
  empty,
  emptyMessage,
  children,
}: DashboardSectionProps) {
  return (
    <div className="bg-surface border border-border rounded-lg overflow-hidden">
      <div className="px-4 py-2.5 border-b border-border">
        <span className="text-[11px] font-mono font-medium text-muted uppercase tracking-[0.05em]">
          {title}
        </span>
      </div>
      {loading ? (
        <div className="h-[200px] flex items-center justify-center">
          <span className="text-xs text-muted">Loading...</span>
        </div>
      ) : empty ? (
        <div className="h-[200px] flex items-center justify-center px-6">
          <p className="text-xs text-muted text-center">{emptyMessage || "No data yet."}</p>
        </div>
      ) : (
        children
      )}
    </div>
  );
}
