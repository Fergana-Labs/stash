# Stash Architecture

Stash is a single-player home for AI-agent work. Everything you create lives in
your Stash and belongs to your account. There are three primary resource
surfaces:

- Sessions: coding-agent transcripts and their generated artifacts.
- Files: your virtual filesystem — one tree with three kinds of node inside
  (folders, pages, files). Tables are a peer of Files at the account level.
- Skills: shareable bundles of sessions and Files entries. Skills are also the
  privacy boundary for your content.

Note: capital-F "Files" is the account category (peer of Sessions and Skills);
lowercase "file" is one of the three kinds of node inside that tree (an
S3-backed binary, vs. an in-app-editable page, vs. a folder).

## Runtime

- Backend: FastAPI in `backend/`, PostgreSQL, Alembic migrations, S3-compatible
  object storage for file binaries.
- Product UI: Next.js in `frontend/`.
- Landing/docs site: Next.js in `www/`.
- CLI/MCP: `cli/`, `stashai/plugin/`, and agent plugin assets under `plugins/`.

## Data Model

- A `user` owns sessions, Files, tables, and Skills — the account is the scope.
- `sessions` and `history_events` store agent transcript activity.
- `folders`, `pages`, and `files` form the Files surface.
- `tables` and `table_rows` store structured data that can live inside
  Skill folders.
- A Skill is a special folder: one containing a `SKILL.md` page. Files and
  Skills are MECE — skill folders are hidden from every Files surface and
  shown in the Skills area instead.
- `skills` is the 1:1 publish record for a skill folder (`folder_id`
  unique): slug, cover art, Discover flag. Its existence makes the folder
  publicly readable at /skills/<slug>.
- Person-to-person skill access rides the generic `shares` table on the
  skill's folder, exactly like any other folder. Share recipients can
  materialize an unpublished shared skill via
  `/me/shared-skills/{folder_id}/contents` — the share, not publication, is
  the grant.
- Forking deep-copies the skill folder into the forker's account.
- `mcp_servers` is the per-user MCP registry (Tools page / `stash tools`):
  transport + target, with header/env secrets Fernet-encrypted using the
  integrations keyring. The cloud agent's sprite gets the registry written
  into its `.mcp.json` every turn.
- A workspace is an org-owned, login-less scope (`workspaces.domain`,
  membership derived from verified email domain). Content routes select the
  scope via the `X-Stash-Scope` header — including the plugin's session,
  event, transcript, and artifact writes — and non-members are hard-403'd.

Object-level privacy tables and page-link graph tables are intentionally not part
of the current architecture. Privacy is mediated by Skills.

## Access Rules

- Content is private to your account by default.
- A publish record grants READ on the whole folder subtree to everyone,
  never write — publishing IS the public grant.
- Private skill access is a plain folder share to another person.
- Publishing mints the skill's publish record and returns its public URL.

## Main Backend Routers

- `backend/routers/users.py`: account profile (`GET /api/v1/users/me`) and
  API-key management.
- `backend/routers/user_knowledge.py`: account home/sidebar payloads.
- `backend/routers/files_tree.py`: Files folders and pages.
- `backend/routers/files.py`: uploaded files and extraction.
- `backend/routers/sessions.py`: session listing, upload, and materialization.
- `backend/routers/skills.py`: skill listing, publish records, public
  rendering, fork (folder copy), session materialization.
- `backend/routers/publish.py`: Skill publish flow + public Skill URLs.
- `backend/routers/discover.py`: public Skill catalog (search, trending,
  fork-into-account).
- `backend/routers/memory.py`: per-session event push, query, search.
- `backend/routers/tables.py`: structured table CRUD + row search.
- `backend/routers/shares.py`: person-to-person folder shares.
- `backend/routers/sources.py`: GitHub / Google Drive / Notion OAuth + imports.
- `backend/routers/collab.py`: Yjs WebSocket sidecar for live page editing.
- `backend/routers/trash.py`: soft-delete listing + restore/purge.

Object-level privacy is enforced inline in each router that returns a
resource — there is no separate permissions router. Ownership gates everything
in your account; folder shares gate per-person access; the publish record's
existence controls public exposure.

## REST API Shape

The authenticated user is the scope, so account-scoped collections hang off
`/api/v1/me`:

- `GET /api/v1/users/me` — current account.
- `GET /api/v1/me/tree` — your Files tree.
- `GET /api/v1/me/pages`, `GET /api/v1/me/folders` — Files entries.
- `GET /api/v1/me/skills` — your Skills.

Single shared objects are addressed by their canonical, account-independent id:

- `/api/v1/pages/{id}`
- `/api/v1/files/{id}`
- `/api/v1/tables/{id}`

## Frontend Shell

The product sidebar is organized as:

- Home
- Sessions
- Files
- Skills

Home renders a newsfeed-like overview with quick actions to add sessions,
pages/files, and Skills. Public Skill pages render as mini sites with their own
home, sidebar, and grouped Files/Sessions/Tables sections.

## Agent Surface

The CLI and MCP can create/read/update your account's resources, upload
transcripts and files, search history/pages, and create/publish Skills. In the
VFS, your account is rooted at `/me` (e.g. `stash vfs "ls /me/files"`). Agents
should use `stash files ...` for folders/pages and `stash skills ...` for
shareable bundles.
