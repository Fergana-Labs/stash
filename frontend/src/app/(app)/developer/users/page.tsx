"use client";

import { useCallback, useEffect, useState } from "react";

import DeveloperGate from "@/components/developer/DeveloperGate";
import { PageHeading } from "@/components/developer/DocsPrimitives";
import UserTable from "@/components/developer/UserTable";
import { listTenants } from "@/lib/api";
import type { Tenant } from "@/lib/types";

export default function DeveloperUsers() {
  return (
    <DeveloperGate>
      <Users />
    </DeveloperGate>
  );
}

function Users() {
  const [users, setUsers] = useState<Tenant[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(() => {
    setError(null);
    listTenants()
      .then((res) => setUsers(res.tenants))
      .catch((e) => setError(e instanceof Error ? e.message : "Failed to load users"));
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  return (
    <>
      <PageHeading title="Users">
        One end user of your product each — a company, or one person. Each has a private
        wiki of their own; the switch controls whether their sessions also feed the shared
        anonymized wiki.
      </PageHeading>
      {error ? (
        <p className="text-[15px] text-error">Couldn&apos;t load users: {error}</p>
      ) : users === null ? (
        <p className="text-[15px] text-muted-foreground">Loading…</p>
      ) : (
        <UserTable tenants={users} onChanged={refresh} />
      )}
    </>
  );
}
