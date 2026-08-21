"use client";

import { useState } from "react";

import DeveloperGate from "@/components/developer/DeveloperGate";
import { PageHeading, SectionHeading } from "@/components/developer/DocsPrimitives";
import KeyTable from "@/components/developer/KeyTable";
import MintKeyDialog from "@/components/developer/MintKeyDialog";
import SetupCard from "@/components/developer/SetupCard";

export default function DeveloperKeys() {
  // Bumped when the dialog mints, so the table picks up the new row.
  const [minted, setMinted] = useState(0);
  return (
    <DeveloperGate>
      <PageHeading title="API Keys">
        Keys are minted on the workspace itself — they are what your product&apos;s backend
        calls Stash with. Keys minted here follow the read contract: they can read the
        knowledge base and record sessions, and can never delete or rewrite anything.
      </PageHeading>
      <div className="mb-12">
        <div className="flex items-baseline justify-between gap-4">
          <SectionHeading>Your keys</SectionHeading>
          <MintKeyDialog onMinted={() => setMinted((n) => n + 1)} />
        </div>
        <div className="mt-4">
          <KeyTable refresh={minted} />
        </div>
      </div>
      <SetupCard />
    </DeveloperGate>
  );
}
