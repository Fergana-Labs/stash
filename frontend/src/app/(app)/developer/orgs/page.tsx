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
  const [orgs, setOrgs] = useState<Org[]>([]);

  const refresh = useCallback(() => {
    listOrgs()
      .then((res) => setOrgs(res.orgs))
      .catch(() => setOrgs([]));
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
      <OrgTable orgs={orgs} onChanged={refresh} />
    </div>
  );
}
