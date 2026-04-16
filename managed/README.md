# managed/

This directory holds **proprietary code** that does not get mirrored to the public OSS repo. Anything placed here is private-forever: hosted-only features (Auth0, billing, managed infra) live here and never ship to the community version.

When in doubt, put code **outside** this directory — the default is OSS-eligible. Only reach for `managed/` when the code is intentionally private.

## Why this directory exists

Stash will eventually live in two repos:

- **Public OSS repo** — community-facing source of truth.
- **Private managed repo** (this repo) — OSS code + managed-only additions.

When the public repo is created, everything outside `managed/` will be mirrored to it via `git subtree`. Everything inside `managed/` stays here.

Keeping the boundary clean now means the eventual open-sourcing step is mechanical instead of a big refactor.
