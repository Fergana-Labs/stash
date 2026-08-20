"use client";

import { useCallback, useEffect, useState } from "react";

import DeveloperGate from "@/components/developer/DeveloperGate";
import { PageHeading } from "@/components/developer/DocsPrimitives";
import TenantTable from "@/components/developer/TenantTable";
import { listTenants } from "@/lib/api";
import type { Tenant } from "@/lib/types";

export default function DeveloperOrgs() {
  return (
    <DeveloperGate>
      <Tenants />
    </DeveloperGate>
  );
}

function Tenants() {
  const [tenants, setOrgs] = useState<Tenant[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(() => {
    setError(null);
    listTenants()
      .then((res) => setOrgs(res.tenants))
      .catch((e) => setError(e instanceof Error ? e.message : "Failed to load tenants"));
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  return (
    <>
      <PageHeading title="Tenants">
        One end user of your product each — a company, or one person. Each has a private
          notepad; the wiki toggle controls whether their
        sessions feed the shared anonymized wiki.
      </PageHeading>
      {error ? (
        <p className="text-[15px] text-error">Couldn&apos;t load tenants: {error}</p>
      ) : tenants === null ? (
        <p className="text-[15px] text-muted-foreground">Loading…</p>
      ) : (
        <TenantTable tenants={tenants} onChanged={refresh} />
      )}
    </>
  );
}
