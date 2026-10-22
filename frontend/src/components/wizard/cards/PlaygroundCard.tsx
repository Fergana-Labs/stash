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
import { LabelPicker, labelSpace, showLabel } from "../labels";

/** Try any input -- text, JSON, an image or document -- and see the decision and why. */
export default function PlaygroundCard({ item: initialItem, prediction: initialPrediction, editable = false, title = "Try it" }: { item?: Item; prediction?: Prediction; editable?: boolean; title?: string }) {
  const { modelId, send, refresh, version } = useWizard();
  const [detail, setDetail] = useState<ModelDetail | null>(null);
  const [item, setItem] = useState<Item | null>(initialItem ?? null);
  const [prediction, setPrediction] = useState<Prediction | null>(initialPrediction ?? null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [corrected, setCorrected] = useState("");
  const [pick, setPick] = useState<string | null>(null);
  // The wizard's try_item opens the card on its input; "Try another" switches to free input.
  const [fixed, setFixed] = useState(initialItem !== undefined && !editable);

  useEffect(() => { if (modelId) imGet(modelId).then(setDetail).catch((e) => setError(errorMessage(e))); }, [modelId, version]);
  if (!modelId) return <CardShell icon={FlaskConical} title={title}><NeedsModel /></CardShell>;

  const draftReady = detail?.draft && !detail.draft.head_stale;
  const which: "draft" | "active" = draftReady ? "draft" : "active";
  const served = which === "draft" ? detail?.draft : detail?.active;
  const space = detail ? labelSpace(detail) : null;
  const multi = space?.kind === "multi";
  // Multi-issue: explain the issue it is most sure about; otherwise the chosen label.
  const explained = prediction && multi ? Object.entries(prediction.probabilities).sort((a, b) => b[1] - a[1])[0]?.[0] : prediction?.label;

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
      send(`Added a playground input as a labeled example (${showLabel(label)}); the model had said ${showLabel(prediction?.label)}.`, "event");
    } catch (e) { setError(errorMessage(e)); }
  }

  return (
    <CardShell icon={FlaskConical} title={title} subtitle={detail ? `${which === "draft" ? "Trained draft" : "Live version"}${served ? ` v${served.number}` : ""}` : undefined}>
      {detail && !served?.head && !draftReady && <p className="m-0 mb-2 text-[12px] text-muted-foreground">Train the model first; then try inputs here.</p>}
      {fixed && item !== null ? <ItemView item={item} className="mb-2" /> : <EvalInput initialItem={editable ? initialItem ?? null : null} onChange={(next) => { setItem(next); setPrediction(null); setCorrected(""); setPick(null); }} disabled={busy} />}
      <div className="mt-2 flex gap-2">
        <Button size="sm" disabled={busy || item === null || !(draftReady || detail?.active)} onClick={() => void run()}>{busy ? "Running…" : prediction ? "Run again" : "Run"}</Button>
        {fixed && <Button size="sm" variant="ghost" onClick={() => { setFixed(false); setPrediction(null); setItem(null); }}>Try another</Button>}
      </div>
      {error && <p role="alert" className="m-0 mt-2 text-[11.5px] text-destructive">{error}</p>}
      {prediction && served && (
        <div className="mt-3 space-y-3 border-t border-border pt-3">
          <p className="m-0 text-[13px]"><span className="font-semibold">{showLabel(prediction.label, space?.kind)}</span> <span className="text-muted-foreground">{pct(prediction.confidence)} confident</span></p>
          {multi && <p className="m-0 text-[11px] text-muted-foreground">Each bar is the chance that issue applies, judged independently.</p>}
          <ProbabilityBars probabilities={prediction.probabilities} highlight={multi ? undefined : prediction.label} />
          <div>
            <div className="mb-1 text-[10.5px] font-medium tracking-wide text-muted-foreground uppercase">Why{multi && explained ? ` (${explained})` : ""}</div>
            <ContributionBars contributions={(explained && prediction.contributions[explained]) || prediction.contributions.score} rubric={served.rubric} limit={5} />
          </div>
          <div className="space-y-1.5 text-[12px] text-muted-foreground">
            {corrected ? <span>Saved as {showLabel(corrected)}. It will learn from it next time you train.</span> : space && <>
              <span>Wrong? Save the right answer as an example:</span>
              <LabelPicker space={space} value={pick} keyboard={false} commitLabel="Save as example" onPick={(label, go) => { setPick(label); if (go) void correct(label); }} />
            </>}
          </div>
        </div>
      )}
    </CardShell>
  );
}
