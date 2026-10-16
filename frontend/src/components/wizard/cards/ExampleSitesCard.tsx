"use client";

import { useState } from "react";
import { Globe } from "lucide-react";
import { CardShell } from "../wizard-ui";
import ExampleSites from "./ExampleSites";
import WebsiteEvalCard from "./WebsiteEvalCard";

/** First step of a website eval: example sites the user likes and ones they don't. */
export default function ExampleSitesCard() {
  const [done, setDone] = useState<{ text: string; jobId: string | null } | null>(null);
  if (done) {
    return (
      <>
        <CardShell icon={Globe} title="Your example sites"><p role="status" className="m-0 text-[12.5px] text-muted-foreground">{done.text}</p></CardShell>
        {/* Shows the build and opens the eval when its endpoint is ready. */}
        {done.jobId && <WebsiteEvalCard section="progress" jobId={done.jobId} />}
      </>
    );
  }
  return (
    <CardShell icon={Globe} title="Show it example sites" subtitle="Upload pages, then mark each one good or bad">
      <ExampleSites onDone={(text, jobId) => setDone({ text, jobId })} />
    </CardShell>
  );
}
