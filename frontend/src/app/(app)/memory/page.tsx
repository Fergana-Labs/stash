"use client";

import BrainDashboard from "@/components/memory/BrainDashboard";

// Memory is a workspace section — the shell renders the explorer beside this
// route's content: the brain dashboard as the section's landing view.
export default function MemoryRoute() {
  return <BrainDashboard />;
}
