# evals/stash/

A/B eval testing whether the stash plugin improves Claude Code performance on multi-session handoff tasks.

See `PLAN.md` for design.

## Quickstart

```bash
cd evals/stash
pip install -e .

# 1. Extract seed events from Session A (needs ANTHROPIC_API_KEY)
python -m harness.extract_session tasks/t1_browser_auth/session_a.jsonl \
  > tasks/t1_browser_auth/seed_events.json

# 2. Run one Arm A trial (baseline)
python -m harness.runner --task tasks/t1_browser_auth --arm a --trial 0

# 3. Run one Arm B trial (stash-enabled)
python -m harness.runner --task tasks/t1_browser_auth --arm b --trial 0

# 4. Report
python -m harness.report --run-id <timestamp>
```

## Layout

```
evals/stash/
  PLAN.md                         # design
  tasks/t1_browser_auth/
    task.yaml                     # manifest
    starting_prompt.md            # the prompt both arms receive
    rubric.md                     # grading criteria
    session_a.jsonl               # snapshot of Session A (committed)
    seed_events.json              # extracted seed events
  harness/
    extract_session.py            # jsonl -> seed_events.json
    seed_workspace.py             # push events via stash CLI
    runner.py                     # spawn Claude Code per trial
    judge.py                      # LLM rubric grader
    metrics.py                    # transcript -> metrics
    report.py                     # aggregate -> summary
  configs/
    models.yaml                   # agent model, judge model
    stash.yaml                    # stash API base URL, eval account config
  runs/                           # gitignored, per-trial artifacts
```
