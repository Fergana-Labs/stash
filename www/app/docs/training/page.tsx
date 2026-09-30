import type { Metadata } from "next";

import { Callout, Code, CodeBlock, H2, H3, P, ParamTable, Title, Subtitle } from "../components";
import { NextPage, Table } from "../parts";

export const metadata: Metadata = {
  title: "Training | Stash Docs",
  description:
    "Train a Bradley–Terry reward model on your annotations, locally on MPS, CUDA, or CPU, or on Modal. Metrics, weights, and self-hosting the training worker.",
  alternates: { canonical: "/docs/training" },
};

const JOB_DIR = `<RM_ARTIFACT_DIR>/<reward_model_id or gepa_run_id>/
  job.json             # backend: {"kind": "train" | "gepa", ...params}
  pairs.jsonl          # train, backend: {"chosen": str, "rejected": str}
  score_items.jsonl    # train, backend: {"trace_id": str, "text": str}
  gepa_examples.jsonl  # gepa, backend: {"trace_id", "system": str | null, "messages": [{role, content}], "feedback": [str]}
  result.json          # worker
  scores.jsonl         # train, worker: {"trace_id": str, "score": float}
  model/               # train, worker: weights, tokenizer, reward_stats.json
  worker.log           # worker`;

export default function TrainingPage() {
  return (
    <>
      <Title>Training</Title>
      <Subtitle>
        A small language model with a scalar head, trained on your + / − pairs to score traces the way your reviewers would.
      </Subtitle>

      <H2>The model</H2>
      <P>
        A reward model reads a rendered trace and returns one number. Stash loads your base model as{" "}
        <Code>AutoModelForSequenceClassification</Code> with <Code>num_labels=1</Code>, so the output is a
        single score <Code>r(x)</Code>, and trains it with the Bradley–Terry loss:
      </P>
      <CodeBlock lang="text">{`loss = −log σ( r(chosen) − r(rejected) )`}</CodeBlock>
      <P>
        The loss only cares about the gap between the two scores: it pushes the chosen text above the
        rejected one. A score has no fixed scale on its own. Compare scores from the same model, never
        across models.
      </P>
      <P>
        Pairs come from your annotations, and the reward model never sees system steps;{" "}
        <a href="/docs/annotations#from-annotations-to-training-pairs" className="text-brand hover:underline">Annotations</a>{" "}
        describes exactly how pairs are built and rendered.
      </P>

      <H2>Start a training job</H2>
      <CodeBlock lang="bash">{`curl -s "$STASH_URL/api/v1/rm/reward-models" \\
  -H "Authorization: Bearer $STASH_API_KEY" \\
  -H "Content-Type: application/json" \\
  -d '{
    "name": "refund-policy-v2",
    "compute": "local",
    "epochs": 2
  }'`}</CodeBlock>
      <ParamTable
        params={[
          { name: "name", type: "string", desc: "Display name.", required: true },
          { name: "compute", type: "string", desc: "local or modal.", required: true },
          { name: "base_model", type: "string", desc: "Hugging Face model id to fine-tune. Default Qwen/Qwen3-0.6B." },
          { name: "epochs", type: "integer", desc: "Passes over the training pairs. Default 1." },
          { name: "max_pairs", type: "integer", desc: "Cap on pairs after shuffling with seed 0. Default 4000." },
        ]}
      />
      <P>
        Pairs are built from your labels when the job starts. <Code>num_pairs</Code> on the reward
        model is how many it used, held-out pairs included.
      </P>

      <H3>Status</H3>
      <P>
        A reward model moves through <Code>queued</Code> → <Code>running</Code> →{" "}
        <Code>succeeded</Code> or <Code>failed</Code>. Metrics and scores are stored in the same step that
        marks it succeeded, so a succeeded model always has both. On failure, <Code>error</Code> holds the
        reason: the last 2000 characters of <Code>worker.log</Code> when the worker failed.
      </P>

      <H3>Training settings</H3>
      <Table
        head={["setting", "value"]}
        rows={[
          ["max length", "1024 tokens. Longer texts lose their beginning, so the end of the conversation, the part being judged, is kept."],
          ["learning rate", "1e-5, AdamW"],
          ["batch size", "4 pairs"],
          ["held-out split", "10% of pairs, at least 1. Training needs at least 2 pairs."],
          ["shuffling", "Seed 0, for both the split and the batch order."],
        ]}
      />
      <P>These are fixed in the worker; the request sets only the fields above.</P>

      <H2>Choosing a base model</H2>
      <P>
        Any Hugging Face model that loads as <Code>AutoModelForSequenceClassification</Code> works.
        Start with the default, <Code>Qwen/Qwen3-0.6B</Code>: it is small enough to train on a laptop,
        so you can check your labels produce a useful model before paying for a bigger one. Move to a
        larger base model when held-out accuracy stops improving as you add labels.
      </P>

      <H2>Compute</H2>
      <Table
        head={["compute", "runs on"]}
        rows={[
          ["local", "The machine running the Stash worker: MPS on Apple silicon, CUDA when a GPU is present, otherwise CPU."],
          ["modal", "A Modal A10G GPU, with a 6-hour limit. Same training code; only the device changes."],
        ]}
      />
      <P>
        With <Code>modal</Code>, the worker uploads the job&apos;s inputs, trains remotely, and gets
        the model, scores, and metrics back as one download, so the job directory ends up the same as
        after a local run. Returning the weights in one piece is practical up to about 3B parameters.
        The first Modal run also builds the container image, which takes about 2 minutes.
      </P>
      <P>
        The device used is recorded in <Code>metrics.device</Code>.
      </P>

      <H2>Metrics</H2>
      <P>
        The model never trains on the held-out pairs; they measure whether it learned your preference
        or memorized your examples.
      </P>
      <Table
        head={["metrics field", "meaning"]}
        rows={[
          ["train_pairs", "Pairs the model trained on."],
          ["eval_pairs", "Held-out pairs."],
          ["eval_accuracy", "Fraction of held-out pairs where r(chosen) > r(rejected). 0.5 is chance."],
          ["final_loss", "Mean Bradley–Terry loss over the last epoch's batches."],
          ["epochs", "Epochs run."],
          ["device", "mps, cuda, or cpu."],
          ["seconds", "Wall-clock time of the worker run, including scoring."],
        ]}
      />
      <Callout type="warning">
        With a handful of pairs, the held-out split is one or two pairs and <Code>eval_accuracy</Code>{" "}
        is close to meaningless. Read it once you have dozens of labels.
      </Callout>

      <H2>Scores</H2>
      <P>
        After training, the worker scores every trace you own, including ones nobody annotated. A score
        is the model&apos;s raw reward: any real number, higher is better. Scores appear on each trace in
        the app, in <Code>GET /traces/&#123;trace_id&#125;</Code> (the latest one also in{" "}
        <Code>latest_score</Code> on the trace list), and in the <Code>scores</Code> table of the{" "}
        <a href="/docs/api#sql-query" className="text-brand hover:underline">SQL endpoint</a>.
        Sorting unannotated traces by score is a fast way to find what to review next.
      </P>
      <P>
        GEPA calibrates rewards against the mean and standard deviation of these scores, so its
        scores fall between 0 and 1 with 0.5 at your average trace; see{" "}
        <a href="/docs/gepa#the-calibrated-score" className="text-brand hover:underline">the calibrated score</a>.
      </P>

      <H2>Where the weights go</H2>
      <P>
        The model and its tokenizer are saved together in{" "}
        <Code>RM_ARTIFACT_DIR/&lt;reward_model_id&gt;/model</Code>, along with{" "}
        <Code>reward_stats.json</Code>: the mean and standard deviation of the model&apos;s scores over
        your traces at training time, which GEPA uses to calibrate. On a self-hosted install, score new
        text with the worker&apos;s own loader, <Code>rm_worker.scoring.RewardModel</Code>, which
        truncates exactly like training did. Run it with the worker&apos;s Python from the repo root:
      </P>
      <CodeBlock lang="python">{`model = RewardModel("/var/stash/rm/<reward_model_id>/model")
rewards = model.score([rendered_trace])   # raw rewards, one per text`}</CodeBlock>
      <P>
        Render input text the same way training does (see{" "}
        <a href="/docs/annotations#3-render-each-target-to-text" className="text-brand hover:underline">rendering</a>),
        or scores won&apos;t be comparable.
      </P>

      <H3>Downloading the weights</H3>
      <P>
        Once a model has succeeded, download its <Code>model/</Code> directory as a <Code>.tar.gz</Code>{" "}
        from the API or the Download weights button in the app. Before that, the endpoint returns{" "}
        <Code>404</Code>. The archive holds one folder named after the model:
      </P>
      <CodeBlock lang="bash">{`curl -s "$STASH_URL/api/v1/rm/reward-models/<id>/weights" \\
  -H "Authorization: Bearer $STASH_API_KEY" -OJ
tar xzf refund-policy-reward-model.tar.gz`}</CodeBlock>
      <CodeBlock lang="text">{`refund-policy-reward-model/
  config.json
  model.safetensors
  tokenizer.json
  tokenizer_config.json
  chat_template.jinja
  reward_stats.json      # mean and std of scores at training time`}</CodeBlock>
      <P>
        It loads with Transformers&apos; <Code>AutoTokenizer</Code> and{" "}
        <Code>AutoModelForSequenceClassification</Code>. Truncate from the left, as training did, so
        long conversations keep their end:
      </P>
      <CodeBlock lang="python">{`path = "refund-policy-reward-model"
tokenizer = AutoTokenizer.from_pretrained(path, truncation_side="left")
model = AutoModelForSequenceClassification.from_pretrained(path)

batch = tokenizer([rendered_trace], truncation=True, return_tensors="pt")
reward = model(**batch).logits[0, 0].item()   # raw reward; higher is better`}</CodeBlock>

      <H2>Self-hosting the worker</H2>
      <P>
        Training runs in <Code>rm_worker</Code>, a separate Python package with its own virtualenv and{" "}
        <Code>requirements.txt</Code> (torch, transformers, gepa, litellm, modal). The backend never
        imports torch. For each job it writes a job directory, runs the worker as a subprocess from the
        repo root, and reads the results back. Jobs are dispatched on the Celery <Code>heavy</Code>{" "}
        queue, so a Celery worker must be consuming that queue.
      </P>
      <CodeBlock lang="bash">{`# from the repo root
uv venv -p 3.12 rm_worker/.venv
uv pip install --python rm_worker/.venv/bin/python -r rm_worker/requirements.txt

# backend/.env
RM_WORKER_PYTHON=/path/to/stash/rm_worker/.venv/bin/python
RM_ARTIFACT_DIR=/var/stash/rm`}</CodeBlock>
      <ParamTable
        params={[
          { name: "RM_WORKER_PYTHON", type: "path", desc: "Python interpreter of the rm_worker virtualenv. The backend runs the worker with it.", required: true },
          { name: "RM_ARTIFACT_DIR", type: "path", desc: "Directory for job directories and trained weights. Must be writable by both the backend and the worker.", required: true },
        ]}
      />
      <P>
        Both variables are read when a job runs, not at startup. A missing value fails the job with a
        message naming the variable. The rest of Stash runs without them.
      </P>
      <P>
        For <Code>compute: &quot;modal&quot;</Code>, the worker&apos;s environment also needs Modal
        credentials: run <Code>modal token new</Code> there, or set <Code>MODAL_TOKEN_ID</Code> and{" "}
        <Code>MODAL_TOKEN_SECRET</Code>. GEPA runs need the API keys for their models; see{" "}
        <a href="/docs/gepa#start-a-run" className="text-brand hover:underline">GEPA</a>.
      </P>

      <H3>Job directory contract</H3>
      <P>
        The backend and the worker share nothing but files. A job&apos;s directory is named after the
        reward model or GEPA run it belongs to. If you want to run the worker by hand or replace it,
        this is the whole interface:
      </P>
      <Table
        head={["command", "reads", "writes"]}
        rows={[
          ["python -m rm_worker.train --job-dir DIR", "job.json, pairs.jsonl, score_items.jsonl", "model/, scores.jsonl, result.json"],
          ["python -m rm_worker.modal_train --job-dir DIR", "same", "same, trained on a Modal A10G"],
          ["python -m rm_worker.gepa_run --job-dir DIR", "job.json, gepa_examples.jsonl", "result.json"],
        ]}
      />
      <CodeBlock lang="text">{JOB_DIR}</CodeBlock>
      <P><Code>job.json</Code> for each kind:</P>
      <CodeBlock lang="json">{`{"kind": "train", "base_model": "Qwen/Qwen3-0.6B", "epochs": 1, "compute": "local"}

{"kind": "gepa", "reward_model_dir": "<RM_ARTIFACT_DIR>/<reward_model_id>/model",
 "skill_name": "…", "skill_description": "…", "task_model": "…", "task_api_base": null,
 "reflection_model": "…", "max_metric_calls": 150}`}</CodeBlock>
      <P><Code>result.json</Code> for a training job:</P>
      <CodeBlock lang="json">{`{"metrics": {"train_pairs": …, "eval_pairs": …, "eval_accuracy": …,
             "final_loss": …, "epochs": …, "device": "…", "seconds": …}}`}</CodeBlock>
      <P>For a GEPA job:</P>
      <CodeBlock lang="json">{`{"best_skill": "…", "best_score": …, "seed_skill": "…", "seed_score": …,
 "candidates": [{"skill": "…", "score": …}]}`}</CodeBlock>
      <P>Each skill in it is the full rendered <Code>SKILL.md</Code>, frontmatter included.</P>
      <P>
        A non-zero exit fails the job. <Code>worker.log</Code> holds the worker&apos;s output, and the
        reason is at the end of it.
      </P>

      <NextPage href="/docs/gepa" label="Skills (GEPA)" />
    </>
  );
}
