"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import BrainDashboard from "@/components/memory/BrainDashboard";
import { isDeveloperView } from "@/lib/scope-store";

// Home is the memory dashboard — the shell renders the Memory explorer beside
// this route's content: the curator's briefing plus the wiki views. In a
// Developer Console context the console IS home, so this route forwards there
// instead of showing the consumer dashboard inside developer chrome.
export default function HomeRoute() {
  const router = useRouter();
  const developer = isDeveloperView();

  useEffect(() => {
    if (developer) router.replace("/developer");
  }, [developer, router]);

  if (developer) return null;
  return <BrainDashboard />;
}
