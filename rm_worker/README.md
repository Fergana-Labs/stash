# rm_worker

The ML side of the reward model training platform: trains Bradley–Terry reward
models, scores traces with them, and runs GEPA prompt optimization against
them. It has its own venv because it depends on torch; the backend never
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
  The reward score GEPA sees is `sigmoid(reward)`, in [0, 1].

## Setup

```bash
uv venv -p 3.12 rm_worker/.venv
uv pip install --python rm_worker/.venv/bin/python -r rm_worker/requirements.txt
```

Then point the backend at it: `RM_WORKER_PYTHON=<repo>/rm_worker/.venv/bin/python`.
