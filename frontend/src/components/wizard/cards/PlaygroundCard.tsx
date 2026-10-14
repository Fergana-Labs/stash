"use client";

import { useEffect, useState } from "react";
import { FlaskConical } from "lucide-react";
import { Button } from "@/components/ui/button";
import EvalInput from "@/components/evals/EvalInput";
import ItemView from "@/components/intuitions/ItemView";
import { ContributionBars, ProbabilityBars } from "@/components/intuitions/ProbabilityBars";
import { errorMessage } from "@/components/reward-models/rm-text";
import { imAddExamples, imGet, imPredict, type Item, type ModelDetail, type Prediction } from "@/lib/intuition-api";
import { CardShell, NeedsModel, pct, useWizard } from "../wizard-ui";

/** Try any input -- text, JSON, an image or document -- and see the decision and why. */
export default function PlaygroundCard({ item: initialItem, prediction: initialPrediction }: { item?: Item; prediction?: Prediction }) {
  const { modelId, send, refresh, version } = useWizard();
  const [detail, setDetail] = useState<ModelDetail | null>(null);
  const [item, setItem] = useState<Item | null>(initialItem ?? null);
  const [prediction, setPrediction] = useState<Prediction | null>(initialPrediction ?? null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [corrected, setCorrected] = useState("");
  // The wizard's try_item opens the card on its input; "Try another" switches to free input.
  const [fixed, setFixed] = useState(initialItem !== undefined);

  useEffect(() => { if (modelId) imGet(modelId).then(setDetail).catch((e) => setError(errorMessage(e))); }, [modelId, version]);
  if (!modelId) return <CardShell icon={FlaskConical} title="Try it"><NeedsModel /></CardShell>;

  const draftReady = detail?.draft && !detail.draft.head_stale;
  const which: "draft" | "active" = draftReady ? "draft" : "active";
  const served = which === "draft" ? detail?.draft : detail?.active;
  const labels = detail?.model.output_type === "choice" ? (served?.labels ?? []).map((l) => l.id) : ["good", "bad"];

  async function run() {
    if (!modelId || item === null) return;
    setBusy(true); setError(""); setCorrected("");
    try { setPrediction(await imPredict(modelId, item, which)); } catch (e) { setError(errorMessage(e)); } finally { setBusy(false); }
  }

  async function correct(label: string) {
    if (!modelId || item === null) return;
    try {
      await imAddExamples(modelId, [{ item, label }]);
      setCorrected(label); refresh();
      send(`Added a playground input as a labeled example (${label}); the model had said ${prediction?.label}.`, "event");
    } catch (e) { setError(errorMessage(e)); }
  }

  return (
    <CardShell icon={FlaskConical} title="Try it" subtitle={detail ? `${which === "draft" ? "Trained draft" : "Live version"}${served ? ` v${served.number}` : ""}` : undefined}>
      {detail && !served?.head && !draftReady && <p className="m-0 mb-2 text-[12px] text-muted-foreground">Train the model first; then try inputs here.</p>}
      {fixed && item !== null ? <ItemView item={item} className="mb-2" /> : <EvalInput initialItem={null} onChange={setItem} disabled={busy} />}
      <div className="mt-2 flex gap-2">
        <Button size="sm" disabled={busy || item === null || !(draftReady || detail?.active)} onClick={() => void run()}>{busy ? "Running…" : prediction ? "Run again" : "Run"}</Button>
        {fixed && <Button size="sm" variant="ghost" onClick={() => { setFixed(false); setPrediction(null); setItem(null); }}>Try another</Button>}
      </div>
      {error && <p role="alert" className="m-0 mt-2 text-[11.5px] text-destructive">{error}</p>}
      {prediction && served && (
        <div className="mt-3 space-y-3 border-t border-border pt-3">
          <p className="m-0 text-[13px]"><span className="font-semibold">{prediction.label}</span> <span className="text-muted-foreground">· {pct(prediction.confidence)} confident</span></p>
          <ProbabilityBars probabilities={prediction.probabilities} highlight={prediction.label} />
          <div>
            <div className="mb-1 text-[10.5px] font-medium tracking-wide text-muted-foreground uppercase">Why</div>
            <ContributionBars contributions={prediction.contributions[prediction.label] ?? prediction.contributions.score} rubric={served.rubric} limit={5} />
          </div>
          <div className="flex flex-wrap items-center gap-1.5 text-[12px] text-muted-foreground">
            {corrected ? <span>Saved as {corrected}. It will learn from it next time you train.</span> : <>
              <span>Should be:</span>
              {labels.map((l) => <Button key={l} size="xs" variant="outline" onClick={() => void correct(l)}>{l}</Button>)}
            </>}
          </div>
        </div>
      )}
    </CardShell>
  );
}
