# Changelog

This file tracks user-visible changes. v0 is the open-source baseline —
everything before it is captured in git history (`git log`), not here.

## Unreleased

- Skills are now explicitly typed folders under the `/skills` VFS root.
  A file named `SKILL.md` is the agent manifest inside a Skill; creating or
  deleting that filename no longer silently changes an ordinary folder's type.
- Agent skills now require non-empty `name` and `description` metadata
  before Stash creates, imports, publishes, installs, or syncs them. Stash
  no longer syncs every skill into global agent directories at session
  startup; installation and sync are explicit commands.
- Frontend server-side backend requests now require `BACKEND_INTERNAL_URL`
  or `NEXT_PUBLIC_API_URL` instead of guessing an environment, so missing
  managed deploy config fails during build rather than crashing public
  Stash pages at runtime.
- Added a committed `docker-compose.local.yml` override for laptop
  self-hosting dry runs. It exposes backend, frontend, and collab on
  localhost ports and disables Caddy.
- CLI onboarding now says to run `stash connect` when setup finishes
  without connecting a repo, instead of telling users to commit a
  `.stash` file that was never created.
- Self-hosting now uses a prebuilt `ghcr.io/fergana-labs/stash-frontend`
  image alongside the backend and collab images, so
  `docker-compose.prod.yml` no longer builds application containers on the
  target machine.
- Backend now routes markdown and HTML uploads to the pages table on the
  one upload endpoint, so every surface (frontend drag-drop, CLI `stash
  files upload`, MCP `stash_upload_file`) gets the same behavior. The
  response is a discriminated `{kind, ...}` payload — `kind: "page"` for
  md/html, `kind: "file"` for everything else.
- MCP server gained ten tools to reach parity with the CLI on agent-
  useful surfaces: discover (`stash_search_public_stashes`,
  `stash_read_public_stash`), page search (`stash_search_pages`),
  session ops (`stash_session_transcript`, `stash_delete_session`),
  invite management (`stash_create_invite`, `stash_revoke_invite`),
  stash access control (`stash_set_stash_access`), and table tooling
  (`stash_update_table`, `stash_export_table`).
- Renamed the three unprefixed MCP tools to share the `stash_` prefix
  with the rest of the surface: `stash_list_trash`, `stash_restore`,
  `stash_purge`.
- Added `BACKEND_INTERNAL_URL` env var so docker / self-host deployments
  route the Next.js server-side fetches at the in-network backend
  hostname instead of looping through the public URL. Public Stash pages
  no longer 500 on a fresh self-host boot.
- Added `INTEGRATIONS_ENCRYPTION_KEY`, `ANTHROPIC_API_KEY`,
  `ANTHROPIC_MODEL`, and `ANTHROPIC_FAST_MODEL` to `.env.example` —
  every variable `backend/config.py` actually reads is now in the
  reference file.
- Refreshed user-facing docs (`README`, `ARCHITECTURE`, `USE_CASES`,
  `DESIGN`, the `frontend/docs/*` pages) to match shipped product
  surface: real concept names, real CLI commands, real container set
  for self-hosting.
- Bumped the Claude Code plugin to 0.1.84 so the cached
  SessionStart context refreshes — older versions injected
  `stash history *` / `stash notebooks list` references to commands
  that no longer exist.
- Added `stash vfs`, an app-level virtual filesystem shell for browsing
  Stash with bash-shaped commands and editing existing writable pages.
- Kept `stash mount` hidden as experimental spike code; the supported
  production path is `stash vfs`.

## v0

Initial open-source release.
