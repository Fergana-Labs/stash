# Hosted rollout

Migration 0210 marks every existing user `reward_models_enabled = false`, then
sets the default to true for future accounts. Both the UI and every `/api/v1/rm`
endpoint enforce that per-account flag. Existing accounts keep the original
navigation, home, settings entry, and Skills experience. No customer data is
imported by migrations. The Heavi sample is local development data only.

Opting an account in or out is an explicit database update of that user's flag.
Disabling it blocks the reward API and hides the workspace on the next profile
fetch. It does not delete traces or models or cancel an already running job.

## Runtime

The hosted backend image includes the lightweight Modal runner. A separate
Celery service consumes only `reward`, with concurrency 1. Existing default,
heavy, and sync services retain their current queues. GPU libraries are built
inside Modal, not installed on the API or ingestion workers.

Required on the reward worker:

- `DATABASE_URL` and `REDIS_URL` for the same deployment as the API.
- `RM_COMPUTE=modal`, `RM_WORKER_PYTHON=/usr/local/bin/python`,
  `RM_ARTIFACT_DIR=/tmp/stash-rm` (set in the image).
- `MODAL_TOKEN_ID`, `MODAL_TOKEN_SECRET` for the Stash Modal workspace.
- `ANTHROPIC_API_KEY` for feedback extraction and default skill generation.
- `S3_ENDPOINT`, `S3_BUCKET`, `S3_ACCESS_KEY`, `S3_SECRET_KEY`, `S3_REGION`.

The API also needs `RM_COMPUTE` when accepting training requests and the S3
settings to authorize five-minute signed checkpoint download URLs. The browser
downloads directly from storage without buffering the checkpoint in JavaScript.
Modal receives only the storage and model-provider credentials; it never
receives database, queue, OAuth, or integration credentials. Each GPU invocation
is limited to 20 minutes. Shared candidate jobs run training and two benchmark
evaluations sequentially under a 65-minute Celery hard limit; personal jobs retain
their existing timeout.

Checkpoint archives live in private S3 storage. Migration 0211 records their
keys and the exact training pairs/evidence. A successful job can be downloaded
and used for skill generation after its worker filesystem is discarded.

## Shared evaluator bootstrap

Migration 0215 queues existing and new traces for the shared evaluator, but leaves
shared-training consent and recurring training off. Celery beat's 30-second sweep
is required for scoring, contribution collection and candidate dispatch. No shared
checkpoint or benchmark is installed by migration. Until the first candidate passes
and is released, the UI reports that it is waiting for the first evaluator.

Follow [Shared evaluator and learning loop](SHARED_EVALUATOR.md) to seed a permitted,
reviewed corpus, train remotely, inspect the release gate and promote the first
model. The operator API uses the existing `ADMIN_PASSWORD` / `X-Admin-Token`
boundary. Enabling automation authorizes recurring GPU jobs; `auto_promote` enables
gated releases. Turning automation off blocks new candidates and automatic releases.
Never use customer data without its applicable shared-training permission.

## Verification boundary

Use a separate database, queue, backend, worker, and frontend for branch QA.
Never point an unmerged branch's migration runner at the production database.
Verify a new account's comment-only training, scores, checkpoint download,
SKILL.md generation/download, and a flag-off account's navigation and API denial.

Merging `main` triggers Render deployments and migrations. The flag limits
feature exposure, but shared dependencies, migrations, and backend deployment
remain part of the release's infrastructure blast radius.
