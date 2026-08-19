"use client";

import { useCallback, useEffect, useState } from "react";

import DeveloperGate from "@/components/developer/DeveloperGate";
import OrgTable from "@/components/developer/OrgTable";
import { listOrgs } from "@/lib/api";
import type { Org } from "@/lib/types";

export default function DeveloperOrgs() {
  return (
    <DeveloperGate>
      <Orgs />
    </DeveloperGate>
  );
}

function Orgs() {
  const [orgs, setOrgs] = useState<Org[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(() => {
    setError(null);
    listOrgs()
      .then((res) => setOrgs(res.orgs))
      .catch((e) => setError(e instanceof Error ? e.message : "Failed to load orgs"));
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  return (
    <div className="mx-auto max-w-4xl space-y-4 p-8">
      <div>
        <h1 className="text-xl font-semibold">Orgs</h1>
        <p className="mt-1 text-sm text-zinc-500">
          Your customers. Each has a private notepad; the wiki toggle controls
          whether their sessions feed the shared anonymized wiki.
        </p>
      </div>
      {error ? (
        <p className="text-sm text-destructive">Couldn&apos;t load orgs: {error}</p>
      ) : orgs === null ? (
        <p className="text-sm text-zinc-500">Loading…</p>
      ) : (
        <OrgTable orgs={orgs} onChanged={refresh} />
      )}
    </div>
  );
}
