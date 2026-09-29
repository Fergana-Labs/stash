# rm_worker

The ML side of the reward model training platform: trains Bradley–Terry reward
models, scores traces with them, and uses GEPA to write a skill (a SKILL.md
the agent loads into its context) with a trained reward model as the metric. It has its own venv because it depends on torch; the backend never
imports it.

## How the backend calls it

The backend writes a job directory (see "Job directory contract" in
`docs/reward-models/DESIGN.md`) and runs one of these with `RM_WORKER_PYTHON`
from the repo root, capturing stdout/stderr into `worker.log`:

| command | reads | writes |
|---|---|---|
| `python -m rm_worker.train --job-dir DIR` | `job.json`, `pairs.jsonl`, `score_items.jsonl` | `model/`, `scores.jsonl`, `result.json` |
| `python -m rm_worker.modal_train --job-dir DIR` | same | same, trained on a Modal A10G |
| `python -m rm_worker.gepa_run --job-dir DIR` | `job.json`, `gepa_examples.jsonl` | `result.json` |

A non-zero exit means the job failed; the reason is at the end of `worker.log`.

- Training runs on MPS on Apple silicon, CUDA when present, otherwise CPU.
  `job.json` is `{"kind": "train", "base_model", "epochs", "compute"}`.
  Max length (1024 tokens; long texts are truncated from the left so the end
  of the conversation survives), learning rate (1e-5) and batch size (4) are
  constants in `train.py`.
- `modal_train` needs Modal credentials (`~/.modal.toml` or `MODAL_TOKEN_ID` /
  `MODAL_TOKEN_SECRET`). The first run builds the image (about 2 minutes).
  The trained model comes back from Modal as one in-memory tarball (2.4 GB for
  Qwen3-0.6B in fp32); base models much larger than that will need a Modal Volume.
- `gepa_run` needs the API key for the LiteLLM model strings it is given
  (for example `ANTHROPIC_API_KEY` for `anthropic/...`) in its environment.
  The score GEPA sees is `sigmoid((reward - mean) / std)`, in [0, 1], where
  mean and std come from `model/reward_stats.json`. Training writes that file
  from the rewards of every scored trace. The raw rewards of a confident
  model push the sigmoid to 0 or 1, which leaves GEPA nothing to improve.
  `scores.jsonl` keeps raw rewards.
  GEPA evolves only the skill's body; `skill_name` and `skill_description` are
  fixed and the seed body is the description. Each candidate is loaded into the
  task model's system message (after the example's own system prompt) as
  `<skill name="...">` + the rendered SKILL.md + `</skill>`. The system message
  is left out of the text the reward model scores. A failed reflection model
  call fails the job, and so does a run that never reached the reflection model.

## Setup

```bash
uv venv -p 3.12 rm_worker/.venv
uv pip install --python rm_worker/.venv/bin/python -r rm_worker/requirements.txt
```

Then point the backend at it: `RM_WORKER_PYTHON=<repo>/rm_worker/.venv/bin/python`.
