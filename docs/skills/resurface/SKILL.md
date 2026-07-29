---
name: resurface
description: Pick a few old saves worth revisiting now, and say why now.
when_to_use: When the user asks what they've forgotten, wants something resurfaced from their archive, or a scheduled resurfacing fires.
examples:
  - What should I revisit from my archive this week?
  - Find old saves that connect to what I'm working on now.
  - Surface something I bookmarked and never used.
version: "1"
---

# Resurfacing old saves

The home feed already resurfaces saved items at random. Doing that again adds
nothing. The whole value here is **why now** — the connection between
something the user saved months ago and what they are doing this week.

If you cannot find that connection for an item, do not resurface it. Three
items with a real reason beat ten without.

## Find candidates

Old saves, from the **Bookmarks** table:

```
query_table(table_name="Bookmarks",
            filters=[{"column_id": "<Saved>", "op": "lte", "value": "<90 days ago>"}],
            limit=100)
```

## Find the reason

This is the part a bookmark manager cannot do, and it is the only reason this
skill is worth running. Look at what the user has actually been doing:

- `search_history` / `fetch_history` — what they have been working on lately
- recent saves — what they are reading about now
- their memory wiki — standing interests

Then look for old saves that speak to it: an article they saved before a
problem became relevant, a technique they bookmarked and never used, a
counter-argument to a position they have since adopted.

## Write it

Two to four items. For each:

- **What it is** — one line, from its summary.
- **Why now** — the specific connection, naming what they were doing.
  "You saved this in March; you spent this week on retry logic and it argues
  the opposite of the approach you took." Not "this might be relevant."
- A link to the saved copy.

Say nothing else. No preamble, no encouragement to read more.

## Rules

- Never resurface something saved in the last month. It is not forgotten yet.
- Never resurface the same item twice in a row; check whether a previous
  resurfacing page already names it.
- If nothing has a real "why now", say "nothing from the archive connects to
  this week" and stop. That is the correct answer some weeks.
