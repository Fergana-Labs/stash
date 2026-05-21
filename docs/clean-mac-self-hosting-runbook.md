# Clean Mac Self-Hosting Runbook

Use this runbook before onboarding a self-hosted user. The goal is to prove that
a clean macOS account can install, start, sign in, connect the CLI, and use a
workspace without relying on anything from an existing developer machine.

This is a release gate, not a demo script. If a step fails, record the command,
the error, and the service logs before trying a workaround.

## Success Criteria

- A clean macOS user can start the production Docker Compose stack from a fresh clone.
- `https://localhost/health` or the real deployment domain returns `{"status":"ok"}`.
- The browser can create a first account and land in a workspace.
- The CLI can authenticate against the self-hosted instance without manual API key copying.
- `stash connect` creates a repo `.stash` file and can read/write workspace data.
- Optional file uploads either work with configured S3-compatible storage or fail clearly when storage is not configured.

## Time Box

Plan for 60-90 minutes the first time:

- 15 minutes for clean macOS user setup.
- 20 minutes for Docker and repo setup.
- 20 minutes for production Compose startup and health checks.
- 20 minutes for browser, CLI, and workspace smoke tests.
- 10 minutes for cleanup and notes.

## Test Matrix

Run the production path first. The local-dev path is only a fallback for app
smoke testing after a production blocker is captured.

| Path | Purpose | Passing means |
| --- | --- | --- |
| Production Compose | Tests the documented self-hosting flow using `docker-compose.prod.yml`. | Safe to give to a self-hosted user. |
| Source-built Compose | Tests app behavior from this checkout using local Docker builds. | Useful debugging data only; not a pass for published self-hosting. |

## 1. Create a Clean macOS User

Create a disposable standard macOS account named `stash-test`:

1. Open System Settings.
2. Go to Users & Groups.
3. Add a new standard user.
4. Log out of your normal account and log in as `stash-test`.

Keep this account clean:

- Do not copy your existing `~/.stash`, shell config, agent configs, Docker volumes, or SSH keys.
- Use a fresh browser profile.
- If Docker Desktop is already installed globally, still launch it once from this user account and wait until it says it is running.

## 2. Install Prerequisites

In the clean account:

```bash
xcode-select --install
```

Install Docker Desktop if it is not already installed:

```bash
open https://www.docker.com/products/docker-desktop/
```

After installing or launching Docker Desktop, verify it from Terminal:

```bash
docker version
docker compose version
```

Install `git` if the clone command below fails:

```bash
xcode-select --install
```

## 3. Fresh Clone

Clone the repository into the clean account:

```bash
mkdir -p ~/src
cd ~/src
git clone https://github.com/Fergana-Labs/stash.git
cd stash
```

If you are testing a branch, check it out now:

```bash
git fetch origin
git checkout <branch-name>
```

Record the exact commit:

```bash
git rev-parse --short HEAD
```

## 4. Configure Production Compose For Localhost

Use `localhost` when testing on a Mac with no public DNS. Use the real domain
instead when rehearsing the exact friend onboarding path.

```bash
cp .env.example .env
```

Set these values in `.env`:

```dotenv
POSTGRES_USER=stash
POSTGRES_PASSWORD=stash-clean-mac-test
POSTGRES_DB=stash
PUBLIC_URL=https://localhost
CORS_ORIGINS=https://localhost
EMBEDDING_PROVIDER=local
INTEGRATIONS_ENCRYPTION_KEY=
```

Notes:

- This deliberately tests the documented no-key embedding path. If backend logs show missing `sentence-transformers`, record it as a blocker or docs bug.
- To test hosted embeddings instead, set `EMBEDDING_PROVIDER=openai` and provide `OPENAI_API_KEY`.
- `INTEGRATIONS_ENCRYPTION_KEY` can stay blank if you are not testing Google/GitHub/Notion integrations.

Change the local Caddy host:

```bash
perl -0pi -e 's/app\.example\.com/localhost/' Caddyfile
```

For a real domain rehearsal, use:

```bash
perl -0pi -e 's/app\.example\.com/<your-domain>/' Caddyfile
```

Then set:

```dotenv
PUBLIC_URL=https://<your-domain>
CORS_ORIGINS=https://<your-domain>
```

## 5. Production Image Gate

This must pass before onboarding anyone to the documented self-hosting flow:

```bash
docker compose -f docker-compose.prod.yml pull
```

Expected: all application images pull successfully.

Release blockers to record:

- Docker rejects an image reference as invalid.
- GHCR denies unauthenticated pulls.
- Any required image tag is missing.

Do not count the source-built fallback as a pass for this gate.

## 6. Start Production Compose

```bash
docker compose -f docker-compose.prod.yml up -d
docker compose -f docker-compose.prod.yml ps
```

Wait until `backend` is healthy. Then check:

```bash
curl -k https://localhost/health
curl -k https://localhost/api/v1/users/cli-auth/sessions \
  -H 'content-type: application/json' \
  -d '{"device_name":"clean-mac-smoke"}'
```

Expected:

- `/health` returns `{"status":"ok"}`.
- The CLI auth session request returns a JSON object with `session_id`.

If the backend does not become healthy, capture:

```bash
docker compose -f docker-compose.prod.yml logs --tail=200 backend
docker compose -f docker-compose.prod.yml logs --tail=200 postgres
docker compose -f docker-compose.prod.yml logs --tail=200 redis
```

## 7. Browser Smoke Test

Open:

```bash
open https://localhost
```

Accept the local certificate warning if macOS shows one.

Test:

1. Create a new account.
2. Confirm a workspace is created.
3. Create a page in the workspace.
4. Refresh the browser and confirm the page is still there.
5. Open the browser network panel and confirm API calls go to `https://localhost/api/...`, not `localhost:3456`, `joinstash.ai`, or `api.joinstash.ai`.

Expected: account creation and normal workspace navigation work without editing browser storage or copying API keys.

If the page does not load or API calls go to the wrong origin, capture:

```bash
docker compose -f docker-compose.prod.yml logs --tail=200 frontend
docker compose -f docker-compose.prod.yml logs --tail=200 caddy
```

## 8. CLI Install And Auth

Install the CLI from the same checkout so the test matches the server:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
export PATH="$HOME/.local/bin:$PATH"
uv tool install --force --reinstall "$PWD"
stash --help
```

Then test the user-facing auth flow:

```bash
stash signin --api https://localhost
```

Expected:

- The CLI opens a browser page on the self-hosted instance.
- The browser signs in or authorizes the current user.
- The CLI receives an API key and exits successfully.

Known failure to catch:

- If the CLI opens `/connect-token` but the app only supports `/login?cli=...`, record it as a blocker.
- If the CLI waits until timeout, capture the opened URL and backend logs.

Manual API key auth is useful for continuing the smoke test, but it is not a pass:

```bash
stash auth https://localhost --api-key <api-key>
```

## 9. Repo Connection Smoke Test

Create a disposable repo:

```bash
mkdir -p ~/src/stash-smoke-repo
cd ~/src/stash-smoke-repo
git init
git config user.name "Stash Smoke"
git config user.email "stash-smoke@example.invalid"
echo '# Stash smoke repo' > README.md
git add README.md
git commit -m 'initial smoke repo'
```

Connect it:

```bash
stash connect
```

Expected:

- `stash connect` creates or selects a workspace.
- `.stash` is written with the workspace id.
- The CLI does not point back to managed Stash.

Verify reads and writes:

```bash
stash files add-page "Clean Mac Smoke" --content "self-host smoke test"
stash files pages
stash files search "self-host smoke"
stash sessions push "clean mac event" --agent cli --type smoke
stash sessions query --limit 5
stash vfs ls /
```

Expected:

- The page appears in `stash files pages`.
- Search finds the page.
- The session event appears in `stash sessions query`.
- `stash vfs ls /` lists workspace data.

## 10. Optional File Upload Test

Run this only when S3-compatible storage is configured in `.env`.

```bash
cd ~/src/stash-smoke-repo
printf 'hello from clean mac\n' > upload-smoke.txt
stash files upload upload-smoke.txt --json
```

Expected:

- With S3 configured, the command returns JSON with an app URL.
- Without S3 configured, the command fails clearly with file storage not configured.

## 11. Optional Agent Streaming Test

Run this only if the clean user has a supported coding agent installed.

```bash
cd ~/src/stash-smoke-repo
stash settings
```

Confirm the desired agent is enabled. Start a short agent session in the repo,
then check:

```bash
stash sessions query --limit 20
stash sessions agents
```

Expected:

- New events appear for the agent.
- No hook warnings appear in the agent UI.

## 12. Source-Built Fallback

Use this only after production Compose has failed and the failure is recorded.
It helps separate app bugs from image publishing or registry bugs.

```bash
cd ~/src/stash
docker compose up -d --build
docker compose ps
curl http://localhost:3456/health
open http://localhost:3457
```

The local-dev stack publishes:

- Backend: `http://localhost:3456`
- Frontend: `http://localhost:3457`
- Collab: `http://localhost:3458`

Repeat the browser and CLI smoke tests against:

```bash
stash signin --api http://localhost:3456
```

If this path works but production Compose fails, the blocker is likely in
image publishing, production environment injection, Caddy routing, or TLS.

## 13. Cleanup

From the repo directory:

```bash
docker compose -f docker-compose.prod.yml down -v
docker compose down -v
```

Remove local CLI state:

```bash
rm -rf ~/.stash
uv tool uninstall stashai || true
```

Then delete the `stash-test` macOS account from System Settings.

## 14. Report Template

Use this format for the final test note:

```markdown
## Clean Mac Self-Hosting Smoke Test

- Date:
- macOS version:
- Docker Desktop version:
- Stash commit:
- Production Compose: pass/fail
- Browser signup: pass/fail
- CLI signin: pass/fail
- `stash connect`: pass/fail
- CLI read/write smoke: pass/fail
- File upload: pass/fail/not tested
- Agent streaming: pass/fail/not tested

### Blockers

1.

### Notes

-
```
