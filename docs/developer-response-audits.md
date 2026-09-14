# Developer response audits

Developer VFS and skill reads keep a private copy of the serialized JSON
response in `read_response_audits`. This evidence is independent of transcript
uploads and their clipping limits. It is never written to pages, files,
`history_events`, customer security-event metadata, search, or curator inputs.
The table has no product API or VFS mount; investigation requires operator
database access. Treat its request inputs and response bodies as private
customer data.

## Coverage and identifiers

The journal applies when the authenticated scope belongs to an activated
developer workspace (`external_wiki_folder_id` is set):

- `POST /api/v1/me/vfs`: full result, including nonzero shell exit codes, and
  handled HTTP errors such as a scan-budget rejection.
- `GET /api/v1/me/skills`: skill index.
- `GET /api/v1/me/skills/{name}` and `/api/v1/me/source-skills/{source_ref}`:
  skill document or its 404 response.

The server returns `X-Stash-Request-Id`, a new UUID for each recorded response.
The row contains the authenticated workspace and actor, method, path, request
inputs, HTTP status, timestamp, response bytes, and their SHA-256 digest.
`response_body` is `bytea` so it preserves the exact JSON entity, including
escaped NUL characters, without a JSONB reserialization or text truncation.
HTTP compression and transfer framing are outside this snapshot.

Callers can attach these optional headers (1–128 characters when present):

| Header | Meaning |
| --- | --- |
| `X-Stash-User-Id` | Caller-asserted external org/user for skill reads. VFS always records the body `user_id` instead. |
| `X-Stash-Session-Id` | Calling product's conversation/session ID. |
| `X-Stash-Workflow-Run-Id` | Calling product's workflow/turn ID. |

These headers supply correlation only; they grant no access and never select
the authenticated workspace. The VFS body's existing `user_id` contract still
controls its read scope. Skill access rules are unchanged. Missing identifiers
remain NULL rather than being inferred from a later upload. Reads for new end
users are recorded even before an end-user or session row exists.

## Failure behavior and limits

The database insert completes **before** the response is released. If that
insert fails, the endpoint returns a generic 503 without the prepared customer
payload or a misleading receipt. This adds a synchronous database write to
each covered developer read and makes audit storage availability a dependency
of those reads. Exception details and raw response bodies are not logged to
the application console.

Authentication/validation rejections before route execution, unhandled server
errors, disconnects, requests to other endpoints, and personal scopes are not
covered by this journal. It is a record of prepared responses, not an exhaustive
request-attempt counter or proof that a remote agent/human received a response.
It cannot reconstruct historical results from before deployment. Client-side
cache reuse is not a new Stash HTTP response; the client must retain provenance
for that reuse if needed.

## Operator lookup and rollout

Apply migration `0205` before serving the updated routes (normal backend startup
applies migrations). Deploy Stash before relying on receipts in a client. Older
clients remain compatible: requests without correlation headers are still
recorded with any VFS body `user_id`.

For one conversation, bind the workspace UUID and the caller's session ID:

```sql
SELECT id, external_user_id, workflow_run_id, method, path, status_code,
       created_at, request_data, octet_length(response_body) AS response_bytes,
       response_sha256
FROM read_response_audits
WHERE workspace_id = $1 AND session_id = $2
ORDER BY created_at, id;
```

Fetch a specific body with `SELECT response_body FROM read_response_audits
WHERE workspace_id = $1 AND id = $2`. Verify its SHA-256 locally before examining
the parsed JSON. Keep any exports private; do not upload them into a customer
wiki or transcript feed.

Rows have no automatic expiration in this change. Workspace deletion cascades
to its audit rows; deleting an actor only clears the actor reference. Inspect
`pg_total_relation_size('read_response_audits')` to track table/index/TOAST
storage, and group `octet_length(response_body)` by workspace to attribute
growth. Retention changes must account for investigation holds; this migration
does not delete existing evidence.
