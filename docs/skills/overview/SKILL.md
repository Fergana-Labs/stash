---
name: overview
description: Chart what's in the library — topics, sources, saves over time — and say what the shape means.
when_to_use: When the user asks for an overview of their saves, what they've been reading about, a breakdown by topic, or charts of their library.
examples:
  - Give me an overview of my library.
  - What have I been reading about lately, by topic?
  - Chart my saves over time and tell me what the shape means.
version: "1"
---

# Overview of a saved library

A chart on its own is decoration. Every chart here answers a question the
user would otherwise have to ask, and you say the answer in words next to it.

## Get the data

From the **Bookmarks** table via `query_table`. You need the whole table, not
a page — read `total` from the first call and page with `offset` until you
have it. Counting 100 of 4,000 saves and calling it a distribution is worse
than not charting at all.

Columns you'll use: `Saved` (ISO date), `Topics` (array), `Site`, `Type`,
`Status`.

## The four that earn their place

1. **Saves over time** — by week or month. Answers "am I still using this?"
   and shows bursts, which usually map to a project.
2. **Topics by volume** — horizontal bars, biggest first. Answers "what am I
   actually collecting?" Cap at the top 12 and group the tail as "other";
   a bar chart with 60 labels communicates nothing.
3. **Sources** — top domains. Answers "where does my reading come from?"
   Often uncomfortable and therefore useful.
4. **Topic over time** — the top few topics as lines. Answers "what am I
   moving toward, and what have I dropped?"

Skip any chart the data can't support. Fewer than ~20 saves, or fewer than
three distinct topics, means the honest output is a sentence, not a chart.

## Say what it means

Under each chart, one or two sentences of what it shows — the actual reading,
not a caption. "Two thirds of your saves are from three domains" is worth
writing. "This chart shows saves by domain" is not.

Close with what stands out across all four: a topic that stopped, a source
that dominates, a burst that maps to something they were building.

## Rules

- Charts follow the repo's dataviz conventions. Render as an HTML page in the
  user's stash so they can keep it.
- Label axes and units. Never a pie chart with more than five slices.
- Say the corpus size and date range you charted, so the reader knows what
  they're looking at.
