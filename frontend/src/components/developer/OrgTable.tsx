"use client";

import { useState } from "react";
import Link from "next/link";
import { Building2, NotebookPen } from "lucide-react";

import { updateOrg } from "@/lib/api";
import type { Org } from "@/lib/types";
import { cn } from "@/lib/utils";

export default function OrgTable({ orgs, onChanged }: { orgs: Org[]; onChanged: () => void }) {
  if (orgs.length === 0) {
    return (
      <p className="rounded-lg border border-dashed border-zinc-200 p-6 text-sm text-zinc-500">
        No orgs yet. Orgs appear automatically the first time your backend
        uploads a session with a new <code>org_id</code>.
      </p>
    );
  }
  return (
    <div className="divide-y divide-zinc-200 rounded-lg border border-zinc-200 bg-white">
      {orgs.map((org) => (
        <OrgRow key={org.id} org={org} onChanged={onChanged} />
      ))}
    </div>
  );
}

function OrgRow({ org, onChanged }: { org: Org; onChanged: () => void }) {
  const [saving, setSaving] = useState(false);

  async function toggleWiki() {
    setSaving(true);
    try {
      await updateOrg(org.id, { share_wiki: !org.share_wiki });
      onChanged();
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="flex items-center gap-3 px-4 py-3">
      <Building2 className="h-4 w-4 shrink-0 text-zinc-900" />
      <div className="min-w-0 flex-1">
        <div className="truncate text-sm font-medium">{org.name}</div>
        <div className="truncate text-xs text-zinc-500">
          {org.external_id} · {org.session_count} session
          {org.session_count === 1 ? "" : "s"}
          {org.last_session_at &&
            ` · last ${new Date(org.last_session_at).toLocaleDateString()}`}
        </div>
      </div>
      <Link
        href={`/folders/${org.notepad_folder_id}`}
        className="flex items-center gap-1 rounded-md border border-zinc-200 px-2 py-1 text-xs hover:bg-zinc-50"
      >
        <NotebookPen className="h-3.5 w-3.5" />
        Notepad
      </Link>
      <button
        onClick={toggleWiki}
        disabled={saving}
        title="Whether this org's sessions feed the shared anonymized wiki"
        className={cn(
          "rounded-md border px-2 py-1 text-xs",
          org.share_wiki
            ? "border-zinc-900 bg-zinc-900 text-white"
            : "border-zinc-200 text-zinc-500",
        )}
      >
        {org.share_wiki ? "Feeds wiki" : "Wiki opt-out"}
      </button>
    </div>
  );
}
