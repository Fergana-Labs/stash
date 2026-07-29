---
name: brief
description: Brief the user on what they saved in a period — the thread running through it, not a list.
when_to_use: When the user asks what they saved this week/month, wants catching up on recent saves, or a scheduled digest fires.
examples:
  - Brief me on what I saved this week.
  - What was the thread running through last month's saves?
  - Catch me up on everything I saved and haven't read.
version: "1"
---

# Briefing new saves

A period's saves are not a list to recite. The user already knows they saved
things; what they don't know is what those saves add up to. Lead with the
thread, not the inventory.

## Get the set

Saves live in the **Bookmarks** table. Use `query_table` with a date filter
on the `Saved` column — dates are ISO strings, so `gte` compares correctly:

```
query_table(table_name="Bookmarks",
            filters=[{"column_id": "<Saved>", "op": "gte", "value": "2026-07-20"}],
            limit=100)
```

`query_table` returns the column list, so read the ids off that rather than
guessing. It also returns `total` — if it exceeds your limit, page with
`offset` before writing anything. Never brief on a partial set without saying
so.

Each row carries a `Summary` and `Topics` already, written when the item was
saved. Use them. Only open the full saved copy (the `Clip` link) when the
summary is too thin to place the item.

## Write it

1. **The thread** — two or three sentences on what connects this period's
   saves. If nothing connects them, say that; a week of scattered saves is a
   real finding, not a failure to look hard enough.
2. **What's worth your time** — at most three items, each with why *this*
   one and a link. Rank by what the user seems to be working on, not by
   what's most impressive.
3. **The rest** — one line each, grouped by topic, linked.
4. **Untouched** — anything saved in the period they haven't opened since.
   Say it plainly; don't nag.

## Rules

- Every claim links to the item it came from.
- No outside knowledge. If context helps, mark it "(context, not from your
  saves)".
- If the period is empty, say so in one line and stop. Do not pad.
- Write it as a page in the user's stash next to the material, when you can
  write pages; otherwise put it in the chat.
