# Skills

A Skill is a folder containing `SKILL.md`. Published Skills are publicly
readable at their `/skills/<slug>` URL, and users explicitly install the ones
they want.

Stash does not seed Skills into user accounts. The Stash-authored skills in
`docs/skills/` reach users only through the mini-programs strip and their
public URLs, and no runtime task copies them into an account.

## The library

- `brief` — explain the thread through saves from a period.
- `cleanup` — propose actions for duplicates, dead links, and untagged saves.
- `overview` — chart topics, sources, and saves over time.
- `resurface` — find old saves that matter to the user's current work.
- `slides` — author fixed-canvas HTML slide decks.

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

## Adding and running

An agent resolves skills from its own scope, never from anyone else's,
so a published skill has to be added before anything can run it. `POST
/api/v1/me/skills/install` does that, idempotently by skill name, so pressing
Add twice can't leave a user picking between `brief` and `brief (2)`.

**Adding is always explicit.** Running a skill never installs one as a side
effect: the Skills launcher only opens on skills already in your Skills, and
the strip above a mini program offers Add for the ones you don't hold. A skill
shared with you is not in your scope either — same as a shared folder, you copy
it in before it's yours — so it can't be run until you do.

The launcher shows the skill's own frontmatter and sends `Use the <name>
skill.` followed by the user's request. Naming the skill is what makes Run mean
*that* skill: the agent otherwise picks skills by matching the message against
each `when_to_use`, which makes an unnamed run a guess. That one templated line
is the whole of what the product composes — the skill format carries no fields
for the launcher, and nothing is authored per skill.
