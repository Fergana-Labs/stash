# Stash Architecture

Stash is a workspace for AI-agent work. The product has three primary resource
surfaces:

- Sessions: coding-agent transcripts and their generated artifacts.
- Files: the workspace's virtual filesystem — one tree with three kinds of
  node inside (folders, pages, files). Tables are a peer of Files at the
  workspace level.
- Skills: shareable bundles of sessions and Files entries. Skills are also
  the privacy boundary for workspace content.

Note: capital-F "Files" is the workspace category (peer of Sessions and
Skills); lowercase "file" is one of the three kinds of node inside that
tree (an S3-backed binary, vs. an in-app-editable page, vs. a folder).

## Runtime

- Backend: FastAPI in `backend/`, PostgreSQL, Alembic migrations, S3-compatible
  object storage for file binaries.
- Product UI: Next.js in `frontend/`.
- Landing/docs site: Next.js in `www/`.
- CLI/MCP: `cli/`, `stashai/plugin/`, and agent plugin assets under `plugins/`.

## Data Model

- `workspaces` contain members, sessions, Files, tables, and Skills.
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
  skill's folder, exactly like any other folder.
- Forking deep-copies the skill folder into the forker's workspace.

Object-level privacy tables and page-link graph tables are intentionally not part
of the current architecture. Privacy is mediated by Skills.

## Access Rules

- Content not inside a published skill folder is visible to workspace members.
- A publish record grants READ on the whole folder subtree to everyone,
  never write — publishing IS the public grant.
- Private skill access is a plain folder share.
- Publishing mints the skill's publish record and returns its public URL.

## Main Backend Routers

- `backend/routers/workspaces.py`: workspace CRUD, membership, invites.
- `backend/routers/files_tree.py`: Files folders and pages.
- `backend/routers/files.py`: uploaded files and extraction.
- `backend/routers/sessions.py`: session listing, upload, and materialization.
- `backend/routers/skills.py`: skill listing, publish records, public
  rendering, fork (folder copy), session materialization.
- `backend/routers/workspace_knowledge.py`: workspace home/sidebar payloads.
- `backend/routers/publish.py`: Skill publish flow + public Skill URLs.
- `backend/routers/discover.py`: public Skill catalog (search, trending,
  fork-into-workspace).
- `backend/routers/memory.py`: per-session event push, query, search.
- `backend/routers/tables.py`: structured table CRUD + row search.
- `backend/routers/collab.py`: Yjs WebSocket sidecar for live page editing.
- `backend/routers/integrations/`: GitHub / Google Drive / Notion OAuth +
  imports.
- `backend/routers/trash.py`: soft-delete listing + restore/purge.

Object-level privacy is enforced inline in each router that returns a
resource — there is no separate permissions router. The `workspace_members`
table gates everything inside a workspace; folder shares gate
per-person access; the publish record's existence controls public exposure.

## Frontend Shell

The product sidebar is organized as:

- Home
- Sessions
- Files
- Skills

Workspace home renders a newsfeed-like overview with quick actions to add
sessions, pages/files, and Skills. Public Skill pages render as mini workspaces
with their own home, sidebar, and grouped Files/Sessions/Tables sections.

## Agent Surface

The CLI and MCP can create/read/update workspace resources, upload transcripts
and files, search history/pages, and create/publish Skills. Agents should use
`stash files ...` for folders/pages and `stash skills ...` for shareable
bundles.
