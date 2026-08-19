"use client";

import { useCallback, useEffect, useState } from "react";

import DeveloperGate from "@/components/developer/DeveloperGate";
import { PageHeading } from "@/components/developer/DocsPrimitives";
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
    <>
      <PageHeading title="Orgs">
        Your customers. Each has a private notepad; the wiki toggle controls whether their
        sessions feed the shared anonymized wiki.
      </PageHeading>
      {error ? (
        <p className="text-[15px] text-error">Couldn&apos;t load orgs: {error}</p>
      ) : orgs === null ? (
        <p className="text-[15px] text-muted-foreground">Loading…</p>
      ) : (
        <OrgTable orgs={orgs} onChanged={refresh} />
      )}
    </>
  );
}
