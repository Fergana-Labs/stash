"use client";

import BrainDashboard from "@/components/memory/BrainDashboard";

// Home is the memory dashboard — the shell renders the Memory explorer beside
// this route's content: the curator's briefing plus the wiki views.
export default function HomeRoute() {
  return <BrainDashboard />;
}
