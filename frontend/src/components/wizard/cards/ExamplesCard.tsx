"use client";

import { useEffect, useState } from "react";
import { Table2 } from "lucide-react";
import { examplePreview } from "@/components/evals/eval-ui";
import { errorMessage } from "@/components/reward-models/rm-text";
import { imExamples, type Example } from "@/lib/intuition-api";
import { CardShell, NeedsModel, useWizard } from "../wizard-ui";

/** Every example with its label, split and source. */
export default function ExamplesCard() {
  const { modelId, version } = useWizard();
  const [examples, setExamples] = useState<Example[] | null>(null);
  const [error, setError] = useState("");
  useEffect(() => { if (modelId) imExamples(modelId).then(setExamples).catch((e) => setError(errorMessage(e))); }, [modelId, version]);
  if (!modelId) return <CardShell icon={Table2} title="Examples"><NeedsModel /></CardShell>;
  return (
    <CardShell icon={Table2} title="Examples" subtitle={examples ? `${examples.length} total · ${examples.filter((e) => e.split === "eval").length} held out` : "Loading…"}>
      {error && <p role="alert" className="m-0 text-[11.5px] text-destructive">{error}</p>}
      <div className="max-h-72 overflow-auto rounded border border-border">
        <table className="w-full text-left text-[12px]">
          <thead className="sticky top-0 bg-surface text-muted-foreground"><tr className="[&>th]:px-2.5 [&>th]:py-1.5 [&>th]:font-medium"><th>Example</th><th>Label</th><th>Split</th><th>Source</th></tr></thead>
          <tbody>
            {(examples ?? []).map((e) => (
              <tr key={e.id} className="border-t border-border [&>td]:px-2.5 [&>td]:py-1.5">
                <td className="max-w-[22rem] truncate">{typeof e.item === "object" && e.item.kind === "image" ? `🖼 ${String(e.item.name ?? "image")}` : examplePreview(e.item)}</td>
                <td>{e.needs_review ? <span className="text-muted-foreground">{e.label ? `${e.label}?` : "—"}</span> : e.label}</td>
                <td className="text-muted-foreground">{e.split === "eval" ? "held out" : "train"}</td>
                <td className="text-muted-foreground">{e.note.startsWith("Adversarial repair") ? "repair" : e.source}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </CardShell>
  );
}
