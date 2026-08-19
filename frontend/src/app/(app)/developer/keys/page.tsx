"use client";

import DeveloperGate from "@/components/developer/DeveloperGate";
import SetupCard from "@/components/developer/SetupCard";

export default function DeveloperKeys() {
  return (
    <DeveloperGate>
      <div className="mx-auto max-w-3xl space-y-4 p-8">
        <div>
          <h1 className="text-xl font-semibold">API Keys &amp; Setup</h1>
          <p className="mt-1 text-sm text-zinc-500">
            Keys are minted on the workspace itself — they are what your
            product&apos;s backend calls Stash with.
          </p>
        </div>
        <SetupCard />
      </div>
    </DeveloperGate>
  );
}
