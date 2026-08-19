"use client";

import DeveloperGate from "@/components/developer/DeveloperGate";
import { PageHeading } from "@/components/developer/DocsPrimitives";
import SetupCard from "@/components/developer/SetupCard";

export default function DeveloperKeys() {
  return (
    <DeveloperGate>
      <PageHeading title="API Keys">
        Keys are minted on the workspace itself — they are what your product&apos;s backend
        calls Stash with.
      </PageHeading>
      <SetupCard />
    </DeveloperGate>
  );
}
