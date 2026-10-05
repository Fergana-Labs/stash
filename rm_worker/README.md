# rm_worker

Trains Bradley–Terry reward models, scores traces, and uses GEPA to write
`SKILL.md` instructions. GPU libraries run in this package's own environment;
the API imports only the lightweight artifact helper, never torch.

The default product path is a shared Stash evaluator. Shared candidates always use
Modal, freeze explicit train/eval task partitions, and evaluate the candidate and
incumbent on the same benchmark before release. Recurring training is off until an
operator enables it. See [Shared evaluator](../docs/reward-models/SHARED_EVALUATOR.md)
for bootstrap, permissions, release gates and rollback. Personal models retain the
selected-trace workflow described below.

## Execution and storage

The API records `RM_COMPUTE` (`local` or `modal`) on each model. Clients cannot
set `compute` in a training request. A dedicated Celery worker consumes the
`reward` exchange/queue, builds pairs from selected traces, and runs a subprocess
with `RM_WORKER_PYTHON`. Comments and explicit later user corrections can supply
pairs; at least two are required. Exact pairs and cited evidence are saved in
Postgres before training.

| command | reads | returns to the job directory |
|---|---|---|
| `python -m rm_worker.train --job-dir DIR` | `job.json`, `pairs.jsonl`, `score_items.jsonl`, `action_score_items.jsonl` | `model/`, `scores.jsonl`, `action_scores.jsonl`, `result.json` |
| `python -m rm_worker.score_run --job-dir DIR` | `job.json`, `action_score_items.jsonl` | `action_scores.jsonl`, `result.json` |
| `python -m rm_worker.evaluate_run --job-dir DIR` | `job.json`, `evaluation_pairs.jsonl` | `evaluation.json` (example ID + whether chosen beats rejected) |
| `python -m rm_worker.modal_runner --job-dir DIR` | training, scoring or GEPA inputs | the corresponding worker outputs above |
| `python -m rm_worker.gepa_run --job-dir DIR` | `job.json`, `gepa_examples.jsonl` | `result.json` |

Local training uses MPS, CUDA, or CPU according to the machine. Modal runs
training and GEPA on an A10G with a 20-minute limit. Its GPU process receives
only inputs plus storage/model-provider credentials; no database or queue
credentials. It returns JSON results, not checkpoint bytes.

Both runtimes upload checkpoint archives to private S3 before marking training
successful. `RM_ARTIFACT_DIR` is temporary job storage, not durable model storage.
GEPA downloads the model identified by `reward_model_key` into its own temporary
workspace. The API returns a five-minute signed URL for weights downloads.
Archives contain a `reward-model/` directory with weights, tokenizer, and
`reward_stats.json`, plus `action_reward_stats.json` when trained on action pairs.

See the [job directory contract](../docs/reward-models/DESIGN.md#job-directory-contract-backend--worker)
for input/output fields. A non-zero exit fails the job; `worker.log` holds the
subprocess output. Model settings are 1024 tokens (left truncation), learning
rate 1e-5, and batch size 4.

GEPA uses `sigmoid((reward - mean) / std)`. The saved mean and standard deviation
come from rewards for both chosen and rejected texts in the training pairs only.
Action credit uses `tanh((reward - mean) / (2 * std))` with a separate reference
from training action pairs. This is a relative display scale, not a correctness
probability or causal contribution. Saved-checkpoint action inference never
calls the labeling LLM. Evaluation holds out complete source traces, excludes
cross-partition pairs and reports null accuracy when independent evaluation is
unavailable, plus separate action and tool-call accuracy and counts.
The reflection model generates the skill's name and description, then
GEPA evolves its body. Each candidate is included in the task model's system
message; the reward model scores the conversation without that system message.

In an environment with the worker dependencies and pytest, the tiny CPU smoke
test exercises training, checkpoint saving and reloaded action inference without
network access, production weights or storage:

```bash
HF_HUB_OFFLINE=1 python -m pytest rm_worker/tests/test_action_training.py --no-cov -q
```

## Local setup

From the repository root:

```bash
uv venv -p 3.12 rm_worker/.venv
uv pip install --python rm_worker/.venv/bin/python -r rm_worker/requirements.txt
```

Set these in the root `.env`, which `start.sh` loads:

```dotenv
RM_COMPUTE=local
RM_WORKER_PYTHON=/absolute/path/to/stash/rm_worker/.venv/bin/python
RM_ARTIFACT_DIR=/absolute/path/to/rm-job-scratch
ANTHROPIC_API_KEY=<provider-key>
S3_ENDPOINT=<storage-origin>
S3_BUCKET=<private-bucket>
S3_ACCESS_KEY=<access-key>
S3_SECRET_KEY=<secret-key>
S3_REGION=<region>
```

S3 is required even for local training. The API and reward worker need the same
storage configuration. `ANTHROPIC_API_KEY` supports feedback extraction and the
default GEPA models. Other task/reflection models need their provider keys.
Start the local stack with `./start.sh`; it includes a reward worker with
concurrency 1. A standalone worker uses the backend environment:

```bash
celery -A backend.celery_app worker --loglevel=info --concurrency=1 -Q reward
```

## Hosted setup

Set `RM_COMPUTE=modal` on the API and reward worker. The backend image includes
the runner and sets `RM_WORKER_PYTHON=/usr/local/bin/python` and
`RM_ARTIFACT_DIR=/tmp/stash-rm`. Add `MODAL_TOKEN_ID` and `MODAL_TOKEN_SECRET` to
the reward worker, along with the storage/provider settings above and the
same `DATABASE_URL` and `REDIS_URL` as the API. Modal builds the ML environment
from `rm_worker/requirements.txt`; torch is not installed in the API image.

See [Hosted rollout](../docs/reward-models/ROLLOUT.md) for account gating and
verification. New accounts enter the experiment; existing accounts stay disabled.
