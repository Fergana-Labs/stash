# Managed Security Readiness

This document records the security controls that must be true before Stash is used as a managed product for a customer that connects confidential systems such as Slack, Jira, Gong, or source repositories.

It is intentionally operational: do not use this as marketing copy. Use it to verify what is enforced in code, what CI checks continuously, and what still needs evidence from production operations.

Operational evidence collection lives in [security-operations.md](security-operations.md).

## Customer Data We Must Treat As Confidential

- Session transcripts and agent messages.
- Uploaded files, exported artifacts, generated pages, and copied documents.
- Slack messages and file metadata from approved channels.
- Jira issues, comments, project metadata, and JQL-derived results.
- Gong calls, transcripts, participants, and workspace metadata.
- Source integration credentials, OAuth tokens, refresh tokens, and webhook payloads.
- Workspace membership, permissions, analytics, and security audit events.

## Code Controls Required For Managed Access

- Managed Auth0 must fail closed. `AUTH0_ENABLED=true` requires `AUTH0_DOMAIN` and `AUTH0_AUDIENCE`, and Auth0 domains must be hostnames only.
- Managed Auth0 deployments must use HTTPS origins for `PUBLIC_URL`, `CORS_ORIGINS`, and `APP_BASE_URL`.
- Managed Auth0 deployments must set a valid `INTEGRATIONS_ENCRYPTION_KEY` Fernet keyring and complete HTTPS S3 storage config.
- Configured managed OAuth redirect URIs must be HTTPS callback URLs without path params, query strings, or fragments.
- Managed Auth0 deployments must reject local password registration, login, and profile password-change paths.
- Browser clients must use Auth0 access tokens for managed API calls. They must not carry long-lived Stash API keys.
- Managed Auth0 deployments must not expose generic Auth0-to-API-key exchange, manual API-key creation, or unauthenticated invite redemption paths; CLI keys require explicit short-lived session approval.
- Managed Auth0 deployments must reject password-login, manually-created, migrated, and invite-redemption API keys; only explicitly approved CLI device keys may authenticate as Stash API keys.
- Replayed CLI auth approvals must not mint orphaned device API keys.
- Expired CLI auth sessions must purge raw pending API keys and revoke approved-but-unclaimed CLI keys.
- Managed Auth0 deployments must not expose or accept legacy permanent workspace invite codes; use hashed, TTL-bounded invite tokens instead.
- User search must be scoped to a workspace where the requester is already a member; it must not enumerate users across tenants.
- Aggregate session lists must require current workspace access for workspace sessions; event authorship alone must not preserve access after a user leaves or is removed from a workspace.
- User-wide analytics visualizations must not serve cached workspace-derived labels or topics after membership changes; only explicit workspace-scoped visualization results may use persistent caches.
- Workspace writes must require editor or owner membership. Viewer access is read-only.
- Stash creation, item replacement, shared-page creation, and Stash write/admin grants must require workspace editor or owner membership.
- Non-owner Stash admins must not grant Stash access to users outside the workspace; external Stash read grants require a workspace owner.
- Agent runtime Stash tools must enforce the same workspace write, workspace owner, active-workspace, and item-write checks as backend Stash routes.
- Public, discoverable, or non-default workspace-readable session folders must require workspace owner membership; private session-folder management and session assignment must require current workspace write access.
- Public links must not create write-capable paths for Stashes, session folders, files, pages, tables, or collaboration documents.
- Export workers must re-check page/file access server-side and must block outbound network access during export rendering.
- Stored file access must use signed URLs. Raw storage URLs must not be returned to clients.
- Slack and Gong integrations must require explicit allowlists before sync. Empty allowlists must not default to broad access.
- Slack and Gong allowlist reductions must physically delete copied rows outside the current allowlist.
- Slack deleted-message events must remove copied message rows, and Slack changed-message events must update the existing copied row without duplicating old content.
- Copied source documents that disappear from an upstream crawl must be physically deleted rather than retained as hidden soft-deleted content.
- Slack indexing and history skip logs must not include channel names, provider error text, tokens, or message content.
- Jira source references and JQL must be scoped and quoted before execution.
- Source handles must be scoped to the route workspace and source owner.
- Source sync must require the source owner to still be a workspace member; leaving a workspace must remove member-owned connected sources and copied integration documents.
- Leaving or removing a workspace member must remove direct shares, share invites, Stash memberships, Stash invites, and member-owned Stashes that user received or granted in that workspace.
- OAuth token exchange and refresh failures must not include upstream response bodies, authorization codes, access tokens, refresh tokens, tenant details, or customer text in raised exceptions, logs, redirects, or API responses.
- Snowflake execution must reject multi-statement or CTE-prefixed SQL and clamp row limits before execution.
- Sensitive errors from storage, Auth0 JWT handling, Snowflake, source sync, OAuth callbacks, profile calls, and credential validation must be redacted before reaching API responses.
- Unhandled API exceptions must return a generic 500 and log only non-sensitive failure metadata.
- File download and table ingest failures must not log storage keys, bucket names, tokens, parser exception text, or workbook-derived content.
- Background task and file extraction failures must not persist or return exception messages, parser output, storage keys, or customer document text.
- Agent tool failures must not log tool inputs, customer queries, source handles, or transcript snippets.
- Source provider failures must log only source metadata and exception class, not provider response bodies, query text, tokens, or customer snippets.
- Integration indexer logs must not include external source references, provider resource identifiers, tool response text, customer document names, meeting IDs, or query text.
- Embedding failures must not log provider response bodies, exception messages, tokens, transcript text, copied integration content, or table row content.
- Export image failures must not log raw image sources, signed URLs, storage keys, or provider exception text.
- Email delivery failures must not log provider response bodies, recipient addresses, subjects, tokens, or customer text.
- Integration token encryption must fail closed on missing or invalid managed keyrings and support rotation through the Fernet keyring.
- Integration disconnect must delete Stash's local encrypted credentials even when provider token revocation or decryption fails.
- Disconnect and hard-delete paths must purge copied documents, stored files, and generated artifacts.
- Permanent delete paths must delete a storage object only when no surviving file or session artifact still references its storage key.
- Sensitive integration and source actions must emit workspace security audit events that only admins can read.
- Connected-source document reads, searches, history fetches, queries, and Stash snapshots must audit hashed refs or filters rather than storing source names, provider refs, queries, or customer content.
- Security audit log reads and denied member read attempts must themselves emit security audit events with hashed filter metadata.
- Shared-token admin endpoint access must emit global security audit events without storing tokens, client IPs, or raw query strings.
- Workspace invite token creation/revocation and member join/leave events must emit workspace security audit events without storing raw invite tokens, member names, emails, or workspace names in event metadata.
- Explicit Stash member grants and removals must emit workspace security audit events without storing recipient names, emails, or customer content in event metadata.
- Explicit object share grants, email invites, pending invite revocations, invite conversions, and share revocations must emit workspace security audit events without storing recipient names, emails, or customer content in event metadata.
- Page, file, and session delete/restore/permanent-purge actions must emit workspace security audit events without storing customer content, object names, or storage keys in event metadata.
- Credentialed CORS must reject wildcard origins.
- API and Next.js responses must include baseline security headers.
- Next.js routes must deny framing except for explicit published Stash embed routes.
- Admin secrets and cookie secrets must be at least 32 characters.

## Continuous Checks

The CI workflow includes checks that fail when:

- Backend Python requirements have known vulnerabilities.
- The CLI Python package has known vulnerabilities.
- The SDK Python package has known vulnerabilities.
- Frontend, www, or collab npm lockfiles contain moderate-or-higher advisories.
- Backend tests, plugin tests, frontend tests, backend lint, and frontend lint fail.

Run these checks locally before changing dependency versions:

```bash
python -m pip_audit -r backend/requirements.txt -r backend/requirements-dev.txt
python -m pip_audit .
python -m pip_audit sdk
(cd frontend && npm audit --audit-level=moderate --package-lock-only)
(cd www && npm audit --audit-level=moderate --package-lock-only)
(cd collab && npm audit --audit-level=moderate --package-lock-only)
```

## Production Evidence Required Before A High-Trust Customer Demo

These items cannot be proven by code alone. They need production configuration, logs, vendor records, or written operating procedures before we claim readiness for a customer like Webflow.

- Production secrets are stored in a managed secret store, rotated on staff departure, and never copied into source, logs, support tickets, or shared documents.
- Employee production access is least-privilege, tied to individual identities, protected by MFA, and reviewed before the customer connects integrations.
- Admin access to customer data is logged, reviewable, and limited to named support or incident-response cases.
- Customer data retention and deletion windows are documented, including copied integration data, transcripts, files, exports, backups, and derived artifacts.
- Backup and restore procedures are documented and tested against the production database and storage buckets.
- Incident response has an owner, severity levels, customer notification criteria, and a tested process for revoking integration tokens.
- Subprocessors and infrastructure vendors are listed with the data categories they process.
- Production observability redacts secrets and customer content from logs by default.
- The customer can disconnect Slack, Jira, Gong, and other integrations without leaving copied documents or stored files behind.
- A security contact and vulnerability reporting path are published at `/security` and `/.well-known/security.txt`, and the contact path is monitored.

## Demo Stance

For a managed customer demo, say that Stash has implemented application-level isolation, scoped integration ingestion, signed file access, audit logging for sensitive actions, error redaction, dependency scanning, and fail-closed managed Auth0 configuration.

Do not claim SOC 2, formal penetration-test coverage, or complete enterprise readiness until the production evidence above exists and has been reviewed.
