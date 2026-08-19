"use client";

import { useState } from "react";
import Link from "next/link";

import { Code } from "@/components/developer/DocsPrimitives";
import { updateOrg } from "@/lib/api";
import type { Org } from "@/lib/types";
import { cn } from "@/lib/utils";

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
        <OrgRow key={org.id} org={org} onChanged={onChanged} />
      ))}
    </div>
  );
}

function OrgRow({ org, onChanged }: { org: Org; onChanged: () => void }) {
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function toggleWiki() {
    setSaving(true);
    setError(null);
    try {
      await updateOrg(org.id, { share_wiki: !org.share_wiki });
      onChanged();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not change the wiki setting");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="border-b border-border px-5 py-4 last:border-b-0">
      <div className="flex items-center gap-4">
        <div className="min-w-0 flex-1">
          <div className="truncate text-[15px] font-medium text-foreground">{org.name}</div>
          <div className="mt-0.5 truncate font-mono text-[12px] text-muted-foreground">
            {org.external_id} · {org.session_count} session
            {org.session_count === 1 ? "" : "s"}
            {org.last_session_at &&
              ` · last ${new Date(org.last_session_at).toLocaleDateString()}`}
          </div>
        </div>
        <Link
          href={`/folders/${org.notepad_folder_id}`}
          className="shrink-0 rounded-lg border border-border px-3 py-1.5 text-[13px] text-dim transition-colors hover:bg-raised hover:text-foreground"
        >
          Notepad
        </Link>
        <button
          onClick={toggleWiki}
          disabled={saving}
          title="Whether this org's sessions feed the shared anonymized wiki"
          className={cn(
            "shrink-0 rounded-lg px-3 py-1.5 text-[13px] transition-colors disabled:opacity-50",
            org.share_wiki
              ? "bg-brand-500/10 font-medium text-brand-500"
              : "border border-border text-muted-foreground hover:bg-raised",
          )}
        >
          {org.share_wiki ? "Feeds wiki" : "Wiki opt-out"}
        </button>
      </div>
      {error && <p className="mt-2 text-[13px] text-error">{error}</p>}
    </div>
  );
}
