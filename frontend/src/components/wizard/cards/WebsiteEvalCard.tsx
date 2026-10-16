"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { Sparkles } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog";
import { errorMessage } from "@/components/reward-models/rm-text";
import {
  tasteGet,
  tasteReview,
  tasteInspect,
  tasteCheckpoint,
  tasteCompare,
  type TasteWorkspace,
} from "@/lib/taste-api";
import {
  CopyText,
  Design,
  Picture,
  ReviewCard,
} from "@/components/taste/website-eval-ui";
import { CardShell, useWizard } from "../wizard-ui";

type Section =
  | "preferences"
  | "grader"
  | "connect"
  | "experiments"
  | "results"
  | "progress";
const titles: Record<Section, string> = {
  preferences: "Your preferences",
  grader: "Your eval",
  connect: "Use this eval with your agent",
  experiments: "Improve your agent",
  results: "Compare the designs",
  progress: "Working on your eval",
};
export default function WebsiteEvalCard({
  section = "preferences",
  jobId,
  exampleIds,
  readOnly = false,
}: {
  section?: Section;
  jobId?: string;
  exampleIds?: string[];
  readOnly?: boolean;
}) {
  const { send, refresh, busy } = useWizard();
  const [data, setData] = useState<TasteWorkspace | null>(null);
  const [error, setError] = useState("");
  const [brief, setBrief] = useState("research");
  const [pair, setPair] = useState<string[]>([]);
  const [preferenceSaved, setPreferenceSaved] = useState(false);
  const [inspection, setInspection] = useState<{
    id: string;
    kind: string;
    data: Record<string, unknown> | null;
  } | null>(null);
  const [ids, setIds] = useState<string[] | null>(null);
  const completed = useRef(false);
  const reload = useCallback(async () => {
    try {
      const next = await tasteGet();
      setData(next);
      if (next && ids === null)
        setIds(
          exampleIds ??
            next.examples
              .filter((e) => !e.reviewed)
              .slice(0, 3)
              .map((e) => e.id),
        );
    } catch (e) {
      setError(errorMessage(e));
    }
  }, [exampleIds, ids]);
  useEffect(() => {
    void reload();
    const timer = setInterval(() => void reload(), 3000);
    return () => clearInterval(timer);
  }, [reload]);
  useEffect(() => {
    if (!jobId || !data || completed.current) return;
    const job = data.jobs.find((j) => j.id === jobId);
    if (!job || !["succeeded", "failed"].includes(job.status)) return;
    const key = "website-eval-job:" + jobId;
    if (sessionStorage.getItem(key)) return;
    completed.current = true;
    sessionStorage.setItem(key, "seen");
    send(
      `Website eval background job ${jobId} (${job.operation}) ${job.status}. Read website_eval status and continue from the saved result.`,
      "event",
    );
  }, [jobId, data, send]);
  async function inspect(kind: string, id: string) {
    setInspection({ kind, id, data: null });
    try {
      setInspection({
        kind,
        id,
        data: await (kind === "check"
          ? tasteCheckpoint(id)
          : tasteInspect(kind, id)),
      });
    } catch (e) {
      setError(errorMessage(e));
      setInspection(null);
    }
  }
  const job = data?.jobs.find((j) => j.id === jobId);
  const pending = data?.examples.filter((e) => !e.reviewed) ?? [];
  const examples = data?.examples.filter((e) => ids?.includes(e.id)) ?? [];
  const tasks = [
    ...new Map(data?.trials.map((t) => [t.task, t.brief]) ?? []).entries(),
  ];
  const selectedBrief =
    tasks.find(([id]) => id === brief)?.[0] ?? tasks[0]?.[0];
  const trials = data?.trials.filter((t) => t.task === selectedBrief) ?? [];
  const instructions = inspection?.data?.instructions as
    | { skill?: string; changes?: string }
    | undefined;
  return (
    <CardShell icon={Sparkles} title={titles[section]}>
      {error && (
        <p role="alert" className="text-xs text-destructive">
          {error}
        </p>
      )}
      {!data ? (
        <p role="status" className="text-xs text-muted-foreground">
          Loading the saved eval…
        </p>
      ) : (
        <div className="space-y-4">
          {section === "progress" && (
            <>
              <p role="status" className="text-sm">
                {job?.progress ?? "Waiting for the worker…"}
              </p>
              <p className="text-xs text-muted-foreground">
                Progress is saved. I’ll continue here when it finishes.
              </p>
            </>
          )}
          {section === "preferences" && (
            <>
              <p className="text-xs text-muted-foreground">
                {data.reviewed}/{data.examples.length} reviewed. These
                suggestions come from your actual feedback; you choose what they
                mean.
              </p>
              {examples.map((example) => (
                <ReviewCard
                  key={example.id}
                  example={example}
                  onInspect={() => void inspect("example", example.id)}
                  onSave={async (label, note) => {
                    try {
                      setData(await tasteReview(example.id, label, note));
                      refresh();
                    } catch (e) {
                      setError(errorMessage(e));
                    }
                  }}
                />
              ))}
              {examples.length === 0 && (
                <p className="text-sm">
                  {pending.length
                    ? "I can bring the next examples into this conversation."
                    : "There are no unreviewed suggestions here."}
                </p>
              )}
              <Button
                size="sm"
                disabled={busy}
                onClick={() =>
                  send(
                    `I have reviewed these website examples. Continue using my saved labels; ${pending.length} suggestions remain.`,
                    "event",
                  )
                }
              >
                Continue
              </Button>
            </>
          )}
          {section === "grader" && (
            <>
              <p className="text-sm font-medium">{data.name}</p>
              <p className="text-xs text-muted-foreground">
                {data.grader.version
                  ? `Frozen vision-language model + ${data.grader.parameters.toLocaleString()} learned probe parameters · ${data.grader.version.slice(0, 8)}`
                  : "The grader has not been built yet."}
              </p>
              <p className="text-sm">
                {data.grader.released
                  ? "Ready to use."
                  : "This grader needs validation before optimization."}
              </p>
              {data.blockers.length > 0 && (
                <ul className="space-y-1 pl-4 text-xs text-muted-foreground">
                  {data.blockers.map((b) => (
                    <li key={b}>{b}</li>
                  ))}
                </ul>
              )}
              <details className="text-xs">
                <summary className="cursor-pointer">
                  Results and evidence coverage
                </summary>
                <pre className="max-h-64 overflow-auto whitespace-pre-wrap break-words">
                  {JSON.stringify(data.grader, null, 2)}
                </pre>
              </details>
              {!readOnly && (
                <Button
                  size="sm"
                  variant="outline"
                  disabled={busy}
                  onClick={() =>
                    send("What should we do next to make this eval useful?")
                  }
                >
                  Help me with the next step
                </Button>
              )}
            </>
          )}
          {section === "connect" && (
            <>
              <p className="text-xs text-muted-foreground">
                The agent gathers the public trace, current source and a
                rendered screenshot. The small model and your learned probe make
                the judgment.
              </p>
              <CopyText
                text={`Use my Stash eval ${JSON.stringify(data.name)} (id ${data.model_id ?? data.id}). Connect ${typeof window !== "undefined" ? window.location.origin : ""}/mcp/intuitions with my Stash API key. Call get_taste_grader, then check_website_taste with the current task brief, public trace [{id,role,text}], current HTML, actual screenshot_base64 PNG/JPEG bytes, trace_complete, and a checkpoint ref. Exclude credentials and private reasoning. Report missing or clipped evidence. Inspect the exact grader version and saved receipt. Scores are uncalibrated; a failed check is not approval.`}
              />
              {!data.grader.released && (
                <p className="text-xs text-muted-foreground">
                  The current model is exploratory and is not approved for
                  optimization.
                </p>
              )}
              {data.predictions.map((p) => (
                <button
                  key={p.id}
                  className="block text-xs underline"
                  onClick={() => void inspect("check", p.id)}
                >
                  {p.output.label} · {p.output.score.toFixed(3)} · inspect
                  checkpoint {p.id.slice(0, 8)}
                </button>
              ))}
            </>
          )}
          {section === "experiments" && (
            <>
              <p className="text-xs text-muted-foreground">
                GEPA changes instructions with fixed Qwen weights. Weight
                refinement changes Qwen weights using the original skill. They
                are independent experiments.
              </p>
              {data.blockers.length > 0 && (
                <p className="text-xs text-muted-foreground">
                  Both optimization experiments are blocked until the grader
                  passes its checks.
                </p>
              )}
              <div className="flex flex-wrap gap-2">
                {[
                  [
                    "Write the skill",
                    "Create the baseline skill from my reviewed training preferences.",
                  ],
                  [
                    "Run GEPA",
                    "Run the independent GEPA experiment using this eval.",
                  ],
                  [
                    "Refine weights",
                    "Run the independent weight-refinement experiment using the original baseline skill, not GEPA instructions.",
                  ],
                  [
                    "Compare results",
                    "Show the designs for the same prompt and the exact skill used for each result.",
                  ],
                ].map(([label, message]) => (
                  <Button
                    key={label}
                    size="sm"
                    variant="outline"
                    disabled={busy}
                    onClick={() => send(message)}
                  >
                    {label}
                  </Button>
                ))}
              </div>
            </>
          )}
          {section === "results" && (
            <>
              <p className="text-xs text-muted-foreground">
                One brief across the available methods. Missing arms remain
                explicit; judge scores are separate from your preferences.
              </p>
              {tasks.length > 0 && (
                <select
                  aria-label="Website brief"
                  className="w-full min-w-0 rounded border border-border bg-background p-2 text-xs"
                  value={selectedBrief}
                  onChange={(e) => {
                    setBrief(e.target.value);
                    setPair([]);
                    setPreferenceSaved(false);
                  }}
                >
                  {tasks.map(([id, text]) => (
                    <option key={id} value={id}>
                      {text}
                    </option>
                  ))}
                </select>
              )}
              <div className="space-y-4">
                {trials.map((t) => (
                  <div key={t.id}>
                    <Design
                      trial={t}
                      onInspect={() => void inspect("design", t.id)}
                    />
                    <label className="mt-1 flex items-center gap-2 text-xs">
                      <input
                        type="checkbox"
                        disabled={
                          !t.image || (!pair.includes(t.id) && pair.length >= 2)
                        }
                        checked={pair.includes(t.id)}
                        onChange={(e) => {
                          setPair(
                            e.target.checked
                              ? [...pair, t.id]
                              : pair.filter((id) => id !== t.id),
                          );
                          setPreferenceSaved(false);
                        }}
                      />
                      Compare this result
                    </label>
                  </div>
                ))}
              </div>
              {pair.length === 2 && (
                <div className="space-y-3 rounded border border-border p-3">
                  <p className="text-sm">Which design would you keep?</p>
                  <div className="grid gap-3 sm:grid-cols-2">
                    {pair.map((id, index) => (
                      <div key={id}>
                        <Picture
                          kind="design"
                          id={id}
                          alt={`Comparison ${index === 0 ? "A" : "B"}`}
                          className="h-52"
                        />
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() =>
                            void tasteCompare(pair[0], pair[1], id)
                              .then(() => setPreferenceSaved(true))
                              .catch((e) => setError(errorMessage(e)))
                          }
                        >
                          Prefer {index === 0 ? "A" : "B"}
                        </Button>
                      </div>
                    ))}
                  </div>
                  {preferenceSaved && (
                    <p role="status" className="text-xs">
                      Your preference is saved separately from the grader’s
                      scores.
                    </p>
                  )}
                </div>
              )}
              {!trials.length && (
                <p className="text-sm">There are no generated designs yet.</p>
              )}
              <p className="text-xs text-muted-foreground">
                {["base", "skill", "gepa", "posttrained"]
                  .map(
                    (method) =>
                      `${method}: ${trials.filter((t) => t.method === method && t.status === "scored").length} completed`,
                  )
                  .join(" · ")}
              </p>
            </>
          )}
        </div>
      )}
      <Dialog
        open={!!inspection}
        onOpenChange={(open) => {
          if (!open) setInspection(null);
        }}
      >
        <DialogContent className="max-h-[90dvh] overflow-y-auto sm:max-w-4xl">
          <DialogTitle>
            {inspection?.kind === "example"
              ? "Source evidence"
              : "Design, skill and grader evidence"}
          </DialogTitle>
          {inspection && (
            <>
              {inspection.kind !== "check" && (
                <Picture
                  kind={inspection.kind}
                  id={inspection.id}
                  alt="Selected design"
                  className="max-h-[50vh]"
                />
              )}
              {instructions && (
                <>
                  <h3 className="text-sm font-medium">Skill used</h3>
                  <CopyText
                    text={
                      instructions.skill ||
                      "Base model; no supplementary skill."
                    }
                  />
                  <details className="text-xs">
                    <summary>Changes from the baseline</summary>
                    <CopyText
                      text={instructions.changes || "Unchanged baseline skill."}
                    />
                  </details>
                </>
              )}
              <details className="text-xs">
                <summary>Exact inputs and provenance</summary>
                <pre className="max-h-80 overflow-auto whitespace-pre-wrap break-words">
                  {JSON.stringify(inspection.data, null, 2)}
                </pre>
              </details>
            </>
          )}
        </DialogContent>
      </Dialog>
    </CardShell>
  );
}
