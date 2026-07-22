# Disconnecting a source should not delete its data

Status: proposal (2026-07-21)
Owner: Sam
Trigger incident: reconnecting X to fix a billing problem wiped the entire X
archive (534 bookmarks + posts/replies/articles + archived media) because
disconnect hard-deletes. Anything deleted on X since the original save is
unrecoverable — which is exactly what the archive existed to prevent.

## Current behavior (verified in code)

- `POST /integrations/{provider}/disconnect` calls
  `delete_sources_for_provider` → `DELETE FROM user_sources` for every source
  of that provider (`backend/services/source_service.py:403`), then revokes
  stored tokens.
- Every per-integration document table has
  `source_id REFERENCES user_sources(id) ON DELETE CASCADE` — the delete
  silently destroys all synced/archived documents.
- Archived media blobs (x_saves, instagram_saves) live in object storage and
  are NOT deleted — the cascade orphans them.
- Shares reference sources generically (`object_type='source'`, no FK) — the
  delete orphans grantees' access rows.
- Reconnecting auto-creates a fresh source row (upsert on
  `(owner_user_id, source_type, external_ref)`), which also RESETS `settings`
  (`settings = EXCLUDED.settings`), discarding sync cursors and walk state.

So today, "Disconnect" is really "delete everything, quietly." Fixing a
token problem requires a disconnect and therefore costs the user their data.

## Decision

**Disconnect stops syncing and revokes credentials. It never deletes data.
Deletion is a separate, explicit action.**

This matches the product promise — Stash is an archive; several sources
(x_saves, instagram_saves) exist specifically so saves outlive the upstream
content. It also matches user expectation from every comparable product
(disconnecting Google from a backup tool does not delete your backups).

## Semantics

One rule for all integrations — no per-provider forks:

### Disconnect (`POST /{provider}/disconnect`)
1. Revoke + delete stored tokens (unchanged, `storage.revoke_stored`).
2. `UPDATE user_sources SET sync_enabled = false` for the provider's sources.
   Rows and documents stay. No new column: "disconnected" is derivable —
   token absent — and the integrations page already computes token presence.
3. Audit event `integration.disconnected` (unchanged), without the
   `source.deleted` events.

What still works after disconnect:
- Content-copying tables (`CONTENT_TABLES`: github_documents, slack_messages,
  granola_notes, gong_documents, notion_index, drive_documents,
  instagram_save_docs, x_save_docs): browse, read, FTS, embeddings,
  ask-the-stash — everything except freshness.
- Index-only / federated types (gmail, whole-Drive, jira, asana, linear,
  posthog): listings still render, but reads and federated search need a live
  token and MUST fail loud with a clear "source is disconnected — reconnect
  to read" error (get_valid_token already raises when the token is gone; we
  surface that error instead of a 500). No fallbacks, no cached-body shims.

### Reconnect (existing connect flow)
1. Upsert hits the same natural key → same source row, same documents.
2. Change the upsert to PRESERVE settings on conflict
   (`settings = user_sources.settings || EXCLUDED.settings`) so sync cursors
   and one-time-walk state survive; connect-time keys (e.g. `x_user_id`)
   merge on top as they do today.
3. Set `sync_enabled = true` on conflict so syncing resumes.

### Reconnect identity — same account, enforced

Today nothing guarantees a reconnect is the same provider account: tokens
sit in one slot per provider (`account_key = "default"` except Gmail), so
connecting a different account silently overwrites the token, auto-creates a
second source, and strands the kept data — and the old source would half-sync
under the new identity (public reads work, private reads 403).

Rule: **one account per provider, enforced at the OAuth callback.**
- At connect, after the token exchange, the server derives the stable
  provider account id from the provider's own API (`fetch_account` /
  `/users/me`) — never from anything client-supplied — and stores it as
  `account_ref` on the `user_integrations` row.
- On a later connect, if a stored `account_ref` (on the token row or implied
  by disconnected-with-data sources) differs from the new token's account:
  reject the connect with a loud, specific error — "Stash is linked to
  @samzliu, whose data is kept. Reconnect with that account, or delete its
  data first to link a different one." No token overwrite, no second source.
- Same account → proceed: token replaced, same source rows, syncing resumes.

Gmail's per-email `account_key` already follows this shape; this generalizes
the identity check without taking on multi-account support (deliberately out
of scope — revisit only if we decide to support multiple accounts per
provider, which means per-account token keys everywhere).

### Delete data (new, explicit)
`POST /{provider}/purge` (and per-source `DELETE /sources/{id}`, which
already exists and stays):
1. Today's behavior: delete source rows, cascade documents.
2. Plus what today's path forgets:
   - delete archived media blobs from object storage (walk the docs' `media`
     keys before the row delete; `storage_service.delete_file` exists),
   - delete share rows for the purged sources.
3. Audit event `source.purged` per source.

## UI

**Disconnect modal** (the Disconnect button opens it; choice is made at
disconnect time, keep is the default):

    Disconnect X?
    Syncing stops and Stash's access is revoked.
    (•) Keep my data — N saved items stay browsable and searchable.
        You can reconnect or delete them later.
    ( ) Delete everything — permanently removes all N items, including
        archived images/video. Cannot be undone.   [Cancel] [Disconnect]

The item count is fetched live so the destructive option states its cost.
"Delete everything" turns the confirm red.

**Integrations page, disconnected state**: provider row reads
"Disconnected — data kept · N items" with two actions: **Reconnect** (normal
OAuth flow; same source row, settings preserved) and **Delete data…** (same
red confirm). Keep-now-delete-later is always available.

**VFS/explorer**: the source folder stays in `/sources` with a
"disconnected" badge. Content-copy sources open normally; index-only
documents show the fail-loud "reconnect to read" state with a Reconnect
button. The folder's context menu gets **Delete source data…** and
**Reconnect** — both are pointers to the same two endpoints, not a third
codepath.

No "keep but hide" state: disconnected data is visible or it's deleted.

## Special cases checked

- **Slack**: tokens are team-scoped and the bot install
  (`slack_bot_installs`) is separate from the user's source. Disconnect
  revokes the user token and disables the source; the bot install is managed
  by its own uninstall flow. Push events for a disabled source are dropped by
  the existing owner-lookup failing — verify it fails loud, not silently.
- **GitHub all-repos mode**: the sync-all reconciler iterates users from
  stored tokens (`storage.sync_all_user_ids`), so a disconnected user drops
  out naturally. Source rows stay disabled until reconnect.
- **Push sources (Granola/Slack)**: nothing to poll; `sync_enabled = false`
  plus missing token means webhook ingest for that user rejects loudly.
- **Seed/dev**: `seed_dev` fakes tokens; unaffected.

## What does NOT change

- Per-source deletion (`delete_source`) — already explicit, keeps cascade.
- The FK `ON DELETE CASCADE` stays: it is correct for the explicit purge
  path; we simply stop reaching it from disconnect.
- Account deletion continues to hard-delete everything.

## Migration

One small migration: `user_integrations.account_ref text` (nullable), filled
at connect. The migration backfills it where the id already exists on our
side — X from the x_saves source `external_ref`, Gmail from `account_key` —
so those are protected immediately; other providers fill in at their next
connect (the mismatch check only fires once an `account_ref` exists, so
current users are never blocked).
Everything else is behavior-only. One shot, all providers at once — no
compatibility flag, no per-provider rollout.

Follow-up (separate, optional): a one-time R2/S3 sweep for media blobs
orphaned by historical disconnects (including today's X wipe).

## Implementation sketch (single PR)

1. `source_service.disable_sources_for_provider(user_id, provider)` replaces
   `delete_sources_for_provider` in the disconnect endpoint (the delete
   helper survives for the purge endpoint).
2. Connect upsert: `settings` merge + `sync_enabled = true` on conflict.
   Callback records `account_ref` and rejects on mismatch (see Reconnect
   identity) before any token write.
3. `POST /{provider}/purge` endpoint = old disconnect behavior + blob and
   share cleanup.
4. Read-path: map missing-token errors on index-only reads/federated search
   to a 409 "source disconnected" instead of 500.
5. Frontend: integrations page three-state row + purge confirmation dialog.
6. Tests: disconnect keeps docs and disables sync; reconnect reuses the row
   and preserves settings; purge removes docs, blobs, and shares; index-only
   read after disconnect returns the 409.

## Open questions for Sam

1. Should **shared-to-me** views of a disconnected source stay readable
   (content-copy types)? Proposal: yes — the data exists; sharing semantics
   shouldn't depend on the owner's token state.
2. Purge granularity: provider-level only, or also per-kind (e.g. "delete my
   X bookmarks but keep articles")? Proposal: provider-level + existing
   per-source delete; per-kind is scope creep until someone asks.
3. Retention cap: do we ever auto-expire data from disconnected sources
   (e.g. free-tier storage pressure)? Proposal: not now; revisit with
   billing/storage limits.
