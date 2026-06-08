# Security Operations Runbook

This runbook is the operating checklist for using Stash as a managed product
with a high-trust customer. Complete the evidence checks here before saying that
Stash is ready to ingest customer Slack, Jira, Gong, source repositories, session
transcripts, files, or exports.

Do not use this as marketing copy. It is an internal proof checklist.

## Webflow-Readiness Gate

Before a managed customer connects integrations, record these items in the deal
or launch review:

- Production environment name and deployment commit.
- Customer workspaces in scope.
- Integrations being connected and their approved scopes or allowlists.
- Named Stash owner for the customer launch.
- Named incident lead and escalation backup.
- Link to the latest successful backend, frontend, plugin, and dependency CI
  checks for the deployment commit.
- Link or screenshot proving the production vulnerability reporting path is
  live at `https://joinstash.ai/security` and
  `https://joinstash.ai/.well-known/security.txt`.

If any item is missing, do not claim high-trust managed readiness.

## Secrets And Production Access

Evidence to collect:

- Secrets are stored in the production platform secret manager, not in source,
  shell history, support tickets, Stash pages, or shared docs.
- Auth0, database, S3, Postmark, OAuth, Slack signing, admin, and integration
  encryption secrets have named owners.
- Staff with production access are listed by individual identity.
- Production access requires MFA.
- Staff departure checklist includes secret rotation and production-access
  removal.

Operating procedure:

- Review production access before the customer connects integrations.
- Remove access that is not needed for the customer launch.
- Rotate any shared secret known to a departed staff member.
- Record the review date, reviewer, and resulting access list.

## Customer Data Retention And Deletion

Evidence to collect:

- Application delete and purge paths have passing tests for pages, files,
  sessions, copied integration documents, source disconnect, and offboarding.
- Backup retention window is documented for production database and object
  storage.
- Account or workspace deletion requests have a named owner and completion
  checklist.

Operating procedure:

- When a customer disconnects Slack, Jira, Gong, or another source, verify the
  source row, copied documents, generated artifacts, and local encrypted
  credentials are gone.
- When a customer requests deletion, purge app rows first, then storage objects
  whose keys are no longer referenced by surviving rows.
- Record the deletion request, objects checked, completion time, and reviewer.
- Do not use soft-deleted copied integration content as evidence of deletion.

## Backup And Restore

Evidence to collect:

- Production database backup schedule.
- Object storage versioning or backup schedule.
- Latest restore-test date, operator, source backup identifier, destination
  environment, and validation result.

Operating procedure:

- Restore into an isolated non-production environment.
- Validate database migrations, workspace listing, file signed URLs, and a sample
  transcript read.
- Delete the restore environment after validation.
- Do not run restore tests in the customer's production workspace.

## Incident Response

Severity levels:

- Sev 1: confirmed or likely unauthorized customer-data exposure, credential
  exposure, destructive access, or active exploitation.
- Sev 2: exploitable vulnerability with customer-data impact but no known active
  exploitation.
- Sev 3: security weakness with limited or indirect customer-data impact.

Operating procedure:

- Assign an incident lead and scribe.
- Preserve relevant logs without copying secrets or customer content into the
  incident record.
- Revoke affected integration tokens and Stash API keys.
- Disable affected sync jobs or public links if containment requires it.
- Patch, verify, and deploy from a reviewed commit.
- Notify affected customers according to contractual obligations and legal
  review.
- Complete a post-incident review with root cause, customer impact, corrective
  actions, and owners.

## Integration Token Revocation

Use provider disconnect first whenever possible. If provider revocation fails,
Stash must still remove local encrypted credentials.

For a customer incident:

- Slack: disconnect the Slack integration, then verify Slack sources and
  `slack_messages` rows for that owner are gone.
- Jira: disconnect the Jira integration, then verify Jira sources and local
  index metadata for that owner are gone.
- Gong: disconnect the Gong integration, then verify Gong sources and
  `gong_documents` rows for that owner are gone.
- Granola, Google, GitHub, Notion, Asana, Snowflake: disconnect the provider and
  verify local credentials and source rows are gone.

Record provider, owner user, workspace, disconnect time, local deletion checks,
and any provider-side revocation errors.

## Observability And Logs

Evidence to collect:

- Production log sinks and retention windows.
- Redaction rules or processors applied before logs reach shared tools.
- Test evidence for application-level error redaction.
- List of staff who can read production logs.

Operating procedure:

- Do not log access tokens, refresh tokens, authorization codes, raw webhook
  bodies, customer document text, transcript snippets, storage keys, signed
  URLs, recipient emails, JQL, SQL text, Slack channel names, Gong meeting IDs,
  or provider response bodies.
- When debugging production, prefer internal IDs, exception type, status code,
  and hashed filters.
- If sensitive data reaches logs, treat it as an incident and rotate affected
  credentials.

## Subprocessors

Maintain a customer-facing list of infrastructure and subprocessors before
connecting high-trust customer integrations. Include:

- Vendor name.
- Service purpose.
- Data categories processed.
- Region, if configured or contractually relevant.
- Link to DPA or security terms.

Do not claim subprocessor readiness until the list is reviewed and shareable
with the customer.
