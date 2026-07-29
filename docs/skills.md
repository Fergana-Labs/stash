# Skills

A Skill is a folder containing `SKILL.md`. Public Skills appear in Discover,
and users explicitly install the ones they want.

Stash does not seed Skills into user accounts. The Stash-authored skills in
`docs/skills/` reach users only through Discover, and no runtime task copies
them into an account.

## The library

- `brief` — explain the thread through saves from a period.
- `cleanup` — propose actions for duplicates, dead links, and untagged saves.
- `overview` — chart topics, sources, and saves over time.
- `resurface` — find old saves that matter to the user's current work.
- `slides` — author fixed-canvas HTML slide decks.

Each declares `examples:` in its frontmatter — the starter prompts the Skills
launcher offers as one-click runs.

## Publication

These are published to the `stash-curated` service account by importing this
repo's `docs/skills` directory:

```
POST /api/v1/admin/discover-skills/import
X-Admin-Token: <ADMIN_PASSWORD>
{"repo_url": "https://github.com/Fergana-Labs/stash/tree/main/docs/skills"}
```

The `/tree/<branch>/<dir>` suffix is what keeps the import to the library —
without it the importer also publishes every unrelated `SKILL.md` in the repo
(`backend/static`, `www/public/smb`). Re-running tracks upstream: skills are
matched by `source_github_url` and their contents replaced in place, so slugs
and view counts survive an edit. Run it after merging a change to any
`docs/skills/*/SKILL.md`.

Publication must not add a signup seed, startup hook, or periodic backfill.

## Running one

An agent resolves skills from its own scope, never from the Discover catalog,
so `POST /api/v1/me/skills/install` puts a published skill in the caller's
scope before the first run. It is idempotent by skill name — the launcher
calls it on every run, and forking each time would leave a user picking
between `brief (2)` and `brief (3)`.
