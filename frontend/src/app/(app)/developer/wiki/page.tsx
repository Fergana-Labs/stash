"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import DeveloperGate from "@/components/developer/DeveloperGate";
import { listTenants } from "@/lib/api";

export default function DeveloperWiki() {
  return (
    <DeveloperGate>
      <WikiRedirect />
    </DeveloperGate>
  );
}

/** The wiki is an ordinary (protected) folder — this route just resolves its
 *  id and forwards to the folder view, so the rail has a stable Wiki entry. */
function WikiRedirect() {
  const router = useRouter();
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listTenants()
      .then((res) => {
        router.replace(`/folders/${res.workspace.external_wiki_folder_id}`);
      })
      .catch((e) => setError(e instanceof Error ? e.message : "Failed to open the wiki"));
  }, [router]);

  if (error) {
    return <p className="text-[15px] text-error">Couldn&apos;t open the wiki: {error}</p>;
  }

  return <p className="text-[15px] text-muted-foreground">Opening the wiki…</p>;
}
