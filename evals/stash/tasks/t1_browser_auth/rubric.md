# Rubric — T1 browser_auth

Grade each criterion 0.0–1.0 with evidence from the patch + final assistant message.

## Criteria

1. **reuses_existing_browser_flow** (weight 0.35)
   The `stash login` command reuses the existing `cli-auth/sessions` browser-poll
   pattern already present in `stash connect`. The agent did NOT invent a new
   polling endpoint or a new session-token shape.

2. **login_opens_browser** (weight 0.20)
   Running `stash login` opens the user's browser (via `webbrowser.open`) to the
   frontend login page, rather than prompting for a username+password in the CLI.

3. **login_page_on_stashac** (weight 0.15)
   The URL opened points at the frontend host (stash.ac in managed mode, the
   configured frontend URL otherwise) — NOT at the backend API host.

4. **polls_backend_for_session** (weight 0.15)
   After opening the browser, the CLI polls the backend
   `/api/v1/users/cli-auth/sessions/{session_id}` endpoint until the session is
   authenticated, and saves the returned api_key to the stash config.

5. **no_regression_on_connect** (weight 0.10)
   The existing `stash connect` command still works (its browser-poll flow was
   not broken or duplicated).

6. **code_quality** (weight 0.05)
   Reasonable code: early returns, no overbroad try/except, no dead code, no
   unrelated refactors.

## Output format

Return JSON:

```json
{
  "criteria": [
    {"name": "reuses_existing_browser_flow", "weight": 0.35, "score": 0.9,
     "evidence": "login() now calls _run_browser_auth() shared helper; patch reuses cli-auth/sessions endpoint at cli/main.py:412",
     "issues": []}
  ],
  "overall_score": 0.84,
  "pass": true
}
```

`pass` = overall_score >= 0.7 AND all weight-≥0.15 criteria score >= 0.5.
