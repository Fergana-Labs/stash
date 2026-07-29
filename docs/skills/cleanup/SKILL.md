---
name: cleanup
description: Find duplicates, dead links and untagged items in a saved library and propose what to do about each.
when_to_use: When the user asks to tidy up their bookmarks, clean their library, deal with duplicates or broken links, or asks what needs attention.
version: "1"
---

# Cleaning up a saved library

**Propose, never dispose.** You do not delete, merge, retag or archive
anything in this skill. You produce a list the user can act on, and you act
only on items they name afterwards. An agent that quietly tidies someone's
library is an agent they stop trusting.

## The three piles

The Bookmarks app computes these; read them rather than deriving them.

**Duplicates** — the same page saved more than once, matched on a normalized
URL (protocol, `www.`, trailing slash and tracking params ignored). The
oldest save is treated as the original.

For each group, recommend which to keep, and say why: prefer the one whose
saved copy actually captured content over a link-only save, then the one with
topics already on it, then the oldest. Note when the "duplicates" are not
really duplicates — a URL that serves different content over time, for
instance — and leave those alone.

**Broken** — a link the checker got a 404 or 410 from. Note it only trusts
those two codes, so a broken item is genuinely gone rather than merely
unreachable. For each, check whether the saved copy still has the content: if
it does, the recommendation is "keep, the archive is the point now"; if it is
link-only, there is nothing left and it can go.

**Untagged** — no topics. Usually means enrichment failed or the page had
nothing to read. Propose topics from the existing vocabulary — read it off
the `Topics` column's options — rather than inventing new ones; a cleanup
pass that adds twelve new near-synonyms has made things worse.

## Write it

Group by pile. Each item: what it is, the recommendation, one clause of why,
and a link. Lead with a one-line count of each pile so the user can decide
where to spend their attention.

End with the single sentence they need: "Say which of these to action and
I'll do it." Then stop.

## Rules

- No action without an explicit instruction naming what to act on.
- If a pile is empty, say so in one line rather than omitting it — knowing
  there are no broken links is worth something.
- Never recommend deleting the last remaining copy of anything.
