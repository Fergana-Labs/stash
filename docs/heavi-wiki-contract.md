# Heavi wiki rollout exception

PR #1096 keeps Heavi on its existing developer integration while other workspaces move to Skills. No Heavi application changes or new API keys are required.

- Shared knowledge remains at `/memory`; per-customer private knowledge remains at `/files/wiki` when `user_id` is supplied.
- Existing wiki folders, index pages and curator instructions survive the migration unchanged. New customer wikis and shared-wiki rotation keep the wiki format and curation prompt.
- The developer dashboard keeps Wiki terminology and `/developer/wiki`. Old wiki graph endpoints and response fields remain available only to opted-out workspaces.
- The global Skill catalog still exposes ordinary team Skills, excluding shared wikis, internal knowledge and private customer knowledge, including nested Skills. Customer reads continue to use their server-authorized roots.
- Transcript curation stays unmetered: no new token allowance or token charges apply to Heavi.

Migration 0223 skips wiki conversion for activated developer workspaces identified by domain `heaviai.com` or owner/scope account `stash@heaviai.com`. Migration 0225 sets `workspaces.legacy_wiki_enabled` for those same workspaces. Other workspaces default to false. These migrations run at backend startup after deployment.

The database column names and curation engine are shared. This is an explicit customer rollout exception, not a second deployment. Do not simply clear the flag to upgrade Heavi later: its wiki data and application paths must be migrated together in a separately reviewed change.

Verification uses synthetic workspaces and customer data. It does not exercise the live Heavi application or production credentials.
