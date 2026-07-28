# Skills

A Skill is a folder containing `SKILL.md`. Public Skills appear in Discover,
and users explicitly install the ones they want.

Stash does not seed Skills into user accounts. The Stash-authored drafts in
`docs/skills/` are documentation and review artifacts only. They do not appear
in Discover, and no runtime task copies them into an account.

## Documented drafts

- `brief` — explain the thread through saves from a period.
- `cleanup` — propose actions for duplicates, dead links, and untagged saves.
- `overview` — chart topics, sources, and saves over time.
- `resurface` — find old saves that matter to the user's current work.
- `slides` — author fixed-canvas HTML slide decks.

## Publication

Publication is handled separately through the existing public Skill system and
service account. That operational workflow is intentionally outside this PR.
Publishing a draft must not add a signup seed, startup hook, or periodic
backfill.
