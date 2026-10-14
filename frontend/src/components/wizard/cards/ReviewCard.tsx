"use client";

import { useEffect, useState } from "react";
import { Inbox } from "lucide-react";
import { Button } from "@/components/ui/button";
import ItemView from "@/components/intuitions/ItemView";
import { errorMessage } from "@/components/reward-models/rm-text";
import { imGet, imLabelQueue, imReview, type QueueItem } from "@/lib/intuition-api";
import { CardShell, NeedsModel, pct, useWizard } from "../wizard-ui";

/** Recent predictions the model was least sure about; confirming or correcting one teaches it. */
export default function ReviewCard() {
  const { modelId, send, refresh } = useWizard();
  const [queue, setQueue] = useState<QueueItem[] | null>(null);
  const [labels, setLabels] = useState<string[]>([]);
  const [reviewed, setReviewed] = useState<Record<string, string>>({});
  const [error, setError] = useState("");

  useEffect(() => {
    if (!modelId) return;
    Promise.all([imGet(modelId), imLabelQueue(modelId)]).then(([d, q]) => {
      const v = d.active ?? d.draft;
      setLabels(d.model.output_type === "choice" ? (v?.labels ?? []).map((l) => l.id) : ["good", "bad"]);
      setQueue(q.filter((i) => i.kind === "predict"));
    }).catch((e) => setError(errorMessage(e)));
  }, [modelId]);

  if (!modelId) return <CardShell icon={Inbox} title="Review predictions"><NeedsModel /></CardShell>;

  async function review(item: QueueItem, label: string | null) {
    if (!modelId) return;
    try {
      await imReview(modelId, item.prediction_id, label === null ? { dismiss: true } : { label });
      setReviewed((r) => ({ ...r, [item.prediction_id]: label ?? "dismissed" }));
    } catch (e) { setError(errorMessage(e)); }
  }

  const open = (queue ?? []).filter((q) => !reviewed[q.prediction_id]);
  const corrections = Object.entries(reviewed).filter(([id, l]) => l !== "dismissed" && queue?.find((q) => q.prediction_id === id)?.predicted !== l).length;

  return (
    <CardShell
      icon={Inbox}
      title="Review predictions"
      subtitle={queue ? `${open.length} to review · least confident first` : "Loading…"}
      actions={Object.keys(reviewed).length > 0 ? <Button size="xs" variant="ghost" onClick={() => { refresh(); send(`Reviewed ${Object.keys(reviewed).length} predictions; corrected ${corrections}.`, "event"); }}>Done</Button> : undefined}
    >
      {error && <p role="alert" className="m-0 mb-2 text-[11.5px] text-destructive">{error}</p>}
      {queue && open.length === 0 && <p className="m-0 text-[12px] text-muted-foreground">{queue.length ? "All caught up." : "No predictions yet. Try inputs in the playground or call the API, and they show up here."}</p>}
      <ul className="m-0 list-none space-y-2 p-0">
        {open.slice(0, 5).map((q) => (
          <li key={q.prediction_id} className="rounded-md border border-border p-2.5">
            <ItemView item={q.input.item} />
            <div className="mt-2 flex flex-wrap items-center gap-1.5 text-[12px]">
              <span className="text-muted-foreground">Said <b className="text-foreground">{q.predicted}</b> ({pct(q.confidence)}). Correct label:</span>
              {labels.map((l) => <Button key={l} size="xs" variant={l === q.predicted ? "secondary" : "outline"} onClick={() => void review(q, l)}>{l}</Button>)}
              <Button size="xs" variant="ghost" onClick={() => void review(q, null)}>Skip</Button>
            </div>
          </li>
        ))}
      </ul>
    </CardShell>
  );
}
