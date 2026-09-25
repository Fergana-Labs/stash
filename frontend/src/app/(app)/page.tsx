"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import BrainDashboard from "@/components/home/BrainDashboard";
import { isDeveloperView } from "@/lib/scope-store";

// Developer Console has its own home; personal scopes show the Skills dashboard.
export default function HomeRoute() {
  const router = useRouter();
  const developer = isDeveloperView();

  useEffect(() => {
    if (developer) router.replace("/developer");
  }, [developer, router]);

  if (developer) return null;
  return <BrainDashboard />;
}
