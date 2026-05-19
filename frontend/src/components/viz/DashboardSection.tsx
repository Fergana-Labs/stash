"use client";

import { ReactNode } from "react";
import { SkeletonBlock } from "../SkeletonStates";

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
    <div className="bg-surface border border-border rounded-lg overflow-visible">
      <div className="px-4 py-2.5 border-b border-border">
        <span className="text-[11px] font-mono font-medium text-muted uppercase tracking-[0.05em]">
          {title}
        </span>
      </div>
      {loading ? (
        <div className="h-[200px] p-4">
          <SkeletonBlock className="h-full w-full" />
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
