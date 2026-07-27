# Skills

A skill is a folder containing a `SKILL.md` — instructions an agent reads
when a task matches. Skills are how the product turns a pile of saved
material into something an agent can act on without being told the same
things every time.

## Two mechanisms, two jobs

These get conflated. They are independent, and most skills want both.

| | What it does | How | Reaches the agent? |
|---|---|---|---|
| **Seeding** | Every scope gets a working copy at signup | `backend/skills/<name>/SKILL.md`, copied by `skill_seeds.py` | **Yes** — it's a folder in their scope |
| **Publishing** | Others can find, view and fork it | A row in the `skills` table with `discoverable = true`; shows in Discover and the home feed | **No** — not until installed |

The reason seeding is load-bearing: `agent_runtime.list_skills` reads
*"folders with SKILL.md in this Stash account"*. An agent cannot see the
published-skills table at all. So a skill that is only published shows up in
Discover and does nothing until someone installs it, and a skill that is only
seeded works but is invisible to everyone else.

## Adding a skill

Create `backend/skills/<name>/SKILL.md` with frontmatter:

```markdown
---
name: cleanup
description: One line, shown in listings.
when_to_use: The phrases and situations that should route to this skill.
version: "1"
---

# Body
```

That is the whole change. `skill_seeds.default_skills()` reads the directory,
new signups get it immediately, and `tasks/skill_backfill.py` seeds it into
existing scopes on its next hourly pass.

`when_to_use` is what an agent routes on. A skill without it seeds fine and
is never selected, which is why a test asserts every skill has one.

## The seeded skills

**Output formats** — turn saved material into a document.

- **`slides`** — HTML slide decks: the 1920×1080 fixed-canvas format, safe
  areas, per-slide types. Also embedded verbatim in the landing-page demo.
- **`briefing`** — a named set (a topic, a folder, explicit items) into a
  one-page brief where every claim links to its source.
- **`study-guide`** — the same material as something to learn from.
- **`timeline`** — the same material ordered by when things happened.

**Library skills** — operate on the Bookmarks app, using enrichment
(`Summary`, `Topics`) and the derived filters.

- **`brief`** — what you saved in a period, led by the *thread* through it
  rather than an inventory. Date-scoped via `Saved gte <date>`. The natural
  target for a weekly cron.
- **`resurface`** — a few old saves worth revisiting, each with a specific
  *why now* drawn from what you have actually been working on (history,
  recent saves, memory). Explicitly refuses to resurface anything it can't
  justify — the home feed already does random resurfacing, and the reason is
  the entire added value.
- **`overview`** — four charts (saves over time, topics by volume, sources,
  topic over time) with the reading written next to each. Refuses to chart a
  corpus too small to support it.
- **`cleanup`** — duplicates, dead links and untagged items, with a
  recommendation per item. **Proposes, never disposes**: no deletes, merges
  or retags without an explicit instruction naming what to act on.

## How library skills address a set

Skills receive a *query*, not a payload. A skill handed 60 rows of JSON
breaks at 6,000, can't be re-run from a cron, and can't page.

`query_table` takes filters, sorting and paging, and returns the column
list alongside the rows so the agent reads cells by name rather than
guessing at `col_9f07…`:

```
query_table(table_name="Bookmarks",
            filters=[{"column_id": "<Saved>", "op": "gte", "value": "2026-07-20"}],
            limit=100)
```

Ops: `eq`, `gte`, `lte`, `contains`, `is_empty`, `is_not_empty`. Dates are
stored as ISO strings, so `gte`/`lte` compare correctly. That covers most
sets a skill wants:

| Set | Filter |
|---|---|
| Saved this week | `Saved gte <date>` |
| Untagged | `Topics is_empty` |
| Broken | `Status eq Broken` |
| A topic | `Topics contains <label>` |

**Duplicates is the exception.** It is an aggregation (`GROUP BY
normalize(url) HAVING count > 1`), not a row predicate, so no filter
expresses it. The app computes it at `/api/v1/me/apps/bookmarks/rows?filter=duplicates`;
an agent can call that or compute it while paging.

## Scheduling

`agents.schedule_cron` + `schedule_prompt`, fired by
`tasks/agent_schedules.py`. A weekly digest is a cron row invoking `brief`,
not new machinery. Output lands as a page in the user's stash, following the
curator's existing pattern.

## Known limitations

**Seeding does not update.** `_seed_skill` is idempotent per skill: if a
scope already has a folder of that name containing a `SKILL.md`, it is left
alone, because the user may have edited it. So improving `briefing` does not
reach anyone who already has it — only scopes missing it entirely.

That is deliberate (never clobber a user's edits) but it means skill content
effectively freezes per user at first seed. The fix is to seed *by installing
from a published skill* so there is one source of truth and updates can
propagate with a version check. It needs its own design pass: a fresh or
self-hosted instance with no published skills would then seed nothing.

**Nothing is published yet.** None of the seeded skills — including `slides`,
which predates this work — has a row in the `skills` table, so none appear in
Discover. Publishing needs an owning account (`skills.owner_user_id`), which
is a product decision about whether a "Stash" system account exists.
