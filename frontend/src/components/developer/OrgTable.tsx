"use client";

import Link from "next/link";
import { ChevronRight } from "lucide-react";

import { Code } from "@/components/developer/DocsPrimitives";
import WikiToggle from "@/components/developer/WikiToggle";
import type { Org } from "@/lib/types";

export default function OrgTable({ orgs, onChanged }: { orgs: Org[]; onChanged: () => void }) {
  if (orgs.length === 0) {
    return (
      <p className="rounded-2xl border border-dashed border-border px-6 py-10 text-center text-[15px] leading-7 text-muted-foreground">
        No orgs yet. Orgs appear automatically the first time your backend uploads a session
        with a new <Code>org_id</Code>.
      </p>
    );
  }
  return (
    <div className="overflow-hidden rounded-2xl border border-border bg-surface">
      {orgs.map((org) => (
        <Link
          key={org.id}
          href={`/developer/orgs/${org.id}`}
          className="flex items-center gap-4 border-b border-border px-5 py-4 transition-colors last:border-b-0 hover:bg-raised"
        >
          <span className="min-w-0 flex-1">
            <span className="block truncate text-[15px] font-medium text-foreground">
              {org.name}
            </span>
            <span className="mt-0.5 block truncate font-mono text-[12px] text-muted-foreground">
              {org.external_id} · {org.session_count} session
              {org.session_count === 1 ? "" : "s"}
              {org.last_session_at &&
                ` · last ${new Date(org.last_session_at).toLocaleDateString()}`}
            </span>
          </span>
          <WikiToggle org={org} onChanged={onChanged} />
          <ChevronRight className="h-4 w-4 shrink-0 text-muted-foreground" />
        </Link>
      ))}
    </div>
  );
}
