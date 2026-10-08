# Local trace review

Use a local database and an account with reward models enabled. Keep credentials
in ignored `backend/.env` or environment variables. These commands reject a
destination `DATABASE_URL` whose host is not loopback.

## Import saved grades with a snapshot

For a trace you are authorized to read, set `STASH_SOURCE_DATABASE_URL` to the
source database connection and `DATABASE_URL` to the local database. Then run:

```sh
python scripts/local_trace_data.py --user YOUR_LOCAL_USER copy \
  --source-owner SOURCE_OWNER_UUID --trace-id TRACE_UUID
```

This reads the source in a read-only transaction and copies the trace, its steps,
the three most recent evaluations, and their saved grading calls. Only ownership
changes: step IDs, evaluation IDs, frozen requests, outputs, and revision hashes
stay intact. It does not copy comments, model artifacts, or image files.

The command refuses to overwrite an existing local trace or another import of
the same session. Re-importing a native transcript creates new step IDs, so its
old grades cannot be attached as though they evaluated those new IDs. Score that
local copy instead. Never fabricate scores or rewrite frozen grading evidence.

## Score new local imports

For unlabeled traces, configure `OPENAI_API_KEY` in local `backend/.env`.
Optional quality checks use `TYPESAFE_API_KEY` and `JEV_MODEL`; section summaries
use `ANTHROPIC_API_KEY`. Restart the local backend and scoring worker after
changing configuration. The production pipeline decides which providers a
trace needs; imported labels do not require a labeling provider.

```sh
python scripts/local_trace_data.py --user YOUR_LOCAL_USER score --watch
```

This processes one queued trace at a time for that local account using the same
automatic evaluation pipeline as production. It polls for new queued imports
every five seconds, so no Redis or general Celery worker is needed for this UI
loop. Omit `--watch` to process at most one due trace. Ctrl-C stops the worker.
Inference runs through the remote API; this command never trains or loads a
model on the laptop. Production data and configuration are not modified.

Use a separate isolated database for tests; the backend test fixtures truncate
their database. Do not point tests at the database serving your local UI.
