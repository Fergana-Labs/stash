# Website design demo

This extends the existing local sample account with the flow in the
[October 15 demo notes](https://notes.granola.ai/t/d3745d43-723c-48ef-9604-4716a5614dca-008umkv4):
inspect an HTML file, capture visual preferences, build an evaluator, improve the
file against it, and compare the rendered results.

The sample product and preference labels are synthetic. The screenshots, visual
extractions, judge answers, classifier fit, held-out check, generated HTML
revisions, and prediction receipts are produced by the actual services. The
setup conversation is a scripted sample describing those saved artifacts. The
UI presents a recorded run; switching stages does not launch another agent.

## Build the existing local fixture

Use the consolidated demo's `.env` and local account identity at
`/private/tmp/stash-consolidated-local/auth.json`. Start its database, backend,
and frontend, and install the frontend Playwright browser. Then run:

```sh
.venv/bin/python -u scripts/seed_website_demo.py
```

The script refuses databases other than the loopback
`stash_consolidated_local` database. It disables embedding models, fits only a
tiny classifier on 16 examples, and calls remote providers for vision, judgments,
HTML generation, trace labels, and completion estimates. It does not launch
local LLM training or inference. It creates one new evaluator and trace, without
replacing the other demo samples.

Provider answers and all four HTML/screenshot revisions are checkpointed under
`/private/tmp/stash-consolidated-local/website-demo`. The manifest contains the
trace, evaluator, wizard session, selected revision, and local demo URL. Completed
trace assessment is saved separately in `trace-assessment.json`. A failed
assessment can be resumed by importing `finish_trace` with the manifest's trace
ID and an initialized local database pool. Existing trace steps are never
silently overwritten on rerun.

## Present

Open the manifest's URL while signed into the local sample account. Use the four
stages to inspect the file, sample setup, all candidate evaluations, and before
and after screenshots. “Open trace” and “Open eval” navigate to the ordinary
owner-scoped product pages. The trace also links back to the website comparison.

The best revision is selected by the saved P(liked) prediction, retaining the
incumbent on ties. Worse attempts remain visible. The held-out set is deliberately
small and synthetic; neither its agreement nor P(liked) establishes universal
design quality.

Generated HTML is displayed as text and rendered only by the background
screenshot script, with scripts and network requests disabled. The app displays
PNG pixels rather than executing the generated document.

## Verify

```sh
cd frontend
npm test -- --maxWorkers=2 src/components/demos
npx tsc --noEmit
npx eslint src/components/demos 'src/app/(app)/reward-models/demos'
```

Inspect all four stages in a headless browser, follow the native trace and eval
links, and confirm the trace has persisted completion checkpoints and credits
for every agent action before presenting it.
