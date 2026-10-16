"use client";

import { useState } from "react";
import { Globe } from "lucide-react";
import { CardShell } from "../wizard-ui";
import ExampleSites from "./ExampleSites";

/** First step of a website eval: example sites the user likes and ones they don't. */
export default function ExampleSitesCard() {
  const [done, setDone] = useState("");
  if (done) return <CardShell icon={Globe} title="Your example sites"><p role="status" className="m-0 text-[12.5px] text-muted-foreground">{done}</p></CardShell>;
  return (
    <CardShell icon={Globe} title="Show it example sites" subtitle="Websites you like and ones you don’t: URLs, HTML files, or screenshots">
      <ExampleSites onDone={setDone} />
    </CardShell>
  );
}
