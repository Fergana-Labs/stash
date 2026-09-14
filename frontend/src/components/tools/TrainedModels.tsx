"use client";

import { useCallback, useEffect, useState } from "react";
import { Sparkles } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import {
  ApiError,
  PaymentRequiredError,
  checkModelCorpus,
  createFolder,
  createPage,
  deleteTrainedModel,
  getModelJob,
  listFolders,
  listModelKinds,
  listTrainedModels,
  runModel,
  trainModel,
  type CorpusReport,
  type ModelKind,
  type ModelRunResult,
  type TrainedModel,
} from "@/lib/api";
import type { Folder } from "@/lib/types";

// The Models section of the Tools page: what the user has trained, a way to
// train another, and a plain write box for people who want the model without
// an agent. Agents never come here — they get the same capability through
// the MCP server the skill declares — so this page owns nothing they need.

const TRAINING_POLL_MS = 20_000;
const JOB_POLL_MS = 15_000;

const STATUS_LABEL: Record<TrainedModel["status"], string> = {
  queued: "Queued",
  training: "Training",
  ready: "Ready",
  failed: "Failed",
};

function StatusPill({ status }: { status: TrainedModel["status"] }) {
  const tone =
    status === "ready"
      ? "text-[var(--color-success)]"
      : status === "failed"
        ? "text-destructive"
        : "text-muted-foreground";
  return (
    <span className={`inline-flex items-center gap-1.5 text-[12px] font-medium ${tone}`}>
      <span
        className={`h-1.5 w-1.5 rounded-full ${
          status === "ready"
            ? "bg-[var(--color-success)]"
            : status === "failed"
              ? "bg-destructive"
              : "animate-pulse bg-muted-foreground"
        }`}
      />
      {STATUS_LABEL[status]}
    </span>
  );
}

function ModelRow({
  model,
  title,
  onRemoved,
  onWrite,
  writing,
}: {
  model: TrainedModel;
  title: string;
  onRemoved: () => void;
  onWrite: () => void;
  writing: boolean;
}) {
  const [removing, setRemoving] = useState(false);

  async function remove() {
    if (!window.confirm(`Delete ${model.name}? A new one costs a training run.`)) return;
    setRemoving(true);
    try {
      await deleteTrainedModel(model.kind, model.name);
      onRemoved();
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Failed to delete model");
      setRemoving(false);
    }
  }

  return (
    <li className="flex items-center gap-3 rounded-lg border border-border bg-surface px-4 py-3">
      <Sparkles className="h-4 w-4 shrink-0 text-muted-foreground" />
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <span className="text-sm font-medium">{model.name}</span>
          <span className="text-xs text-muted-foreground">{title}</span>
          {model.shared && (
            <span className="rounded-full bg-muted px-2 py-0.5 text-[11px] text-muted-foreground">
              Shared
            </span>
          )}
        </div>
        <div className="truncate text-xs text-muted-foreground">
          {model.status === "failed" && model.error
            ? model.error
            : model.shared
              ? "A house voice everyone can try. Train your own for yours."
              : `${model.words.toLocaleString()} words from ${model.corpus.sources.length} page${
                  model.corpus.sources.length === 1 ? "" : "s"
                }`}
        </div>
      </div>
      <StatusPill status={model.status} />
      {model.status === "ready" && (
        <Button variant={writing ? "secondary" : "outline"} size="sm" onClick={onWrite}>
          Write
        </Button>
      )}
      {!model.shared && (
        <Button variant="ghost" size="sm" onClick={() => void remove()} disabled={removing}>
          Delete
        </Button>
      )}
    </li>
  );
}

function CorpusReportView({ report }: { report: CorpusReport }) {
  return (
    <div
      className={`rounded-md border px-3 py-2 text-[12.5px] ${
        report.status === "blocked"
          ? "border-destructive/40 bg-destructive/5"
          : "border-border bg-muted"
      }`}
    >
      <div className="font-medium text-foreground">
        {report.usable_words.toLocaleString()} usable words in {report.usable_documents} of{" "}
        {report.documents} page{report.documents === 1 ? "" : "s"}
        <span className="font-normal text-muted-foreground">
          {" "}
          · {report.minimum_words.toLocaleString()} needed,{" "}
          {report.recommended_words.toLocaleString()}+ recommended
        </span>
      </div>
      {report.reasons.map((r) => (
        <div key={r} className="mt-1 text-destructive">
          {r}
        </div>
      ))}
      {report.warnings.map((w) => (
        <div key={w} className="mt-1 text-muted-foreground">
          {w}
        </div>
      ))}
    </div>
  );
}

function TrainForm({ kinds, onTrained }: { kinds: ModelKind[]; onTrained: () => void }) {
  const [kind, setKind] = useState(kinds[0].kind);
  const [name, setName] = useState("");
  const [folders, setFolders] = useState<Folder[]>([]);
  const [folderId, setFolderId] = useState("");
  const [pasteName, setPasteName] = useState("Writing samples");
  const [pasted, setPasted] = useState("");
  const [report, setReport] = useState<CorpusReport | null>(null);
  const [checking, setChecking] = useState(false);
  const [training, setTraining] = useState(false);
  const [checkout, setCheckout] = useState<{ message: string; url: string } | null>(null);

  useEffect(() => {
    listFolders()
      .then(({ folders }) => setFolders(folders.filter((f) => !f.parent_folder_id)))
      .catch((e) => toast.error(e instanceof Error ? e.message : "Failed to load folders"));
  }, []);

  const check = useCallback(
    async (id: string) => {
      if (!id) {
        setReport(null);
        return;
      }
      setChecking(true);
      try {
        setReport(await checkModelCorpus(kind, id));
      } catch (e) {
        toast.error(e instanceof ApiError ? e.message : "Couldn't check the folder");
        setReport(null);
      } finally {
        setChecking(false);
      }
    },
    [kind]
  );

  // Pasted writing becomes a page in a fresh folder — the corpus is always a
  // folder, whichever way the writing arrived.
  async function addPasted() {
    const text = pasted.trim();
    if (!text) return;
    try {
      const folder = await createFolder(pasteName.trim() || "Writing samples");
      await createPage(`sample-${Date.now()}.md`, folder.id, text);
      setFolders((fs) => [...fs, folder]);
      setFolderId(folder.id);
      setPasted("");
      await check(folder.id);
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Couldn't save the writing");
    }
  }

  async function train() {
    setTraining(true);
    setCheckout(null);
    try {
      await trainModel(kind, name.trim(), folderId);
      setName("");
      onTrained();
    } catch (e) {
      if (e instanceof PaymentRequiredError) setCheckout({ message: e.message, url: e.checkoutUrl });
      else toast.error(e instanceof ApiError ? e.message : "Couldn't start training");
    } finally {
      setTraining(false);
    }
  }

  const canTrain = !!name.trim() && !!folderId && !!report?.ready && !training;

  return (
    <form
      className="rounded-lg border border-border bg-surface p-4"
      onSubmit={(e) => {
        e.preventDefault();
        void train();
      }}
    >
      <h3 className="text-sm font-semibold">Train a model</h3>
      <p className="mt-0.5 text-[12.5px] text-muted-foreground">
        Pick a folder of your own writing. Headings, lists and code are ignored; only paragraphs
        count. One training run is a one-time fee, then the model is yours to use without limit.
      </p>
      <div className="mt-3 flex flex-col gap-3">
        {kinds.length > 1 && (
          <select
            aria-label="Model kind"
            className="h-9 rounded-md border border-border bg-base px-2 text-sm"
            value={kind}
            onChange={(e) => setKind(e.target.value)}
          >
            {kinds.map((k) => (
              <option key={k.kind} value={k.kind}>
                {k.title}
              </option>
            ))}
          </select>
        )}
        <Input
          aria-label="Model name"
          placeholder="Name (e.g. me, work, newsletter)"
          value={name}
          onChange={(e) => setName(e.target.value.toLowerCase())}
        />
        <div className="flex flex-col gap-2 md:flex-row">
          <select
            aria-label="Corpus folder"
            className="h-9 min-w-0 flex-1 rounded-md border border-border bg-base px-2 text-sm"
            value={folderId}
            onChange={(e) => {
              setFolderId(e.target.value);
              void check(e.target.value);
            }}
          >
            <option value="">Choose a folder of your writing…</option>
            {folders.map((f) => (
              <option key={f.id} value={f.id}>
                {f.name}
              </option>
            ))}
          </select>
          <Button
            type="button"
            variant="outline"
            disabled={!folderId || checking}
            onClick={() => void check(folderId)}
          >
            {checking ? "Checking…" : "Check again"}
          </Button>
        </div>
        <details className="rounded-md border border-dashed border-border px-3 py-2">
          <summary className="cursor-pointer text-[12.5px] text-muted-foreground">
            Or paste writing to start a new folder
          </summary>
          <div className="mt-2 flex flex-col gap-2">
            <Input
              aria-label="New folder name"
              value={pasteName}
              onChange={(e) => setPasteName(e.target.value)}
            />
            <Textarea
              aria-label="Pasted writing"
              rows={6}
              placeholder="Paste an essay, a few posts, or a dozen real emails…"
              value={pasted}
              onChange={(e) => setPasted(e.target.value)}
            />
            <Button
              type="button"
              variant="outline"
              className="self-start"
              disabled={!pasted.trim()}
              onClick={() => void addPasted()}
            >
              Add to a new folder
            </Button>
          </div>
        </details>
        {report && <CorpusReportView report={report} />}
        {checkout && (
          <div className="rounded-md border border-border bg-muted px-3 py-2 text-[12.5px]">
            <div className="text-foreground">{checkout.message}</div>
            <a
              href={checkout.url}
              className="mt-1 inline-block font-medium text-brand-700 underline"
            >
              Pay and come back to train
            </a>
          </div>
        )}
        <Button type="submit" disabled={!canTrain} className="self-start">
          {training ? "Starting…" : "Train"}
        </Button>
      </div>
    </form>
  );
}

function WritePanel({ model }: { model: TrainedModel }) {
  const [notes, setNotes] = useState("");
  const [length, setLength] = useState<"short" | "medium" | "long">("medium");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<ModelRunResult | null>(null);

  useEffect(() => {
    if (result?.status !== "pending") return;
    const jobId = result.job_id;
    const timer = window.setInterval(() => {
      getModelJob(model.kind, model.name, jobId)
        .then((r) => setResult(r))
        .catch((e) => toast.error(e instanceof ApiError ? e.message : "Couldn't fetch the draft"));
    }, JOB_POLL_MS);
    return () => window.clearInterval(timer);
  }, [result, model.kind, model.name]);

  async function write() {
    const lines = notes
      .split("\n")
      .map((l) => l.replace(/^[-*]\s*/, "").trim())
      .filter(Boolean);
    if (!lines.length) return;
    setBusy(true);
    setResult(null);
    try {
      setResult(await runModel(model.kind, model.name, "write", { notes: lines, length }));
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Couldn't write");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="rounded-lg border border-border bg-surface p-4">
      <h3 className="text-sm font-semibold">Write with {model.name}</h3>
      <p className="mt-0.5 text-[12.5px] text-muted-foreground">
        One note per line: the facts the passage should contain. Anything not in the notes gets
        invented. The first draft after a quiet spell can take a few minutes while the model loads.
      </p>
      <div className="mt-3 flex flex-col gap-3">
        <Textarea
          aria-label="Notes"
          rows={5}
          placeholder={"the wedge is trust, not features\nour users are ops leads\nend with an invitation to reply"}
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
        />
        <div className="flex items-center gap-2">
          <select
            aria-label="Length"
            className="h-9 rounded-md border border-border bg-base px-2 text-sm"
            value={length}
            onChange={(e) => setLength(e.target.value as typeof length)}
          >
            <option value="short">Short (a reply or post)</option>
            <option value="medium">Medium (a section)</option>
            <option value="long">Long (a whole short piece)</option>
          </select>
          <Button type="button" onClick={() => void write()} disabled={busy || !notes.trim()}>
            {busy ? "Writing…" : "Write"}
          </Button>
        </div>
        {result?.status === "pending" && (
          <p className="text-[12.5px] text-muted-foreground">{result.hint}</p>
        )}
        {result?.status === "done" && (
          <div className="flex flex-col gap-2">
            <pre className="whitespace-pre-wrap rounded-md bg-muted px-3 py-2 font-sans text-sm text-foreground">
              {result.text}
            </pre>
            <div className="text-[12px] text-muted-foreground">
              style {result.style_score.toFixed(2)} · reads human {Math.round(result.p_human * 100)}%
              {" · "}
              {result.draws} draft{result.draws === 1 ? "" : "s"} drawn
              {result.soft_failed && " · no draft cleared the detector"}
            </div>
            <div className="text-[12px] text-muted-foreground">{result.warning}</div>
          </div>
        )}
      </div>
    </div>
  );
}

export default function TrainedModels() {
  const [kinds, setKinds] = useState<ModelKind[] | null>(null);
  const [models, setModels] = useState<TrainedModel[] | null>(null);
  const [writing, setWriting] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      setModels(await listTrainedModels());
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Failed to load models");
    }
  }, []);

  useEffect(() => {
    listModelKinds()
      .then(setKinds)
      .catch((e) => toast.error(e instanceof ApiError ? e.message : "Failed to load model kinds"));
    void refresh();
  }, [refresh]);

  // A run takes minutes; keep the row honest without the user reloading.
  const inFlight = models?.some((m) => m.status === "queued" || m.status === "training") ?? false;
  useEffect(() => {
    if (!inFlight) return;
    const timer = window.setInterval(() => void refresh(), TRAINING_POLL_MS);
    return () => window.clearInterval(timer);
  }, [inFlight, refresh]);

  if (kinds === null || models === null) return null;
  const titles = Object.fromEntries(kinds.map((k) => [k.kind, k.title]));
  const active = models.find((m) => m.id === writing && m.status === "ready");

  return (
    <div className="flex flex-col gap-3">
      {models.length === 0 ? (
        <p className="text-sm text-muted-foreground">
          No models yet. Train one on your writing and your agent can draft in your voice.
        </p>
      ) : (
        <ul className="flex flex-col gap-2">
          {models.map((m) => (
            <ModelRow
              key={m.id}
              model={m}
              title={titles[m.kind] ?? m.kind}
              onRemoved={() => void refresh()}
              onWrite={() => setWriting(writing === m.id ? null : m.id)}
              writing={writing === m.id}
            />
          ))}
        </ul>
      )}
      {active && <WritePanel model={active} />}
      {kinds.length > 0 && <TrainForm kinds={kinds} onTrained={() => void refresh()} />}
    </div>
  );
}
