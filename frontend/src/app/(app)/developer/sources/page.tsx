"use client";

import DeveloperGate from "@/components/developer/DeveloperGate";
import { PageHeading } from "@/components/developer/DocsPrimitives";
import SourceConnectorList from "@/components/integrations/SourceConnectorList";

export default function DeveloperSources() {
  return (
    <DeveloperGate>
      <PageHeading title="Sources">
        Connect accounts and choose the sources your product&apos;s agents can read.
      </PageHeading>
      <SourceConnectorList returnTo="/developer/sources" />
    </DeveloperGate>
  );
}
