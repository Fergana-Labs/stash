"use client";

import { useState } from "react";
import { Globe } from "lucide-react";
import { CardShell } from "../wizard-ui";
import ExampleSites from "./ExampleSites";
import WebsiteEvalCard from "./WebsiteEvalCard";

/** First step of a website eval: example sites the user likes and ones they don't. */
export default function ExampleSitesCard() {
  // undefined until uploaded; then the build job, if one started.
  const [jobId, setJobId] = useState<string | null | undefined>(undefined);
  // The chat already confirms what was added; only follow the build from here.
  if (jobId !== undefined) return jobId ? <WebsiteEvalCard section="progress" jobId={jobId} /> : null;
  return (
    <CardShell icon={Globe} title="Show it example sites" subtitle="Upload pages, then mark each one good or bad">
      <ExampleSites onDone={(_text, job) => setJobId(job)} />
    </CardShell>
  );
}
