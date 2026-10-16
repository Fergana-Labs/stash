# Website taste in the product

Website-design preferences are a capability of the existing **eval wizard** at
`/reward-models/wizard`. There is no separate Website taste navigation item or
manual history-search screen. The older `/reward-models/taste` URL resumes the
existing unfinished website-design wizard and preserves its recovered examples.

The wizard agent calls `website_eval` to prepare the same canonical eval, search
and read history itself, gather rendered evidence, show inline preference cards,
build the frozen multimodal probe, and connect the user's own agent. The normal
wizard sidebar shows the actual probe and preference counts. Generic evals keep
their existing setup flow.

The agent owns discovery and orchestration. Users express the judgment they want,
confirm or correct source-grounded visual preferences, and inspect results in the
conversation. They do not type search queries or manage technical source IDs.
Pending jobs show inline progress, persist through navigation, and notify the
wizard to continue when finished. Validation failures remain visible blockers.

The same eval ID serves through the ordinary predict/MCP surface, delegating to
the frozen activation probe for request + public trace + source + screenshot
checkpoints. Generic training is guarded against accidentally replacing that
probe with the ordinary verdict-feature classifier. Publishing ends setup and
opens the ordinary eval URL; later edits use MCP.

Inline results retain same-brief comparison, exact per-design skills and diffs,
source/pixel evidence, and separate human preferences. GEPA and weight refinement
are independent branches; DPO uses the original skill, not GEPA instructions.
Missing and invalid outputs never become successful results. The separate
loopback design journal remains an operator inspection tool.


## Operator setup

Migration **0249** adds owner-scoped workspace/job/prediction tables. The frontend
and backend use the ordinary reward-model feature flag and authentication. The
API never accepts server filesystem locations. To adopt an existing private pilot:

```sh
python -m scripts.adopt_taste_workspace --owner ACCOUNT_UUID \
  --probe /private/path/to/probe --experiment /private/path/to/experiment \
  --related-eval SUPPORTING_NATIVE_EVAL_UUID
```

Repeat `--related-eval` for supporting calibration evals. Adoption preserves the
eval binding and reviews. Empty drafts and explicitly linked supporting
evals are tucked away in the eval list, with a toggle to reveal them; nothing is
deleted. Artifacts/credentials/history stay outside Git.

`TASTE_CLOUD_ENABLED=1` enables explicit cloud actions; it does not approve a new
budget. `TASTE_WORKSPACE_ROOT` must point at persistent shared storage accessible
by the API and the heavy Celery worker for a hosted deployment. Adopted bundle
paths must also be present on that storage. A temporary local directory is only
appropriate for local development. Existing ledger reservations are shared by
rebuilt versions and runtime scoring so a new version cannot reset the pilot's
allowance. Existing provider request/time caps remain in effect.

Backend images include the operator harness and GEPA, without pretrained model
packages. Rendering uses sandboxed Python Playwright in deployed images and the
matching Node renderer in the local checkout. No network or JavaScript is enabled
when rendering generated HTML.

The first pilot remains failed and blocked. Native experiment controls do not
waive validation, silently restart GPU work, or claim a successful post-trained
result. Production deployment and live cloud execution require separate actual
verification; UI/CPU checks do not establish either.
