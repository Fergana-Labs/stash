"""Bootstrap Skills a new user can switch on with one click.

Stash derives Skills from traces, but a fresh stash has no traces to learn
from. This catalog is the answer to "what could I be automating that I'm
not?" — each entry is a complete, working SKILL.md an agent can follow today,
not a placeholder. Installing one creates an ordinary folder-backed Skill the
user can then edit, share, or switch off like any other."""

from __future__ import annotations

SUGGESTED_SKILLS: list[dict] = [
    {
        "key": "company-glossary",
        "name": "Glossary of your company",
        "description": (
            "Keep a glossary of the words, acronyms, and product names your team uses, "
            "and use it to read and write like an insider. Use whenever a message, "
            "ticket, or doc contains a term specific to this company."
        ),
        "instructions": """\
Maintain `glossary.md` in this Skill's folder as the single list of company-specific terms.

## When you meet an unfamiliar term
1. Check `glossary.md` first. If the term is there, use that meaning.
2. If it is not, infer the meaning from context, then add an entry so the next session already knows it.

## When the user uses a term consistently
Add it. A term counts as company vocabulary when it names a product, team, customer, internal tool, metric, or process — not general programming vocabulary.

## Entry format
One line per term, alphabetical:

```
- **Term** — one-sentence meaning. (Where it shows up: e.g. Linear, #eng-alerts, the billing service)
```

## When writing on the user's behalf
Use the glossary's spellings and capitalization exactly. Do not expand an acronym the team never expands.
""",
    },
    {
        "key": "slide-deck-builder",
        "name": "Slide deck builder",
        "description": (
            "Turn an outline, doc, or set of notes into a presentable slide deck as a "
            "single HTML file. Use when the user asks for slides, a deck, a pitch, or a "
            "presentation."
        ),
        "instructions": """\
Build decks as one self-contained HTML file: inline CSS, no external assets, one `<section class="slide">` per slide, 16:9 (1280×720) canvas, arrow keys and click to advance.

## Process
1. Read the source material fully before writing a single slide.
2. Draft the outline first as a numbered list — one line per slide with its single takeaway — and show it to the user before building.
3. Build the deck. One idea per slide; a title plus at most five short lines, or one chart/diagram, or one big number.
4. Open it in a browser and check every slide fits the canvas without overflow.

## Style
- Title slide, then agenda only if the deck has more than eight slides.
- Consistent type scale: title 56px, heading 40px, body 28px. Never smaller than 24px.
- One accent color. Dark text on light background unless the user asks otherwise.
- Speaker notes go in a `<aside class="notes">` inside each slide, hidden by default.

## Hand-off
Return the file path and a one-line summary per slide.
""",
    },
    {
        "key": "pr-description-writer",
        "name": "PR description writer",
        "description": (
            "Write a pull request description from the branch's diff and commits. Use "
            "when opening a PR or when the user asks for a PR summary."
        ),
        "instructions": """\
Read the full diff (`git diff <base>...HEAD`) and the commit messages before writing. Never describe a change you did not see in the diff.

## Structure
```
## What
Two or three sentences: the user-visible or developer-visible change, in plain words.

## Why
The problem or request that motivated it. Link the issue or ticket if the branch name or commits reference one.

## How
Bullets for each notable implementation decision a reviewer would want to know about — new tables, changed contracts, removed code paths, anything risky.

## Testing
What was run (test command and result), and what was checked by hand.
```

## Rules
- No filler ("This PR aims to…"). Start with the change.
- Mention migrations, env vars, and breaking changes explicitly, in their own bullet.
- Keep it under 200 words unless the diff is genuinely large.
- Do not @-mention anyone.
""",
    },
    {
        "key": "weekly-status-update",
        "name": "Weekly status update",
        "description": (
            "Draft the user's weekly status update from what actually happened: merged "
            "PRs, closed tickets, commits, and recent agent sessions. Use when the user "
            "asks for a weekly update, standup summary, or 'what did I do this week'."
        ),
        "instructions": """\
Gather evidence first, then write. Sources, in order of trust:
1. Merged PRs and closed tickets in the last seven days (`gh pr list --author @me --state merged --search "merged:>=<date>"`).
2. Commits on any branch in the last seven days (`git log --author=<user> --since="7 days ago" --all --oneline`).
3. Recent Stash sessions (`stash sessions list`), for work that never became a commit.

## Format
```
**Shipped**
- <one line per merged PR or closed ticket, with link>

**In progress**
- <one line per open branch or ticket, with the concrete next step>

**Blocked / needs a decision**
- <only if real; omit the section otherwise>

**Next week**
- <two to four items, drawn from open work — never invented>
```

## Rules
- Every "Shipped" line must be backed by a link or commit hash.
- Write in the first person, past tense, no adjectives.
- Under 150 words. Ask before sending anywhere.
""",
    },
    {
        "key": "meeting-notes-to-actions",
        "name": "Meeting notes to action items",
        "description": (
            "Turn raw meeting notes or a transcript into decisions, owners, and dated "
            "action items. Use when the user pastes notes or shares a meeting link."
        ),
        "instructions": """\
Read the whole set of notes before extracting anything. Then produce exactly three lists.

## Output
```
**Decisions**
- <what was decided, stated as a fact — not "we discussed">

**Action items**
- [ ] <verb-first task> — @owner — due <date or "no date given">

**Open questions**
- <question, and who is expected to answer it>
```

## Rules
- Only include an owner if the notes name one. Never guess an owner.
- Only include a date if the notes state one. Write "no date given" otherwise.
- Merge duplicates; drop anything that is neither a decision, a task, nor a question.
- If the notes mention a follow-up meeting, add it as an action item with the organizer as owner.
- Offer to create tickets for the action items, but do not create them until asked.
""",
    },
]


def catalog() -> list[dict]:
    return SUGGESTED_SKILLS


def find(key: str) -> dict:
    for skill in SUGGESTED_SKILLS:
        if skill["key"] == key:
            return skill
    raise KeyError(key)
