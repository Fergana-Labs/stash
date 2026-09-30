# Running Stash

This guide covers the open-source code in this repository: session collection,
persistent knowledge, skills, the CLI, and the reward-model experiment. Training
and GEPA are included in `backend/services/rm/` and `rm_worker/`; the
[product docs](https://www.joinstash.ai/docs) describe the workflow. Existing
accounts keep their current experience; new accounts enter the experiment.
See [Hosted rollout](reward-models/ROLLOUT.md) for the account boundary.

## Connect your coding agent to hosted Stash

With [uv](https://docs.astral.sh/uv/) installed, run these commands in an
interactive terminal:

```bash
uv tool install stashai
stash signin
```

`stash signin` authenticates in your browser, then guides you through session
recording, which coding agents to record, and adding Stash instructions to your
current folder. It also offers to import historical conversations in the
background. If you accept, follow progress with `stash import-history --status`.

Recording is on during setup; pause it with `stash stop`. Re-run the wizard with
`stash setup`, or run `stash connect` from another project folder to add Stash
instructions and enable session uploads there. A Git repository is not required.

If you need to install uv as well, the installer handles that and launches signin:

```bash
bash -c "$(curl -fsSL https://joinstash.ai/install)"
```

Ask your coding agent whether it can access Stash, or browse from the CLI:

```bash
stash vfs ls /
stash vfs "rg \"database migration\" /"
```

Run `stash --help` or `stash <command> --help` for command documentation.

## Run from source locally

Install Git, uv, Node.js 20.9 or newer, and Docker with its daemon running.
Ports 3456 and 3457 must be available.

```bash
git clone https://github.com/Fergana-Labs/stash.git
cd stash
uv venv -p 3.12
source .venv/bin/activate
uv pip install -r backend/requirements.txt -r backend/requirements-dev.txt
npm --prefix frontend ci
./start.sh
```

For this setup, leave `DATABASE_URL` and `REDIS_URL` unset in your shell and
repo-root `.env`. The startup script provisions a local Postgres database and
Redis instance, starts the backend and workers, and serves the frontend.
Database migrations run when the backend starts. The script also generates a
durable integration-encryption key in `.env`.

Open <http://localhost:3457/login>. Check the backend from another terminal:

```bash
curl --fail http://localhost:3456/health
```

To connect the released CLI to this local server:

```bash
uv tool install stashai
stash signin --api http://localhost:3456
```

For editable CLI development, run `uv pip install -e .` in the activated virtual
environment. See [Contributing](../CONTRIBUTING.md) for tests and contribution
guidance. Optional provider keys and integration settings are documented in
[.env.example](../.env.example).

To run reward-model training, configure the [reward worker](../rm_worker/README.md)
with `RM_COMPUTE`, its Python interpreter, scratch space, provider credentials,
and private S3 storage. `./start.sh` includes a dedicated `reward` queue consumer;
training is separate from the ingestion workers. Local compute still requires S3.

## Self-host on a domain

Use a server with Git and Docker Compose, a domain pointing at that server, and
ports 80 and 443 available. The deployment uses prebuilt GHCR images pinned in
[docker-compose.prod.yml](../docker-compose.prod.yml).

```bash
git clone https://github.com/Fergana-Labs/stash.git
cd stash
cp .env.example .env
```

Before starting:

- Set `POSTGRES_USER`, `POSTGRES_PASSWORD`, and `POSTGRES_DB` in `.env`; replace
  the example database password.
- Set `PUBLIC_URL` and `CORS_ORIGINS` to your frontend origin, such as
  `https://app.example.com`.
- Replace `app.example.com` in [Caddyfile](../Caddyfile) with your domain.
- Configure any optional model providers, file storage, or OAuth integrations
  you intend to use, following `.env.example`.

```bash
docker compose -f docker-compose.prod.yml config --quiet
docker compose -f docker-compose.prod.yml pull
docker compose -f docker-compose.prod.yml up -d
```

Caddy provisions HTTPS. Open `https://app.example.com/login` using your domain,
then check the backend and connect your CLI:

```bash
curl --fail https://app.example.com/health
uv tool install stashai
stash signin --api https://app.example.com
```

Compose generates and persists the integration-encryption key when
`INTEGRATIONS_ENCRYPTION_KEY` is unset. Set it explicitly if you manage secrets
outside Compose. Inspect startup failures with
`docker compose -f docker-compose.prod.yml logs backend frontend`.

To upgrade, back up your database, review the incoming changes, then run:

```bash
git pull --ff-only
docker compose -f docker-compose.prod.yml pull
docker compose -f docker-compose.prod.yml up -d
```

The localhost Compose override currently references a `collab` service without
an image or build definition and fails configuration validation. Use the local
source setup above for running on localhost.
