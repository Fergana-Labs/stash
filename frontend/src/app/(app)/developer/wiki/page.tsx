"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

import DeveloperGate from "@/components/developer/DeveloperGate";
import { listOrgs } from "@/lib/api";

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

  useEffect(() => {
    listOrgs().then((res) => {
      router.replace(`/folders/${res.workspace.external_wiki_folder_id}`);
    });
  }, [router]);

  return <div className="p-8 text-sm text-zinc-500">Opening the wiki…</div>;
}
