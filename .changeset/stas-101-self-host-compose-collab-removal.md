---
"stash": patch
---

Remove the orphaned `collab` service override from `docker-compose.local.yml` and make
version/pin promotion explicit.

**What was removed:** the `collab:` block (`ports: ["3458:3458"]`) in
`docker-compose.local.yml`. PR #982 deleted the collab service from the repository,
but its local-override entry was never cleaned up. Because compose *creates* a
service declared only by a later `-f` file and then rejects it for having no
image/build context, the documented self-host command
`docker compose -f docker-compose.prod.yml -f docker-compose.local.yml up -d` failed
with `service "collab" has neither an image nor a build context specified: invalid
compose project`. The block is removed outright — no `!override` tag or other
suppression was used. The surviving `backend`, `frontend`, and `caddy`
(`profiles: production-domain`) overrides are unchanged.

**Version/pin promotion is now explicit:** `pyproject.toml` (the CLI release switch)
and all five GHCR pins in `docker-compose.prod.yml` (`stash-backend` x4,
`stash-frontend`) are set to the same release version (`0.1.368`, bare tags — the `v`
belongs only to the git tag). `backend/tests/test_docker_release_contract.py` now
asserts pins == CLI version, so the silent drift can't recur.

**Why it had to be hand-bumped:** `.github/workflows/bump-plugin-version.yml` is the
repo's release-version automation and still fires on every `main` push matching
`cli|stashai|plugins|backend|frontend`, but its direct `git push` has been declined by
repository rule GH013 ("Changes must be made through a pull request") since its last
green run `31410354104` (2026-08-10) — so it lands nothing and its `Publish release`
step is always skipped. That is exactly why the pins had drifted two releases behind
the CLI. This PR's own version commit is therefore the release mechanism: merging it
triggers `publish.yml`, which tags `v<VER>`, publishes the CLI to PyPI, and dispatches
`docker-publish.yml` → `ghcr.io/fergana-labs/stash-backend:<VER>` +
`stash-frontend:<VER>` (bare image tags). Whether to repair that workflow (open a bump
PR / add a ruleset exemption) or delete it is a founder decision — this PR does neither.

**Out of scope (recorded, not done here):** `plugins/claude-plugin/.claude-plugin/plugin.json`
and `.claude-plugin/marketplace.json` stay at `0.1.436` (independent marketplace
sequence); the stale `(cd collab && npm audit …)` instructions in
`docs/security-readiness.md:87,98` are pre-existing and outside this diff.

**Note:** this repo has no tooling that consumes `.changeset/`; `CHANGELOG.md`'s
Unreleased bullet is the authoritative release note. This file exists because the task
framework mandates a removal record for a net-negative change — the founder may delete
it.
