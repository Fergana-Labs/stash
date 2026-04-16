# Full transcript upload + repo scope

Ship full `.jsonl` transcript uploads at SessionEnd, default-scoped to the
repo (+ worktrees) captured at `stash connect`. Atomic with the splash-copy
update so the Q&A matches reality.

## Shape

- `plugins/shared/scope.py` — `cwd_in_scope` using `git rev-parse
  --git-common-dir`. Worktrees share the install repo's common-dir, so
  `scope=repo` covers them with no extra code.
- `plugins/shared/hooks.py` — one `_short_circuit` helper gates all four
  `stream_*` functions. `stream_session_end` does a synchronous
  `client.upload_transcript(...)` after pushing the summary event.
- `plugins/shared/stash_client.py` — adds `upload_transcript`. Gzips the
  `.jsonl` client-side (5-10× compression on JSON) before multipart POST,
  so the server's 50MB cap effectively covers ~500MB of raw transcript.
  Per-request `httpx.Timeout(60, connect=5)` override; default 2s client
  timeout stays for small events.
- Backend: `session_transcripts` table (migration 0009) + `POST` and `GET`
  endpoints. Reuses `storage_service` (50MB cap matches `/files`).
- CLI: `stash history transcript <session_id>` (fetch + print/save),
  `stash config scope <repo|workspace|all>`, `stash connect` captures the
  install repo's common-dir.
- Splash Q&A copy rewritten in both `_WELCOME_MARKDOWN` and the live splash
  body to match actual behavior.

## Explicitly NOT in scope

- PII / secret redaction. Transcripts land verbatim; flagged in the Q&A
  copy and in `memory/project_transcript_redaction_followup.md`.
- Queue + retry for failed uploads. The synchronous upload just `except
  Exception: pass` — one missed transcript is cheap; we're not at scale
  where durable retry earns its complexity.
- Detached-subprocess upload. 60s `httpx` timeout keeps even 50MB files
  under Codex's 5s hook budget only if the network is fast; on a slow
  link we accept the blocked hook. With zero users, this is fine.
- `DELETE` endpoint and `stash history transcripts` list. Add when
  someone asks.
- Idempotent upsert. Duplicate sessions produce duplicate rows;
  `GET /transcripts/{session_id}` returns the most-recent one via `ORDER BY
  uploaded_at DESC LIMIT 1`. With no users, no one will notice.

## Tests

- `plugins/tests/test_scope.py` — worktree match, sibling reject, scope=all
  bypass, and the critical regression: scope=repo blocks live events.
- `backend/tests/test_transcripts.py` — upload + fetch round-trip, 413
  oversize, non-member 403. storage_service stubbed in-memory.

## Rollout

One PR, backend migration auto-runs on deploy. No migration path for
existing plugin installs — memory says zero production users, so ship
`scope=repo` as the hard default.
