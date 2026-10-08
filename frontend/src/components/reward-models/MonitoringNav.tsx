"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";

export default function MonitoringNav() {
  const path = usePathname();
  return <nav aria-label="Monitoring" className="mb-5 flex gap-5 border-b border-border text-sm">
    {[["/reward-models/monitoring", "Performance"], ["/skills", "Current skills"], ["/reward-models/changes", "Changes"], ["/reward-models/review", "Feedback"]].map(([href, label]) => <Link key={href} href={href} aria-current={path === href ? "page" : undefined} className={cn("border-b-2 py-2", path === href ? "border-foreground font-medium" : "border-transparent text-muted-foreground hover:text-foreground")}>{label}</Link>)}
  </nav>;
}
