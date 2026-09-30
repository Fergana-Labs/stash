import type { Metadata } from "next";

import { Callout, Code, CodeBlock, H2, H3, P, ParamTable, Title, Subtitle } from "../components";
import { NextPage, Table } from "../parts";

export const metadata: Metadata = {
  title: "Training · Stash Docs",
  description:
    "Train a Bradley–Terry reward model on your annotations, locally on MPS, CUDA, or CPU, or on Modal. Metrics, weights, and self-hosting the training worker.",
  alternates: { canonical: "/docs/training" },
};

export default function TrainingPage() {
  return (
    <>
      <Title>Training</Title>
      <Subtitle>
        A small language model with a scalar head, trained on supported feedback from selected traces.
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
        Pairs come from actionable comments, explicit later user corrections, and API ratings on the selected traces. The reward model never sees system steps;{" "}
        <a href="/docs/annotations#from-annotations-to-training-pairs" className="text-brand hover:underline">Annotations</a>{" "}
        describes exactly how pairs are built and rendered.
      </P>

      <H2>Start a training job</H2>
      <P>
        In the app, select traces and choose <strong>Create new reward model</strong>. There is no
        separate Auto mode or rating control in the UI. The experiment is enabled for new accounts;
        accounts that existed at rollout receive 404 from reward-model APIs.
      </P>
      <CodeBlock lang="bash">{`curl -s "$STASH_URL/api/v1/rm/reward-models" \\
  -H "Authorization: Bearer $STASH_API_KEY" \\
  -H "Content-Type: application/json" \\
  -d '{
    "name": "refund-policy-v2",
    "trace_ids": ["<trace_id>"],
    "epochs": 2
  }'`}</CodeBlock>
      <ParamTable
        params={[
          { name: "name", type: "string", desc: "Display name.", required: true },
          { name: "trace_ids", type: "string[]", desc: "At least one trace UUID owned by you. Only these traces supply training pairs.", required: true },
          { name: "base_model", type: "string", desc: "Hugging Face model id to fine-tune. Default Qwen/Qwen3-0.6B." },
          { name: "epochs", type: "integer", desc: "Passes over the training pairs. Default 1." },
          { name: "max_pairs", type: "integer", desc: "Cap on combined API-rating and feedback-derived pairs. Default 4000." },
        ]}
      />
      <P>
        The worker extracts supported preferences and saves each generated alternative with its
        source ID, verbatim evidence quote, and rationale. These are model interpretations of
        feedback, not direct human votes. Ambiguous feedback is skipped; invalid extraction fails
        the job. At least two usable pairs are required. <Code>num_pairs</Code> includes held-out pairs.
      </P>
      <P>
        The deployment selects <Code>RM_COMPUTE</Code>; sending <Code>compute</Code> or any unknown
        request field returns 422. Extraction and the minimum pair count are checked after queueing,
        before downloading the base model.
      </P>

      <H3>Status</H3>
      <P>
        A reward model moves through <Code>queued</Code> → <Code>running</Code> →{" "}
        <Code>succeeded</Code> or <Code>failed</Code>. Metrics and scores are stored in the same step that
        marks it succeeded, so a succeeded model has scores, metrics, and a private stored checkpoint. On failure, <Code>error</Code> holds the
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
        The base model must support <Code>AutoModelForSequenceClassification</Code> and fit the deployment&apos;s memory and time limits.
        Start with the default, <Code>Qwen/Qwen3-0.6B</Code>: it is small enough to train on a laptop,
        so you can check your labels produce a useful model before paying for a bigger one. Move to a
        larger base model when held-out accuracy stops improving as you add labels.
      </P>

      <H2>Compute</H2>
      <Table
        head={["compute", "runs on"]}
        rows={[
          ["local", "The machine running the Stash worker: MPS on Apple silicon, CUDA when a GPU is present, otherwise CPU."],
          ["modal", "A Modal A10G GPU, with a 20-minute limit per training or GEPA invocation. Same training code; only the device changes."],
        ]}
      />
      <P>
        With <Code>modal</Code>, the GPU process receives the inputs, uploads the checkpoint directly
        to private S3, and returns only JSON results and scores. It receives storage and model-provider
        credentials, but no database, queue, or integration credentials. The ML image is built from{" "}
        <Code>rm_worker/requirements.txt</Code>.
      </P>
      <P>
        The device used is recorded in <Code>metrics.device</Code>.
      </P>

      <H2>Metrics</H2>
      <P>
        The held-out pairs are not used to update the model. The split is by pair, so related examples
        may appear in both sets; accuracy alone does not establish performance on independent traces.
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
          ["seconds", "Worker training time, including scoring and checkpoint upload."],
        ]}
      />
      <Callout type="warning">
        With a handful of pairs, the held-out split is one or two pairs and <Code>eval_accuracy</Code>{" "}
        is too noisy to establish quality. Check behavior on separate traces before relying on scores.
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
        GEPA uses the mean and standard deviation of rewards for both chosen and rejected texts in
        the training and held-out pairs. Its score falls between 0 and 1, with 0.5 at that calibration
        mean, not a probability of correctness; see{" "}
        <a href="/docs/gepa#the-calibrated-score" className="text-brand hover:underline">the calibrated score</a>.
      </P>

      <H2>Downloading the weights</H2>
      <P>
        Choose <strong>Download weights</strong> on a succeeded model. The owner-authorized API
        returns <Code>{`{"url": "https://…"}`}</Code> with a five-minute signed URL, not archive bytes.
        Download from that URL without forwarding your Stash API key. Unowned or unfinished models
        return 404. Checkpoints live in private S3 storage, independent of the training filesystem.
      </P>
      <CodeBlock lang="bash">{`set -euo pipefail
reward_weights_url="$(curl -fsS "$STASH_URL/api/v1/rm/reward-models/<id>/weights" -H "Authorization: Bearer $STASH_API_KEY" | jq -er '.url')"
curl -fL "$reward_weights_url" --output reward-model.tar.gz
tar xzf reward-model.tar.gz`}</CodeBlock>
      <CodeBlock lang="text">{`reward-model/
  config.json
  model.safetensors
  tokenizer.json
  tokenizer_config.json
  chat_template.jinja
  reward_stats.json`}</CodeBlock>
      <P>
        With worker dependencies installed, run this from the repository root after extracting the
        archive. The loader applies the same truncation as training:
      </P>
      <CodeBlock lang="python">{`from rm_worker.scoring import RewardModel

model = RewardModel("reward-model")
rewards = model.score([rendered_trace])`}</CodeBlock>
      <P>
        Render input as described in <a href="/docs/annotations#3-render-each-target-to-text" className="text-brand hover:underline">Annotations</a>.
        GEPA downloads this same checkpoint into a fresh temporary workspace.
      </P>

      <H2>Self-hosting the worker</H2>
      <P>
        A dedicated Celery worker consumes the <Code>reward</Code> exchange/queue with concurrency 1.
        The API and ingestion workers do not load torch. For local execution, install the ML
        environment from the repository root:
      </P>
      <CodeBlock lang="bash">{`uv venv -p 3.12 rm_worker/.venv
uv pip install --python rm_worker/.venv/bin/python -r rm_worker/requirements.txt`}</CodeBlock>
      <P>Set these in the root <Code>.env</Code>, loaded by <Code>./start.sh</Code>:</P>
      <CodeBlock lang="text">{`RM_COMPUTE=local
RM_WORKER_PYTHON=/absolute/path/to/stash/rm_worker/.venv/bin/python
RM_ARTIFACT_DIR=/absolute/path/to/rm-job-scratch
ANTHROPIC_API_KEY=<provider-key>
S3_ENDPOINT=<storage-origin>
S3_BUCKET=<private-bucket>
S3_ACCESS_KEY=<access-key>
S3_SECRET_KEY=<secret-key>
S3_REGION=<region>`}</CodeBlock>
      <P>
        S3 is required even for local training. The API and worker need the same storage settings.{" "}
        <Code>RM_ARTIFACT_DIR</Code> is temporary scratch space; the API does not need that directory.{" "}
        <Code>ANTHROPIC_API_KEY</Code> supports feedback extraction and default GEPA models.
        Start the local stack with <Code>./start.sh</Code>, which includes the reward worker.
      </P>
      <P>
        For hosted Modal execution, set <Code>RM_COMPUTE=modal</Code> on the API and reward worker.
        The backend image includes the runner and sets <Code>RM_WORKER_PYTHON=/usr/local/bin/python</Code>{" "}
        and <Code>RM_ARTIFACT_DIR=/tmp/stash-rm</Code>. The reward worker also needs{" "}
        <Code>MODAL_TOKEN_ID</Code>, <Code>MODAL_TOKEN_SECRET</Code>, and the same{" "}
        <Code>DATABASE_URL</Code> and <Code>REDIS_URL</Code> as the API. Its command is:
      </P>
      <CodeBlock lang="bash">{`celery -A backend.celery_app worker --loglevel=info --concurrency=1 -Q reward`}</CodeBlock>
      <P>
        The <a href="https://github.com/Fergana-Labs/stash/blob/main/rm_worker/README.md" className="text-brand hover:underline">worker README</a>{" "}
        and <a href="https://github.com/Fergana-Labs/stash/blob/main/docs/reward-models/DESIGN.md#job-directory-contract-backend--worker" className="text-brand hover:underline">job directory contract</a>{" "}
        describe subprocess inputs, outputs, and failure handling.
      </P>

      <NextPage href="/docs/gepa" label="Skills (GEPA)" />
    </>
  );
}
