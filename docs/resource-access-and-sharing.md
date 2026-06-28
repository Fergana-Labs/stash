# Resource access & source sharing — design doc

**Status:** Draft / proposal
**Scope:** `backend/services/permission_service.py`, `backend/services/memory_service.py`,
`backend/services/source_service.py`, `backend/services/share_service.py` and their call sites.

## TL;DR

Two things, which turn out to be the same work:

1. **Unify access enforcement.** Today "can user X read resource Y?" is answered by
   four pieces of code that have drifted out of agreement. Collapse them to **one
   SQL predicate**, and derive the Python boolean by *executing* that predicate —
   not by reimplementing it. No registry, no per-type policy declarations.
2. **Make connected sources shareable** (new product capability). A source becomes
   a normal shareable resource instead of an owner-only special case — which is
   exactly what dropping it into the unified predicate gives us.

There is **one access rule** for everything: *you can read a resource if you own it,
or you hold a sufficient share on it (or a container of it), or it sits in a
published/public container.* Resources don't declare policy; **users grant access**
by writing `shares` rows. Per-type code is limited to *resolution* — which owner
column, which container, how to find an object's shares.

## 1. The two layers (terminology)

A muddle worth stating plainly, because it shaped the original (rejected) design:

- **Mechanism** — *how* access can be obtained: ownership, a share grant, or a
  public container. System-defined, universal, the same for every resource type.
- **Grants** — *who actually has access* to a specific object. These are rows in the
  `shares` table, created by **the user** when they share something.

The mechanism is one rule; the grants are data. Resources do not "declare access
rules." The earlier `POLICIES`/rule-object registry modeled per-type policy that
doesn't really exist, and added a framework to fix a duplication problem — the wrong
trade. It's dropped.

## 2. Current state: four renderings of one rule

| # | Where | Shape | Notes |
|---|-------|-------|-------|
| 1 | `permission_service.check_access()` | Python boolean | owner + share + public session folder. Reimplements the rules in Python. |
| 2 | `permission_service.readable_content_condition()` | SQL predicate | owner + share + published skill. **Latent gap:** its `session` branch omits public folders, but it is never called with `session`. |
| 3 | `memory_service.readable_session_event_condition()` | SQL over `history_events` | Hand-rolls the `shares` join again; docstring admits it *"Mirrors check_access."* |
| 4 | connected sources | inline `owner_user_id = $1 AND owner_user_id = $2` | owner-only, outside the type system (`get_owned_source`, `list_connected_sources`). |

#1 and #3 are two hand-maintained copies of the same share logic in two languages;
#2 has already drifted; #4 is a separate model. This is the inconsistency to remove.

## 3. Target: one predicate, executed for the boolean

- **One SQL predicate** is the single authority — today's `readable_content_condition`,
  generalized over `object_type` (it already branches on type internally; it just
  needs to be the *only* place). Extend its `session` branch to include the
  public-session-folder rule.
- **The boolean executes the predicate** instead of reimplementing it:
  ```sql
  SELECT EXISTS (SELECT 1 FROM <table> obj WHERE obj.id = $1 AND <predicate(obj, viewer, level)>)
  ```
  `check_access` already hits the DB, so this shrinks it, and the boolean can no
  longer disagree with the SQL — it *is* the SQL.
- **The session-event predicate becomes a thin adapter:** resolve the
  `history_events` row to its `sessions` row, then apply the one predicate. Its
  hand-rolled `shares` join is deleted.

Per-type code that remains (legitimate — it's resolution, not policy): which table
holds the owner, which container (folder vs session_folder) carries a public grant,
how to walk an object to its container. These already exist as `_share_target_condition`
/ `_skill_grant_condition` / `_session_folder_open` and stay.

## 4. Connected sources become shareable

**Product decision (confirmed):** a user can share a connected source. Read-only.
Reads are **delegated** — performed by Stash using the *owner's* token, server-side;
the recipient never sees the token, scopes, or refresh ability. Management
(reconfigure / delete / change synced channels) and re-sharing stay owner-only.

This is the same unification: add `source` to the shareable set and give it a branch
in the one predicate. A source has no folder, so its rule is the simplest:
**`owner OR a direct user-share`** (no container cascade, no publish).

### 4.1 The two identities

A shared source needs two distinct user ids — which is exactly the
`(owner_user_id, user_id)` pair that already threads through this code:

- **owner_user_id** — whose data and token the source is → used for the actual
  fetch / federated search, always.
- **user_id** (viewer) — who is asking → used for the access check (owner OR share).

So reads of a shared source split cleanly: **access decided by the viewer, data
fetched as the owner.** (Note: this is why that parameter pair is *not* removable —
it is the delegated-sharing primitive.)

### 4.2 What changes

- **`share_service`**: add `source` to `_SHAREABLE` (today it raises
  `"can't share a {object_type}"`).
- **`permission_service`**: add a `source` branch to the predicate — `owner OR
  direct user-share`. `resolve_owner_user_id` / `_OWNER_LOOKUP` learn the
  `user_sources` table.
- **`source_service` reads**: `get_owned_source(source_id, user_id)` (owner-only)
  splits into:
  - `get_readable_source` — owner **OR** share — gates **reads** (list / search /
    document fetch).
  - `get_managed_source` — owner-only — gates **management & sync** (delete,
    reconfigure, the sync workers).
  The lazy body fetch and federated search keep using `source["owner_user_id"]`'s
  token unchanged — that *is* the delegation.
- **Listings / VFS**: `list_connected_sources` and `sources_tree` include
  sources shared *with* the viewer, attributed to (and grouped under) their owner —
  the "shared with me" surface for sources.
- **Audit**: `_audit_source_read` already carries both `owner_user_id` and
  `user_id`; ensure delegated reads are attributed to the **viewer acting via the
  owner**, so the owner can see who read their shared source.

## 5. Security considerations (delegated reads)

- **Delegation is the point, and the exposure.** A read-share lets the recipient
  exercise the owner's *provider-scoped* read access for that one source, through
  Stash. The owner is vouching. Acceptable because (a) read-only, (b) scoped to the
  single shared source, (c) the token never leaves the server.
- **Token isolation.** The encrypted token is never returned to the recipient; they
  cannot read it, see its scopes, or refresh it. They can only trigger
  Stash-mediated reads.
- **Management stays owner-only** so a recipient cannot *widen* the data they can
  reach (e.g. add Slack channels, change a Drive folder root) — that would turn a
  read-share into an exfiltration lever.
- **Revocation.** Unsharing, or the owner disconnecting the source, immediately cuts
  the recipient off (reads re-check the share; fetches use the owner's now-absent
  token).
- **Sensitive breadth.** Some sources are coarse and sensitive (a whole Gmail
  inbox). That's the owner's explicit choice; the share UI should make the breadth
  obvious (frontend concern, out of scope here, flagged).

## 6. Migration plan

Security-critical SQL; staged, each step its own PR, each green on the permission
suite before the next.

- **A — Unify enforcement (no behavior change).** One predicate; `check_access`
  executes it; fold the public-session-folder rule into the `session` branch.
  Add the **equivalence test** (§7).
- **B — Session adapter.** Convert `readable_session_event_condition` to delegate to
  the predicate; delete the duplicated join. Guard:
  `test_session_list_does_not_leak_unshared_sessions`.
- **C — Shareable sources (the feature).** Add `source` to `_SHAREABLE` and to the
  predicate; split `get_owned_source` into `get_readable_source` /
  `get_managed_source`; include shared-in sources in listings; attribute audit.
  New tests in §7. Frontend share UI is a separate PR.

## 7. Testing

- **Equivalence test (keystone, anti-drift):** for each resource type, across a
  scenario matrix (owner / direct share / ancestor-folder share / public container /
  published skill / expired share / no grant), assert the SQL predicate (run as
  `WHERE`) and the executed boolean return the **same** verdict.
- **Existing contract (must stay green):**
  `test_permissions.py::test_session_list_does_not_leak_unshared_sessions`,
  `test_shared_session_folder_sessions_gated_on_share`,
  `test_sources.py::test_connected_source_is_user_scoped`.
- **New source-sharing tests:**
  - a read-share lets the recipient list / search / read the source's documents;
  - without a share, the recipient is denied (the current `is_user_scoped` test,
    re-expressed against the new gate);
  - management (delete / reconfigure) and re-sharing remain owner-only for the
    recipient;
  - the recipient never receives the token (response/shape assertion);
  - unshare / owner-disconnect revokes access.

## 8. Where sharing state lives — and the scope boundary

Sharing state persists in more than the `shares` table. This refactor unifies the
**principal-based** path only; the rest are deliberately out of band and must NOT be
folded into the predicate.

**In scope — the principal path (what the predicate covers):**

| Store | Role |
|-------|------|
| `shares` | direct grants to a user: `(object_type, object_id, principal_id, permission, expires_at)` |
| `share_invites` | pending grants keyed by `email`; convert to a `shares` row on signup |
| `skills` | a published folder → public read of its subtree (the `_skill_grant_condition` branch) |
| `session_folders.public_permission` | public session folders (the public-session-folder branch) |

These all reduce to "owner OR a grant a `$user` holds OR a public container," which is
exactly the one predicate. Connected sources join this set once `source` is shareable.

**Out of band — NOT principal-based, NOT in the predicate:**

- **`share_links`** — tokenized "anyone with the link" access (`token`/`slug` →
  `target_type`/`target_id`, read-tier, with view telemetry + `revoked_at`). There is
  no `$user`: access is granted by *presenting a token* at request time, resolved at a
  different layer. Folding it into the user predicate would be a category error.
- **`pastes`** (`pastes.visibility`) — the anonymous, no-account pastebin behind
  `joinstash.ai/pages` (a PLG surface, separate `pastes` table + `/api/v1/pastes`).
  No owner, no scope, no `shares`; read via public `slug`, write via a one-time
  `edit_token`. Entirely outside the scoped access model.

**The rule for the predicate:** it answers principal-based reads only (`$user` is
known). Capability/token mechanisms (`share_links`, paste `edit_token`) are a parallel
authorization layer evaluated before/around it, never inside it. Content objects carry
no inline sharing columns — all principal sharing is externalized to `shares` + `skills`;
the only per-row public flags are `session_folders.public_permission` and
`pastes.visibility`.

## 9. Open questions / deferred

- **Re-sharing** by recipients — deferred (owner-only for now).
- **Publishing a source** (public read, like skills) — not in scope; the source
  predicate has no public-container rule yet.
- **Per-source sensitivity UX** (e.g. extra confirmation for Gmail breadth) —
  frontend, tracked separately.
- **Granularity** — sharing is per whole source. Sub-source sharing (one channel,
  one folder) is out of scope.
